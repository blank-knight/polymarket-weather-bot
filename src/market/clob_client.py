"""
Polymarket CLOB 价格查询客户端

查询实时价格、订单簿深度、最近成交。
"""

from dataclasses import dataclass
from typing import Optional

import requests
from src.config.settings import CLOB_API_URL
from src.utils.logger import setup_logger

logger = setup_logger("clob_api")


@dataclass
class OrderBookLevel:
    """订单簿一档"""
    price: float
    size: float


@dataclass
class OrderBookSnapshot:
    """订单簿快照"""
    token_id: str
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    bid_levels: list[OrderBookLevel] = None
    ask_levels: list[OrderBookLevel] = None
    spread: Optional[float] = None
    mid_price: Optional[float] = None

    def __post_init__(self):
        if self.bid_levels is None:
            self.bid_levels = []
        if self.ask_levels is None:
            self.ask_levels = []


@dataclass
class MarketPrice:
    """市场价格快照"""
    token_id: str
    yes_price: float       # YES 当前价格
    no_price: float        # NO 当前价格
    last_trade_price: float  # 最近成交价
    best_bid: float        # 最佳买价
    best_ask: float        # 最佳卖价
    spread: float          # 价差
    mid_price: float       # 中间价
    volume_24h: float = 0  # 24h 成交量


def get_last_trade_price(token_id: str) -> Optional[float]:
    """
    获取最近成交价

    Args:
        token_id: CLOB token ID

    Returns:
        最近成交价 (0-1) 或 None
    """
    try:
        resp = requests.get(
            f"{CLOB_API_URL}/last-trade-price",
            params={"token_id": token_id},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        price = float(data.get("price", 0))
        return price

    except Exception as e:
        logger.debug(f"获取最近成交价失败 {token_id[:20]}...: {e}")
        return None


def get_midpoint(token_id: str) -> Optional[float]:
    """
    获取中间价

    Args:
        token_id: CLOB token ID

    Returns:
        中间价 (0-1) 或 None
    """
    try:
        resp = requests.get(
            f"{CLOB_API_URL}/midpoint",
            params={"token_id": token_id},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        mid = float(data.get("mid", 0))
        return mid

    except Exception as e:
        logger.debug(f"获取中间价失败 {token_id[:20]}...: {e}")
        return None


def get_price_history(
    token_id: str,
    interval: str = "1h",
    fidelity: int = 24,
) -> list[dict]:
    """
    获取价格历史

    Args:
        token_id: CLOB token ID
        interval: 时间间隔 ("1h", "1d", "5m")
        fidelity: 数据点数量

    Returns:
        [{"t": timestamp, "p": price}, ...]
    """
    try:
        resp = requests.get(
            f"{CLOB_API_URL}/prices",
            params={
                "token_id": token_id,
                "interval": interval,
                "fidelity": fidelity,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("history", [])

    except Exception as e:
        logger.debug(f"获取价格历史失败 {token_id[:20]}...: {e}")
        return []


def get_order_book(
    token_id: str,
    depth: int = 5,
) -> OrderBookSnapshot:
    """
    获取订单簿快照

    Args:
        token_id: CLOB token ID
        depth: 深度档数

    Returns:
        OrderBookSnapshot
    """
    try:
        resp = requests.get(
            f"{CLOB_API_URL}/book",
            params={"token_id": token_id},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        # 解析 bids 和 asks
        bids_raw = data.get("bids", [])
        asks_raw = data.get("asks", [])

        bids = []
        for b in bids_raw[:depth]:
            price = float(b.get("price", 0))
            size = float(b.get("size", 0))
            if price > 0 and size > 0:
                bids.append(OrderBookLevel(price=price, size=size))

        asks = []
        for a in asks_raw[:depth]:
            price = float(a.get("price", 0))
            size = float(a.get("size", 0))
            if price > 0 and size > 0:
                asks.append(OrderBookLevel(price=price, size=size))

        best_bid = bids[0].price if bids else None
        best_ask = asks[0].price if asks else None

        spread = None
        mid_price = None
        if best_bid is not None and best_ask is not None:
            spread = round(best_ask - best_bid, 4)
            mid_price = round((best_bid + best_ask) / 2, 4)

        return OrderBookSnapshot(
            token_id=token_id,
            best_bid=best_bid,
            best_ask=best_ask,
            bid_levels=bids,
            ask_levels=asks,
            spread=spread,
            mid_price=mid_price,
        )

    except Exception as e:
        logger.error(f"获取订单簿失败 {token_id[:20]}...: {e}")
        return OrderBookSnapshot(token_id=token_id)


def get_market_price(
    token_id: str,
    gamma_price: float = None,
) -> Optional[MarketPrice]:
    """
    获取完整市场价格信息

    优先级：
    1. CLOB 订单簿中间价（流动性最好）
    2. CLOB 最近成交价
    3. Gamma API 价格（fallback）

    Args:
        token_id: YES token ID
        gamma_price: Gamma API 返回的 YES 价格（fallback 用）

    Returns:
        MarketPrice 或 None
    """
    try:
        # 获取最近成交价
        last_price = get_last_trade_price(token_id)

        # 获取订单簿
        book = get_order_book(token_id)

        # 使用优先级：CLOB mid > CLOB last > Gamma > None
        if book.mid_price and book.mid_price > 0.001:
            yes_price = book.mid_price
            source = "clob_mid"
        elif last_price and last_price > 0.001:
            yes_price = last_price
            source = "clob_last"
        elif gamma_price is not None and gamma_price > 0:
            yes_price = gamma_price
            source = "gamma"
        else:
            return None

        no_price = round(1.0 - yes_price, 4)

        spread = book.spread if book.spread is not None else 0
        best_bid = book.best_bid if book.best_bid is not None else 0
        best_ask = book.best_ask if book.best_ask is not None else 0

        logger.debug(f"价格来源={source}, YES={yes_price:.4f}, token={token_id[:20]}...")

        return MarketPrice(
            token_id=token_id,
            yes_price=round(yes_price, 4),
            no_price=no_price,
            last_trade_price=last_price if last_price else 0,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            mid_price=book.mid_price if book.mid_price else yes_price,
        )

    except Exception as e:
        logger.error(f"获取市场价格失败 {token_id[:20]}...: {e}")
        return None


def get_prices_for_event(
    markets: list,  # List[TempMarket] from gamma_client
) -> dict[str, MarketPrice]:
    """
    批量获取一个 Event 下所有市场的价格

    使用 Gamma API 价格作为 fallback（CLOB 订单簿可能没有）

    Args:
        markets: TempMarket 列表

    Returns:
        {label: MarketPrice} 映射
    """
    results = {}

    for m in markets:
        price = get_market_price(
            token_id=m.yes_token_id,
            gamma_price=m.yes_price,  # Gamma 价格作为 fallback
        )
        if price:
            results[m.label] = price

    logger.info(f"获取 {len(markets)} 个市场价格，成功 {len(results)} 个")
    return results
