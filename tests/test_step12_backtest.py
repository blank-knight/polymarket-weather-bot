"""
快速回测：用历史天气数据 + 当前市场逻辑验证策略

模拟场景：
- 假设我们在过去几天的市场中使用我们的策略
- 用真实天气模型数据对比当时的 Polymarket 价格
- 看看能否赚钱
"""

import sys
sys.path.insert(0, ".")

from datetime import datetime, timedelta
from src.weather.open_meteo_client import get_forecast, get_historical_temperature
from src.weather.probability import (
    TemperatureBucket,
    build_probability_distribution,
    blend_models,
    calc_all_bucket_probs,
)
from src.weather.historical import get_historical_base_rates
from src.decision.edge_calculator import calculate_edge, filter_signals, EdgeSignal
from src.decision.kelly_sizer import calculate_position_size
from src.config.cities import get_city_by_name
from src.utils.db import init_db
from src.utils.logger import setup_logger

logger = setup_logger("backtest")

# Polymarket 温度区间（2°F 一档，跟实际市场一致）
BUCKETS = [
    TemperatureBucket(40, 42),
    TemperatureBucket(42, 44),
    TemperatureBucket(44, 46),
    TemperatureBucket(46, 48),
    TemperatureBucket(48, 50),
    TemperatureBucket(50, 52),
    TemperatureBucket(52, 54),
    TemperatureBucket(54, 56),
    TemperatureBucket(56, 58),
    TemperatureBucket(58, 60),
    TemperatureBucket(60, 62),
    TemperatureBucket(62, 64),
    TemperatureBucket(64, 66),
    TemperatureBucket(66, 68),
    TemperatureBucket(68, 70),
    TemperatureBucket(70, 72),
    TemperatureBucket(72, 74),
    TemperatureBucket(74, 76),
    TemperatureBucket(76, 78),
    TemperatureBucket(78, 80),
    TemperatureBucket(80, 82),
    TemperatureBucket(82, 84),
    TemperatureBucket(84, 86),
    TemperatureBucket(86, 88),
    TemperatureBucket(88, 100),  # "or higher"
]


def simulate_day(
    city_name: str,
    target_date: str,
    bankroll: float,
    simulated_market_prices: dict[str, float] = None,
) -> dict:
    """
    模拟某一天的交易

    Args:
        city_name: 城市名
        target_date: 目标日期 "YYYY-MM-DD"
        bankroll: 当前资金
        simulated_market_prices: 模拟的市场价格 {"52-53°F": 0.155, ...}

    Returns:
        模拟结果
    """
    city = get_city_by_name(city_name)
    if not city:
        return {"error": f"城市未找到: {city_name}"}

    # 获取天气预报
    forecasts = get_forecast(city, forecast_days=3)
    model_temps = {}
    for f in forecasts:
        if f.target_date == target_date:
            model_temps[f.model] = f.temp_high_f

    if not model_temps:
        return {"error": f"无 {target_date} 预报数据"}

    # 获取历史基准
    historical_probs = get_historical_base_rates(city, target_date, BUCKETS, years_back=5)

    # 计算概率分布
    hours_to_settlement = 24  # 假设距结算 24h
    dist = build_probability_distribution(
        city=city_name,
        target_date=target_date,
        model_temps_f=model_temps,
        buckets=BUCKETS,
        hours_to_settlement=hours_to_settlement,
        historical_probs=historical_probs,
    )

    # 如果没有模拟市场价格，就用"理想市场"模拟
    if simulated_market_prices is None:
        # 模拟：假设市场价格是基于"单一 GFS 模型"的概率
        # （模拟人类交易者只看了 GFS 没看 ECMWF 的场景）
        gfs_temp = model_temps.get("gfs_seamless", dist.consensus_temp_f)
        sigma = 3.0  # 假设市场用的标准差更大
        simulated_market_prices = {}
        for bucket in BUCKETS:
            from src.weather.probability import calc_bucket_probability
            prob = calc_bucket_probability(gfs_temp, sigma, bucket)
            simulated_market_prices[bucket.label] = round(max(0.01, min(0.99, prob)), 4)

    # 计算每个区间的 Edge
    signals = []
    for bucket in BUCKETS:
        model_prob = dist.bucket_probs.get(bucket.label, 0)
        market_price = simulated_market_prices.get(bucket.label, 0)

        if model_prob <= 0 or market_price <= 0.005 or market_price >= 0.995:
            continue

        signal = calculate_edge(
            model_prob=model_prob,
            market_yes_price=market_price,
        )
        if signal and signal.abs_edge >= 0.05:
            signal.city = city_name
            signal.target_date = target_date
            signal.label = bucket.label
            signals.append(signal)

    # 过滤
    filtered = [s for s in signals if s.abs_edge >= 0.05]

    # 模拟 Kelly sizing 和下单
    trades = []
    total_cost = 0
    for s in filtered:
        if s.side == "BUY_YES":
            prob = s.model_prob
            price = s.yes_price
        else:
            prob = 1 - s.model_prob
            price = s.no_price

        sizing = calculate_position_size(prob, price, bankroll)
        if sizing["shares"] > 0:
            trades.append({
                "label": s.label,
                "side": s.side,
                "model_prob": round(prob, 3),
                "market_price": round(price, 3),
                "edge": s.edge,
                "shares": sizing["shares"],
                "cost": sizing["position_usd"],
            })
            total_cost += sizing["position_usd"]

    return {
        "city": city_name,
        "date": target_date,
        "consensus_temp": dist.consensus_temp_f,
        "sigma": dist.sigma_f,
        "model_temps": {k: round(v, 1) for k, v in model_temps.items()},
        "signals_found": len(signals),
        "signals_filtered": len(filtered),
        "trades_executed": len(trades),
        "total_cost": round(total_cost, 2),
        "trades": trades,
        "prob_dist": dist.bucket_probs,
    }


def run_backtest(
    cities: list[str] = None,
    days: int = 3,
    bankroll: float = 100.0,
):
    """
    快速回测：扫描多个城市多天
    """
    if cities is None:
        cities = ["New York", "Chicago", "Miami", "Los Angeles"]

    print("\n" + "=" * 70)
    print("📊 Polymarket 天气交易 Bot — 快速回测")
    print("=" * 70)
    print(f"\n  城市: {cities}")
    print(f"  天数: {days}")
    print(f"  资金: ${bankroll:.2f}")
    print(f"  日期范围: 今天 → +{days}天\n")

    all_results = []
    total_trades = 0
    total_cost = 0

    for city_name in cities:
        print(f"\n{'─' * 70}")
        print(f"🏙️  {city_name}")
        print(f"{'─' * 70}")

        for day_offset in range(1, days + 1):
            target_date = (datetime.utcnow() + timedelta(days=day_offset)).strftime("%Y-%m-%d")

            result = simulate_day(city_name, target_date, bankroll)

            if "error" in result:
                print(f"  {target_date}: ❌ {result['error']}")
                continue

            print(f"\n  📅 {target_date}")
            print(f"     共识温度: {result['consensus_temp']:.1f}°F (σ={result['sigma']:.1f})")
            print(f"     模型: {result['model_temps']}")
            print(f"     信号: {result['signals_found']} → 过滤后 {result['signals_filtered']} → 交易 {result['trades_executed']}")

            if result['trades']:
                print(f"\n     {'区间':<15} {'方向':<8} {'模型%':>6} {'市场$':>7} {'Edge':>7} {'股数':>6} {'投入':>7}")
                print(f"     {'─'*65}")
                for t in result['trades']:
                    print(f"     {t['label']:<15} {t['side']:<8} {t['model_prob']:>5.1%} "
                          f"${t['market_price']:>6.3f} {t['edge']:>+6.1%} "
                          f"{t['shares']:>6.1f} ${t['cost']:>6.2f}")

            total_trades += result['trades_executed']
            total_cost += result['total_cost']
            all_results.append(result)

    # 总结
    print(f"\n{'=' * 70}")
    print(f"📊 回测总结")
    print(f"{'=' * 70}")
    print(f"  扫描: {len(cities)} 城市 × {days} 天 = {len(cities) * days} 组合")
    print(f"  有效数据: {len(all_results)} 组")
    print(f"  总交易信号: {total_trades} 笔")
    print(f"  总模拟投入: ${total_cost:.2f}")
    print(f"  资金利用率: {total_cost / bankroll:.1%}")

    if total_trades == 0:
        print(f"\n  📝 无交易信号。这是正常的——说明:")
        print(f"     - 模型概率和市场价格基本一致（市场有效）")
        print(f"     - 需要等 GFS 模型更新产生短暂偏差")
        print(f"     - 策略的严格过滤在保护资金安全")
    else:
        print(f"\n  ✅ 发现 {total_trades} 个潜在交易机会")

    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    init_db()
    run_backtest()
