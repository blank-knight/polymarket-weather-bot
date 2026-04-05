"""
Step 9-10 验证测试: 风控模块 + 交易执行
"""

import sys
sys.path.insert(0, ".")

from src.risk.risk_manager import (
    run_all_checks,
    check_position_limit,
    check_total_exposure,
    check_daily_loss,
    check_settlement_time,
)
from src.execution.trader import (
    execute_trade,
    get_open_positions,
    get_trading_summary,
    close_position,
)
from src.decision.edge_calculator import EdgeSignal
from src.decision.signal_generator import TradeSignal
from src.utils.db import init_db
from datetime import datetime


def make_signal(**kwargs):
    """创建测试用 TradeSignal"""
    defaults = dict(
        city="New York", target_date="2026-04-06", label="52-53°F",
        side="BUY_YES", token_id="test_token_123", market_id="mkt_123",
        model_prob=0.25, market_prob=0.155, edge=0.095,
        shares=18.1, limit_price=0.155, cost_usd=2.81,
        expected_value=0.095, kelly_raw=0.1124, kelly_scaled=0.0281,
        confidence="medium", generated_at=datetime.utcnow().isoformat(),
    )
    defaults.update(kwargs)
    return TradeSignal(**defaults)


def test_position_limit():
    print("\n" + "=" * 60)
    print("测试 1: 单笔仓位限制")
    print("=" * 60)

    # 正常
    r = check_position_limit(10, 100)
    print(f"  $10 / $100 = 10% → {'✅' if r.passed else '❌'} {r.reason}")
    assert r.passed

    # 超限
    r = check_position_limit(20, 100)
    print(f"  $20 / $100 = 20% → {'✅' if r.passed else '❌ 拦截'} {r.reason}")
    assert not r.passed

    # bankroll = 0
    r = check_position_limit(1, 0)
    assert not r.passed
    print(f"  $1 / $0 → ❌ 拦截: {r.reason}")
    print("  ✅ 通过")


def test_settlement_time():
    print("\n" + "=" * 60)
    print("测试 2: 结算时间保护")
    print("=" * 60)

    r = check_settlement_time(24)
    print(f"  24h → {'✅' if r.passed else '❌'}")
    assert r.passed

    r = check_settlement_time(1)
    print(f"  1h → {'❌ 拦截' if not r.passed else '✅'}: {r.reason}")
    assert not r.passed
    print("  ✅ 通过")


def test_all_checks():
    print("\n" + "=" * 60)
    print("测试 3: 综合风控检查")
    print("=" * 60)

    # 正常交易应通过
    r = run_all_checks(
        position_usd=5, bankroll=100, spread=0.02,
        best_bid=0.15, best_ask=0.16, hours_to_settlement=24,
    )
    print(f"  正常交易: {'✅ 通过' if r.passed else '❌ ' + r.reason}")
    assert r.passed

    # 超限交易应被拦截
    r = run_all_checks(
        position_usd=50, bankroll=100, spread=0.02,
        best_bid=0.15, best_ask=0.16, hours_to_settlement=24,
    )
    print(f"  超大仓位: {'❌ 拦截' if not r.passed else '✅'}: {r.reason}")
    assert not r.passed

    print("  ✅ 通过")


def test_simulated_trade():
    print("\n" + "=" * 60)
    print("测试 4: 模拟交易执行")
    print("=" * 60)

    signal = make_signal()
    from src.risk.risk_manager import RiskCheckResult
    risk_ok = RiskCheckResult(passed=True, reason="全部通过")

    result = execute_trade(signal, risk_ok)
    print(f"  状态: {result['status']}")
    print(f"  信息: {result.get('message', '')}")

    assert result["status"] == "simulated"
    assert result["trade_id"] > 0
    print("  ✅ 通过")


def test_rejected_trade():
    print("\n" + "=" * 60)
    print("测试 5: 风控拦截")
    print("=" * 60)

    signal = make_signal()
    from src.risk.risk_manager import RiskCheckResult
    risk_reject = RiskCheckResult(passed=False, reason="[position_limit] 超限")

    result = execute_trade(signal, risk_reject)
    print(f"  状态: {result['status']}")
    print(f"  原因: {result['reason']}")

    assert result["status"] == "rejected"
    print("  ✅ 通过")


def test_positions_and_summary():
    print("\n" + "=" * 60)
    print("测试 6: 仓位查询和汇总")
    print("=" * 60)

    positions = get_open_positions()
    print(f"  未平仓仓位: {len(positions)}")
    for p in positions[:3]:
        print(f"    #{p['id']}: {p['city']} {p['date']} {p['temperature_range']} "
              f"{p['side']} {p['quantity']}股 @${p['price']:.4f}")

    summary = get_trading_summary()
    print(f"\n  交易汇总:")
    print(f"    总交易: {summary['total_trades']}")
    print(f"    未平仓: {summary['open_positions']}")
    print(f"    已结算: {summary['settled']}")
    print(f"    总PnL:  ${summary['total_pnl']:.2f}")
    print(f"    未平仓敞口: ${summary['open_exposure']:.2f}")
    print(f"    模式: {summary['mode']}")

    assert summary["total_trades"] > 0
    print("  ✅ 通过")


def test_close_position():
    print("\n" + "=" * 60)
    print("测试 7: 平仓")
    print("=" * 60)

    # 先开一个仓位
    signal = make_signal(label="54-55°F", cost_usd=3.50)
    from src.risk.risk_manager import RiskCheckResult
    risk_ok = RiskCheckResult(passed=True)
    result = execute_trade(signal, risk_ok)
    trade_id = result["trade_id"]

    # 平仓
    close_position(trade_id, pnl=1.50, status="settled")

    summary = get_trading_summary()
    print(f"  平仓 #{trade_id}, PnL=+$1.50")
    print(f"  当前汇总: 总PnL=${summary['total_pnl']:.2f}")
    print("  ✅ 通过")


if __name__ == "__main__":
    init_db()

    print("\n🛡️ Polymarket 天气 Bot — Step 9-10 验证测试\n")

    try:
        test_position_limit()
        test_settlement_time()
        test_all_checks()
        test_simulated_trade()
        test_rejected_trade()
        test_positions_and_summary()
        test_close_position()

        print("\n" + "=" * 60)
        print("🎉 Step 9-10 全部测试通过!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
