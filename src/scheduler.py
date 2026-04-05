"""
主循环 + 调度器

Bot 24/7 自动运行：
- 每 6 小时触发主交易循环（跟随 GFS/ECMWF 更新）
- 每 1 小时触发仓位检查（止损/止盈/结算前平仓）
"""

from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config.settings import INITIAL_BANKROLL, TRADING_MODE
from src.config.cities import get_cities_by_priority
from src.decision.signal_generator import generate_all_signals
from src.risk.risk_manager import run_all_checks
from src.execution.trader import execute_trade, get_open_positions, close_position, get_trading_summary
from src.utils.db import init_db, get_bankroll, update_bankroll
from src.utils.logger import setup_logger

logger = setup_logger("main_loop")


def get_current_bankroll() -> float:
    """获取当前 bankroll"""
    br = get_bankroll()
    if br:
        return float(br["balance"])
    return INITIAL_BANKROLL


# ──────────────────────────────────────────────
# 主交易循环
# ──────────────────────────────────────────────

def run_trading_cycle():
    """
    主交易循环

    流程:
    1. 获取 bankroll
    2. 扫描所有目标城市，生成信号
    3. 对每个信号做风控检查
    4. 执行交易
    5. 更新 bankroll
    6. 如果有未平仓仓位，启动 WebSocket 监控
    """
    logger.info("=" * 50)
    logger.info("🔄 主交易循环开始")
    logger.info("=" * 50)

    bankroll = get_current_bankroll()
    logger.info(f"当前 bankroll: ${bankroll:.2f} | 模式: {TRADING_MODE}")

    # 目标城市（P0 + P1）
    cities = get_cities_by_priority(priority=1)
    city_names = [c.name for c in cities]

    # 生成信号（扫描未来 2 天）
    try:
        signals = generate_all_signals(
            bankroll=bankroll,
            city_names=city_names,
            days_ahead=2,
        )
    except Exception as e:
        logger.error(f"信号生成失败: {e}")
        return

    if not signals:
        logger.info("无交易信号，本轮跳过")
        return

    logger.info(f"生成 {len(signals)} 个信号")

    # 执行交易
    executed = 0
    rejected = 0
    total_cost = 0

    for signal in signals:
        # 估算距结算时间
        try:
            target_dt = datetime.strptime(signal.target_date, "%Y-%m-%d")
            hours_to_settlement = max(0, (target_dt - datetime.utcnow()).total_seconds() / 3600)
        except ValueError:
            hours_to_settlement = 24

        # 风控检查
        risk = run_all_checks(
            position_usd=signal.cost_usd,
            bankroll=bankroll,
            spread=signal.limit_price,  # simplified
            best_bid=signal.limit_price * 0.99,
            best_ask=signal.limit_price * 1.01,
            hours_to_settlement=hours_to_settlement,
        )

        # 执行
        result = execute_trade(signal, risk)

        if result["status"] in ("simulated", "open"):
            executed += 1
            total_cost += signal.cost_usd
            logger.info(
                f"  ✅ #{executed} {signal.city} {signal.target_date} "
                f"{signal.label} {signal.side} "
                f"{signal.shares:.1f}股 @${signal.limit_price:.4f} "
                f"=${signal.cost_usd:.2f} Edge={signal.edge:+.1%} "
                f"[{signal.confidence}]"
            )
        else:
            rejected += 1
            logger.debug(f"  ❌ {signal.city} {signal.label}: {result.get('reason', '')}")

    logger.info(f"本轮完成: {executed} 笔执行, {rejected} 笔拦截, 总投入 ${total_cost:.2f}")
    logger.info("=" * 50)


# ──────────────────────────────────────────────
# 仓位检查循环
# ──────────────────────────────────────────────

def run_position_check():
    """
    仓位检查循环（每小时）

    检查所有未平仓仓位：
    - 是否需要止盈
    - 是否需要止损
    - 是否即将结算需要平仓
    """
    positions = get_open_positions()
    if not positions:
        return

    logger.info(f"📋 仓位检查: {len(positions)} 个未平仓")

    now = datetime.utcnow()

    for p in positions:
        # 检查结算时间
        try:
            target_dt = datetime.strptime(p["date"], "%Y-%m-%d")
            # 结算时间是目标日期的 23:59 UTC
            settlement = target_dt + timedelta(hours=23, minutes=59)
            hours_left = max(0, (settlement - now).total_seconds() / 3600)

            if hours_left < 2:
                # 结算前 2 小时，标记结算
                logger.info(f"  ⏰ #{p['id']} {p['city']} {p['date']} "
                            f"{p['temperature_range']} 即将结算 ({hours_left:.1f}h)")
                # TODO: 实际结算需要等待 Polymarket 出结果
                # 目前模拟模式先不动
        except (ValueError, KeyError):
            pass


# ──────────────────────────────────────────────
# 调度器
# ──────────────────────────────────────────────

def start_scheduler():
    """
    启动调度器

    主交易循环: 每 6 小时（UTC 00:30, 06:30, 12:30, 18:30）
    仓位检查:   每 1 小时
    """
    init_db()

    # 初始化 bankroll（如果还没有记录）
    br = get_bankroll()
    if not br:
        update_bankroll(INITIAL_BANKROLL)
        logger.info(f"初始化 bankroll: ${INITIAL_BANKROLL}")

    scheduler = BlockingScheduler()

    # 主交易循环: 每 6 小时（模型更新后 30 分钟执行，给 API 缓冲时间）
    scheduler.add_job(
        run_trading_cycle,
        CronTrigger(hour="0,6,12,18", minute=30),
        id="trading_cycle",
        name="主交易循环",
        max_instances=1,
        misfire_grace_time=300,
    )

    # 仓位检查: 每 1 小时
    scheduler.add_job(
        run_position_check,
        CronTrigger(minute=15),  # 每小时第 15 分钟
        id="position_check",
        name="仓位检查",
        max_instances=1,
        misfire_grace_time=120,
    )

    logger.info("🤖 Polymarket 天气交易 Bot 调度器启动")
    logger.info(f"  模式: {TRADING_MODE}")
    logger.info(f"  bankroll: ${get_current_bankroll():.2f}")
    logger.info(f"  主循环: 每 6h (00:30, 06:30, 12:30, 18:30 UTC)")
    logger.info(f"  仓位检查: 每小时 :15")
    logger.info("  Ctrl+C 停止")

    # 启动时立即跑一次
    logger.info("\n🚀 启动时执行首次交易扫描...")
    run_trading_cycle()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("调度器停止")

    # 打印最终汇总
    summary = get_trading_summary()
    logger.info(f"\n📊 最终汇总:")
    logger.info(f"  总交易: {summary['total_trades']}")
    logger.info(f"  未平仓: {summary['open_positions']}")
    logger.info(f"  总 PnL: ${summary['total_pnl']:.2f}")
