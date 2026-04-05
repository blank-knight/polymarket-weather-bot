"""
Step 6-8 验证测试: Edge 计算 + Kelly Sizing + 信号生成
"""

import sys
sys.path.insert(0, ".")

from src.decision.edge_calculator import calculate_edge, filter_signals, rank_signals, EdgeSignal
from src.decision.kelly_sizer import calculate_position_size, kelly_fraction
from src.utils.db import init_db
from src.utils.logger import setup_logger

logger = setup_logger("test_step678")


def test_edge_calculation():
    """测试: Edge 计算"""
    print("\n" + "=" * 60)
    print("测试 1: Edge 计算")
    print("=" * 60)

    # 场景: 模型说 54-55°F 概率 30%, 市场只给 15.5%
    signal = calculate_edge(
        model_prob=0.30,
        market_yes_price=0.155,
    )
    print(f"  模型概率: {signal.model_prob:.1%}")
    print(f"  市场价格: {signal.market_prob:.1%}")
    print(f"  Edge: {signal.edge:+.1%} ({signal.side})")
    assert signal.edge > 0, "Edge 应为正"
    assert signal.side == "BUY_YES"
    assert signal.abs_edge > 0.05
    print("  ✅ 通过")

    # 场景: 模型说 60-61°F 概率 5%, 市场给了 14.5%
    signal2 = calculate_edge(
        model_prob=0.05,
        market_yes_price=0.145,
    )
    print(f"\n  模型概率: {signal2.model_prob:.1%}")
    print(f"  市场价格: {signal2.market_prob:.1%}")
    print(f"  Edge: {signal2.edge:+.1%} ({signal2.side})")
    assert signal2.edge < 0, "Edge 应为负"
    assert signal2.side == "BUY_NO"
    print("  ✅ 通过")


def test_edge_filtering():
    """测试: Edge 过滤"""
    print("\n" + "=" * 60)
    print("测试 2: Edge 过滤")
    print("=" * 60)

    signals = [
        EdgeSignal(city="NYC", target_date="2026-04-06", label="50-51°F", market_id="", token_id="", side="BUY_YES", model_prob=0.08, market_prob=0.045, edge=0.035, abs_edge=0.035, yes_price=0.045, no_price=0.955, best_bid=0.01, best_ask=0.045, spread=0.035, volume=1000, liquidity=0, source="gamma"),
        EdgeSignal(city="NYC", target_date="2026-04-06", label="52-53°F", market_id="", token_id="", side="BUY_YES", model_prob=0.25, market_prob=0.155, edge=0.095, abs_edge=0.095, yes_price=0.155, no_price=0.845, best_bid=0.01, best_ask=0.145, spread=0.035, volume=5000, liquidity=0, source="gamma"),
        EdgeSignal(city="NYC", target_date="2026-04-06", label="54-55°F", market_id="", token_id="", side="BUY_YES", model_prob=0.30, market_prob=0.275, edge=0.025, abs_edge=0.025, yes_price=0.275, no_price=0.725, best_bid=0.01, best_ask=0.265, spread=0.025, volume=8000, liquidity=0, source="gamma"),
        EdgeSignal(city="NYC", target_date="2026-04-06", label="56-57°F", market_id="", token_id="", side="BUY_NO", model_prob=0.20, market_prob=0.255, edge=-0.055, abs_edge=0.055, yes_price=0.255, no_price=0.745, best_bid=0.01, best_ask=0.245, spread=0.035, volume=6000, liquidity=0, source="gamma"),
        EdgeSignal(city="NYC", target_date="2026-04-06", label="58-59°F", market_id="", token_id="", side="BUY_NO", model_prob=0.05, market_prob=0.145, edge=-0.095, abs_edge=0.095, yes_price=0.145, no_price=0.855, best_bid=0.01, best_ask=0.135, spread=0.035, volume=3000, liquidity=0, source="gamma"),
    ]

    # 过滤: min_edge = 5%
    filtered = filter_signals(signals, min_edge=0.05)

    print(f"  原始信号: {len(signals)}")
    print(f"  过滤后:   {len(filtered)}")
    for s in filtered:
        print(f"    {s.label:<15} Edge={s.edge:+.1%} {s.side}")

    assert len(filtered) == 3, f"应过滤到 3 个，实际 {len(filtered)}"
    print("  ✅ 通过")


def test_kelly_sizing():
    """测试: Kelly 仓位计算"""
    print("\n" + "=" * 60)
    print("测试 3: Kelly Sizing")
    print("=" * 60)

    bankroll = 100.0

    # 场景1: 模型 30%, 价格 $0.155
    r1 = calculate_position_size(0.30, 0.155, bankroll)
    print(f"  场景1: 模型30%, 价格$0.155, bankroll=${bankroll}")
    print(f"    Kelly Raw: {r1['kelly_raw']:.4f}")
    print(f"    Kelly Scaled (Quarter): {r1['kelly_scaled']:.4f}")
    print(f"    仓位: ${r1['position_usd']:.2f} ({r1['position_ratio']:.1%})")
    print(f"    股数: {r1['shares']:.1f}")
    print(f"    期望收益/股: {r1['expected_value']:.4f}")

    assert r1["position_usd"] > 0, "应有正仓位"
    assert r1["position_usd"] <= bankroll * 0.15, f"不超过15%: {r1['position_usd']}"
    print("  ✅ 通过")

    # 场景2: 模型 5%, 价格 $0.145 (BUY_NO → 实际模型认为NO概率95%)
    r2 = calculate_position_size(0.95, 0.855, bankroll)  # NO 方向
    print(f"\n  场景2: 模型NO=95%, NO价格$0.855, bankroll=${bankroll}")
    print(f"    仓位: ${r2['position_usd']:.2f} ({r2['position_ratio']:.1%})")
    print(f"    股数: {r2['shares']:.1f}")
    print("  ✅ 通过")

    # 场景3: 无 Edge (模型和市场一致)
    r3 = calculate_position_size(0.50, 0.50, bankroll)
    print(f"\n  场景3: 模型50%, 价格$0.50 (无Edge)")
    print(f"    仓位: ${r3['position_usd']:.2f}")
    assert r3["position_usd"] == 0, "无 Edge 不应下注"
    print("  ✅ 通过")


def test_kelly_edge_cases():
    """测试: Kelly 边界情况"""
    print("\n" + "=" * 60)
    print("测试 4: Kelly 边界情况")
    print("=" * 60)

    bankroll = 100.0

    # 极端高概率 + 低价 = 超大 Kelly（应被 cap 在 15%）
    r = calculate_position_size(0.95, 0.10, bankroll)
    print(f"  高确定性(95%)+低价($0.10): 仓位比例={r['position_ratio']:.1%}")
    assert r["position_ratio"] <= 0.15
    print("  ✅ 通过")

    # 极小 bankroll
    r = calculate_position_size(0.80, 0.50, 10.0)
    print(f"  小bankroll($10): 仓位=${r['position_usd']:.2f}")
    print("  ✅ 通过")

    # bankroll = 0
    r = calculate_position_size(0.80, 0.50, 0)
    assert r["position_usd"] == 0
    print(f"  bankroll=$0: 仓位=${r['position_usd']:.2f}")
    print("  ✅ 通过")


def test_signal_ranking():
    """测试: 信号排序"""
    print("\n" + "=" * 60)
    print("测试 5: 信号排序")
    print("=" * 60)

    signals = [
        EdgeSignal(city="NYC", target_date="2026-04-06", label="54-55°F", market_id="", token_id="", side="BUY_YES", model_prob=0.30, market_prob=0.275, edge=0.025, abs_edge=0.025, yes_price=0.275, no_price=0.725, best_bid=0, best_ask=0, spread=0, volume=0, liquidity=0, source="gamma"),
        EdgeSignal(city="NYC", target_date="2026-04-06", label="52-53°F", market_id="", token_id="", side="BUY_YES", model_prob=0.25, market_prob=0.155, edge=0.095, abs_edge=0.095, yes_price=0.155, no_price=0.845, best_bid=0, best_ask=0, spread=0, volume=0, liquidity=0, source="gamma"),
        EdgeSignal(city="NYC", target_date="2026-04-06", label="58-59°F", market_id="", token_id="", side="BUY_NO", model_prob=0.05, market_prob=0.145, edge=-0.095, abs_edge=0.095, yes_price=0.145, no_price=0.855, best_bid=0, best_ask=0, spread=0, volume=0, liquidity=0, source="gamma"),
        EdgeSignal(city="NYC", target_date="2026-04-06", label="56-57°F", market_id="", token_id="", side="BUY_YES", model_prob=0.28, market_prob=0.255, edge=0.025, abs_edge=0.025, yes_price=0.255, no_price=0.745, best_bid=0, best_ask=0, spread=0, volume=0, liquidity=0, source="gamma"),
    ]

    ranked = rank_signals(signals)

    print(f"  排序结果 (按 |Edge| 降序):")
    for i, s in enumerate(ranked):
        print(f"    {i+1}. {s.label:<15} Edge={s.edge:+.1%} |Edge|={s.abs_edge:.1%}")

    # 最大 Edge 应排在最前
    assert ranked[0].abs_edge >= ranked[1].abs_edge
    print("  ✅ 通过")


def test_end_to_end_logic():
    """测试: 端到端逻辑验证（不调真实API）"""
    print("\n" + "=" * 60)
    print("测试 6: 端到端逻辑验证")
    print("=" * 60)

    bankroll = 100.0

    # 模拟: 天气模型说 52-53°F 概率 25%, 市场只有 15.5%
    model_prob = 0.25
    market_price = 0.155

    print(f"  模型概率: {model_prob:.1%}")
    print(f"  市场价格: ${market_price}")
    print()

    # 1. Edge
    signal = calculate_edge(model_prob=model_prob, market_yes_price=market_price)
    print(f"  Edge: {signal.edge:+.1%} → {signal.side}")
    assert signal.edge > 0.05, f"Edge 应 > 5%: {signal.edge}"

    # 2. Kelly
    sizing = calculate_position_size(model_prob, market_price, bankroll)
    print(f"  Kelly Raw: {sizing['kelly_raw']:.4f}")
    print(f"  Quarter-Kelly: {sizing['kelly_scaled']:.4f}")
    print(f"  投入: ${sizing['position_usd']:.2f}")
    print(f"  股数: {sizing['shares']:.1f}")
    print(f"  每股期望收益: ${sizing['expected_value']:.4f}")
    print(f"  如果赢了收益: ${sizing['shares'] * (1 - market_price):.2f}")
    print(f"  如果输了损失: ${sizing['position_usd']:.2f}")

    assert sizing["position_usd"] > 0
    assert sizing["position_usd"] <= bankroll * 0.15

    print("  ✅ 通过")


if __name__ == "__main__":
    init_db()

    print("\n🧠 Polymarket 天气 Bot — Step 6-8 验证测试\n")

    try:
        test_edge_calculation()
        test_edge_filtering()
        test_kelly_sizing()
        test_kelly_edge_cases()
        test_signal_ranking()
        test_end_to_end_logic()

        print("\n" + "=" * 60)
        print("🎉 Step 6-8 全部测试通过!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
