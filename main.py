"""
Polymarket 天气交易 Bot — 主入口

启动时初始化配置、日志、数据库，然后进入主循环。
"""

import sys

from src.utils.logger import setup_logger
from src.utils.db import init_db
from src.config.settings import TRADING_MODE, INITIAL_BANKROLL, DB_PATH


def main():
    # 初始化日志
    logger = setup_logger("weather_bot")
    logger.info("=" * 60)
    logger.info("🤖 Polymarket 天气交易 Bot")
    logger.info("=" * 60)

    # 显示运行模式
    logger.info(f"运行模式: {TRADING_MODE}")
    logger.info(f"初始资金: ${INITIAL_BANKROLL}")
    logger.info(f"数据库: {DB_PATH}")

    # 初始化数据库
    init_db()

    # 显示目标城市
    from src.config.cities import get_cities_by_priority
    cities = get_cities_by_priority()
    logger.info(f"目标城市 ({len(cities)} 个):")
    for city in cities:
        logger.info(f"  [{city.priority}] {city.display_name} ({city.name})")

    # 选择运行模式
    if "--scheduler" in sys.argv or "--daemon" in sys.argv:
        # 启动调度器（24/7 自动运行）
        from src.scheduler import start_scheduler
        start_scheduler()
    elif "--once" in sys.argv or "--scan" in sys.argv:
        # 单次扫描
        from src.scheduler import run_trading_cycle
        run_trading_cycle()
    elif "--summary" in sys.argv:
        # 显示交易汇总
        from src.execution.trader import get_trading_summary
        summary = get_trading_summary()
        print(f"\n📊 交易汇总:")
        print(f"  模式: {summary['mode']}")
        print(f"  总交易: {summary['total_trades']}")
        print(f"  未平仓: {summary['open_positions']}")
        print(f"  已结算: {summary['settled']}")
        print(f"  总 PnL: ${summary['total_pnl']:.2f}")
        print(f"  未平仓敞口: ${summary['open_exposure']:.2f}")
    else:
        # 默认: 单次扫描
        logger.info("\n提示: 使用以下参数运行:")
        logger.info("  python main.py --once       # 单次交易扫描")
        logger.info("  python main.py --scheduler   # 启动 24/7 调度器")
        logger.info("  python main.py --summary     # 显示交易汇总")
        logger.info("")
        logger.info("🚀 执行单次交易扫描...\n")

        from src.scheduler import run_trading_cycle
        run_trading_cycle()

        # 显示汇总
        from src.execution.trader import get_trading_summary
        summary = get_trading_summary()
        logger.info(f"\n📊 汇总: {summary['total_trades']} 笔交易, "
                     f"PnL ${summary['total_pnl']:.2f}, "
                     f"敞口 ${summary['open_exposure']:.2f}")


if __name__ == "__main__":
    main()
