"""
WebSocket 实时价格流

连接 Polymarket CLOB WebSocket，实时监控持仓相关 token 的价格变化。
支持实时止盈/止损/追踪止损。
"""

import json
import asyncio
from datetime import datetime
from typing import Callable

import websockets

from src.config.settings import CLOB_WS_URL
from src.config.settings import (
    TAKE_PROFIT_EDGE_CAPTURE,
    TRAILING_STOP_PULLBACK,
    STOP_LOSS_RATIO,
    EDGE_CONVERGENCE_EXIT,
)
from src.execution.trader import get_open_positions, close_position, get_trading_summary
from src.utils.db import get_db
from src.utils.logger import setup_logger

logger = setup_logger("ws_stream")


class PriceStream:
    """
    Polymarket CLOB WebSocket 价格流

    订阅指定 token 的实时价格更新，
    触发止盈/止损/追踪止损逻辑。
    """

    def __init__(self):
        self.ws = None
        self.subscriptions: dict[str, dict] = {}  # token_id → {"entry_price", "peak_price", "side", "trade_id"}
        self.running = False
        self.on_price_update: Callable | None = None

    def subscribe_positions(self):
        """
        订阅所有未平仓仓位的 token
        """
        positions = get_open_positions()
        for p in positions:
            if p["status"] not in ("open", "simulated"):
                continue

            # 确定要监听的 token
            from src.market.gamma_client import discover_weather_events
            # 简化：直接用数据库中的 token_id
            token_id = p.get("token_id", "")
            if not token_id:
                continue

            self.subscriptions[token_id] = {
                "trade_id": p["id"],
                "city": p["city"],
                "date": p["date"],
                "range": p["temperature_range"],
                "side": p["side"],
                "entry_price": p["price"],
                "peak_price": p["price"],
            }

        logger.info(f"订阅 {len(self.subscriptions)} 个 token 的实时价格")

    async def connect(self):
        """连接 WebSocket"""
        try:
            self.ws = await websockets.connect(CLOB_WS_URL)
            logger.info(f"WebSocket 已连接: {CLOB_WS_URL}")
            return True
        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}")
            return False

    async def subscribe(self, token_ids: list[str]):
        """
        发送订阅消息

        Polymarket CLOB WebSocket 订阅格式：
        {"type": "subscribe", "markets": [{"market": "<token_id>", "side": "all"}]}
        """
        if not self.ws:
            return

        markets = [{"market": tid, "side": "all"} for tid in token_ids]
        msg = json.dumps({"type": "subscribe", "markets": markets})
        await self.ws.send(msg)
        logger.info(f"已发送订阅请求: {len(token_ids)} 个市场")

    async def listen(self):
        """
        监听 WebSocket 消息

        消息格式：
        {"event": "price_change", "market": "<token_id>", "side": "BUY"/"SELL", "price": "0.55"}
        """
        if not self.ws:
            return

        self.running = True
        logger.info("开始监听 WebSocket 消息...")

        try:
            async for raw_msg in self.ws:
                if not self.running:
                    break

                try:
                    msg = json.loads(raw_msg)
                    await self._handle_message(msg)
                except json.JSONDecodeError:
                    logger.debug(f"非 JSON 消息: {raw_msg[:100]}")
                except Exception as e:
                    logger.error(f"消息处理错误: {e}")

        except websockets.ConnectionClosed:
            logger.warning("WebSocket 连接断开")
        except Exception as e:
            logger.error(f"监听异常: {e}")
        finally:
            self.running = False

    async def _handle_message(self, msg: dict):
        """处理单条消息"""
        event = msg.get("event", "")
        token_id = msg.get("market", "")

        if event == "price_change" and token_id in self.subscriptions:
            price = float(msg.get("price", 0))
            if price <= 0:
                return

            sub = self.subscriptions[token_id]

            # 更新峰值价格
            if price > sub["peak_price"]:
                sub["peak_price"] = price

            # 检查止盈/止损
            action = self._check_exit_conditions(token_id, price)

            if action:
                logger.info(
                    f"🚨 {action} 触发: {sub['city']} {sub['date']} {sub['range']} "
                    f"价格={price:.4f} 入场={sub['entry_price']:.4f}"
                )

                # 模拟模式下记录
                entry = sub["entry_price"]
                if sub["side"] == "BUY_YES":
                    pnl = (price - entry) * 100  # 简化
                else:
                    pnl = (entry - price) * 100

                close_position(sub["trade_id"], pnl=round(pnl, 2))
                del self.subscriptions[token_id]

            # 回调
            if self.on_price_update:
                self.on_price_update(token_id, price)

    def _check_exit_conditions(self, token_id: str, current_price: float) -> str | None:
        """
        检查退出条件

        Returns:
            "take_profit" / "trailing_stop" / "stop_loss" / "edge_convergence" / None
        """
        sub = self.subscriptions.get(token_id)
        if not sub:
            return None

        entry = sub["entry_price"]
        peak = sub["peak_price"]
        side = sub["side"]

        # 计算盈亏比例
        if side == "BUY_YES":
            pnl_ratio = (current_price - entry) / entry if entry > 0 else 0
        else:
            pnl_ratio = (entry - current_price) / entry if entry > 0 else 0

        # 1. 止损
        if pnl_ratio <= STOP_LOSS_RATIO:
            return "stop_loss"

        # 2. 追踪止损
        peak_pnl = (peak - entry) / entry if entry > 0 else 0
        pullback = peak_pnl - pnl_ratio
        if peak_pnl > 0.10 and pullback >= TRAILING_STOP_PULLBACK:
            return "trailing_stop"

        # 3. 止盈（简化：价格达到入场价的 1.5x）
        if pnl_ratio >= TAKE_PROFIT_EDGE_CAPTURE:
            return "take_profit"

        return None

    async def close(self):
        """关闭连接"""
        self.running = False
        if self.ws:
            await self.ws.close()
            logger.info("WebSocket 已关闭")


async def run_ws_stream():
    """
    启动 WebSocket 流（独立异步任务）
    """
    stream = PriceStream()
    stream.subscribe_positions()

    if not stream.subscriptions:
        logger.info("无未平仓仓位，跳过 WebSocket")
        return

    token_ids = list(stream.subscriptions.keys())

    connected = await stream.connect()
    if not connected:
        return

    await stream.subscribe(token_ids)
    await stream.listen()


def start_ws_in_background():
    """
    在后台启动 WebSocket 流（同步调用）
    """
    try:
        asyncio.run(run_ws_stream())
    except KeyboardInterrupt:
        logger.info("WebSocket 流停止")
    except Exception as e:
        logger.error(f"WebSocket 后台任务异常: {e}")
