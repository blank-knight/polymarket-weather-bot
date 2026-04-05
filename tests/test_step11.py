"""
Step 11 验证测试: 主循环 + 端到端验证
"""

import sys
sys.path.insert(0, ".")

from src.scheduler import run_trading_cycle
from src.execution.trader import get_trading_summary, get_open_positions
from src.utils.db import init_db
from src.utils.logger import setup_logger

logger = setup_logger("test_step11")


def test_single_cycle():
    """测试: 单次交易循环"""
    print("\n" + "=" * 60)
    print("测试 1: 端到端交易循环")
    print("=" * 60)

    # 重建数据库确保干净
    init_db()

    from src.utils.db import update_bankroll
    update_bankroll(100.0)

    print("  bankroll: $100.00")
    print("  模式: SIMULATION")
    print("  扫描中...\n")

    run_trading_cycle()

    summary = get_trading_summary()
    print(f"\n  结果:")
    print(f"    总信号数: (见上方日志)")
    print(f"    总交易: {summary['total_trades']}")
    print(f"    未平仓: {summary['open_positions']}")
    print(f"    总 PnL: ${summary['total_pnl']:.2f}")
    print(f"    敞口: ${summary['open_exposure']:.2f}")

    # 显示未平仓
    if summary['open_positions'] > 0:
        positions = get_open_positions()
        print(f"\n  未平仓仓位:")
        for p in positions:
            print(f"    #{p['id']}: {p['city']} {p['date']} {p['temperature_range']} "
                  f"{p['side']} {p['quantity']:.1f}股 @${p['price']:.4f} "
                  f"Edge={p['edge']:+.1%}")

    print("\n  ✅ 通过")


if __name__ == "__main__":
    init_db()

    print("\n🤖 Polymarket 天气 Bot — Step 11 端到端测试\n")

    try:
        test_single_cycle()

        print("\n" + "=" * 60)
        print("🎉 Step 11 测试通过!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
