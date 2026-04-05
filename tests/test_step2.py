"""
Step 2 验证测试: 天气数据引擎

验证:
1. 能获取多模型预报
2. 能获取 GFS 预报
3. 能计算概率分布
4. 能获取历史数据
"""

import sys
sys.path.insert(0, ".")

from src.config.cities import get_city_by_name
from src.weather.open_meteo_client import get_forecast, get_gfs_forecast, get_historical_temperature
from src.weather.probability import (
    TemperatureBucket,
    build_probability_distribution,
    calc_bucket_probability,
    blend_models,
)
from src.weather.historical import get_historical_base_rates
from src.utils.db import init_db


# 定义温度区间（模拟 Polymarket 市场区间，5°F 一档）
TEST_BUCKETS = [
    TemperatureBucket(40, 45),
    TemperatureBucket(45, 50),
    TemperatureBucket(50, 55),
    TemperatureBucket(55, 60),
    TemperatureBucket(60, 65),
    TemperatureBucket(65, 70),
    TemperatureBucket(70, 75),
    TemperatureBucket(75, 80),
]


def test_forecast():
    """测试: 获取多模型预报"""
    print("\n" + "=" * 60)
    print("测试 1: 多模型预报")
    print("=" * 60)

    city = get_city_by_name("New York")
    results = get_forecast(city, models=["gfs_seamless", "ecmwf_ifs025"], forecast_days=2)

    for r in results:
        print(f"  {r.model} | {r.target_date} | 最高 {r.temp_high_f}°F / 最低 {r.temp_low_c:.1f}°C")

    assert len(results) > 0, "无预报数据"
    print("  ✅ 通过")
    return results


def test_gfs():
    """测试: GFS 专用端点"""
    print("\n" + "=" * 60)
    print("测试 2: GFS 预报")
    print("=" * 60)

    city = get_city_by_name("London")
    results = get_gfs_forecast(city, forecast_days=1)

    for r in results:
        print(f"  {r.model} | {r.target_date} | 最高 {r.temp_high_f}°F")

    assert len(results) > 0, "无 GFS 数据"
    print("  ✅ 通过")
    return results


def test_probability():
    """测试: 概率分布计算"""
    print("\n" + "=" * 60)
    print("测试 3: 概率分布")
    print("=" * 60)

    # 模拟: 共识温度 58°F, σ=3°F
    consensus = 58.0
    sigma = 3.0

    print(f"  共识温度: {consensus}°F, σ={sigma}°F")
    print(f"  温度区间概率:")

    for bucket in TEST_BUCKETS:
        prob = calc_bucket_probability(consensus, sigma, bucket)
        if prob > 0.01:
            print(f"    {bucket.label}: {prob:.1%}")

    # 验证: 55-60°F 区间应该概率最高
    prob_55_60 = calc_bucket_probability(consensus, sigma, TemperatureBucket(55, 60))
    prob_40_45 = calc_bucket_probability(consensus, sigma, TemperatureBucket(40, 45))

    print(f"\n  验证: P(55-60°F) = {prob_55_60:.2%} (应 > 50%)")
    print(f"  验证: P(40-45°F) = {prob_40_45:.2%} (应 < 1%)")

    assert prob_55_60 > 0.3, f"P(55-60) 太低: {prob_55_60}"
    assert prob_40_45 < 0.05, f"P(40-45) 太高: {prob_40_45}"
    print("  ✅ 通过")


def test_model_blend():
    """测试: 多模型融合"""
    print("\n" + "=" * 60)
    print("测试 4: 多模型融合")
    print("=" * 60)

    model_temps = {
        "ecmwf_ifs025": 58.5,
        "gfs_seamless": 60.2,
        "ukmo_seamless": 57.8,
        "nws_seamless": 59.0,
    }

    consensus, sigma, weights = blend_models(model_temps, hours_to_settlement=24)

    print(f"  各模型温度: {model_temps}")
    print(f"  融合后: {consensus:.1f}°F, σ={sigma:.1f}°F")
    print(f"  调整后权重: { {k: round(v, 3) for k, v in weights.items()} }")

    assert 57 < consensus < 61, f"共识温度异常: {consensus}"
    print("  ✅ 通过")


def test_historical():
    """测试: 历史温度"""
    print("\n" + "=" * 60)
    print("测试 5: 历史同日温度")
    print("=" * 60)

    city = get_city_by_name("New York")
    target_date = "2026-04-06"

    print(f"  获取 {city.display_name} 4月6日历史温度...")

    base_rates = get_historical_base_rates(city, target_date, TEST_BUCKETS, years_back=5)

    print(f"  历史基准概率:")
    for label, prob in base_rates.items():
        if prob > 0:
            print(f"    {label}: {prob:.0%}")

    assert len(base_rates) > 0, "无历史概率"
    print("  ✅ 通过")


def test_full_distribution():
    """测试: 完整概率分布构建"""
    print("\n" + "=" * 60)
    print("测试 6: 完整概率分布")
    print("=" * 60)

    model_temps = {
        "ecmwf_ifs025": 58.5,
        "gfs_seamless": 60.2,
        "ukmo_seamless": 57.8,
        "nws_seamless": 59.0,
    }

    dist = build_probability_distribution(
        city="New York",
        target_date="2026-04-06",
        model_temps_f=model_temps,
        buckets=TEST_BUCKETS,
        hours_to_settlement=24,
    )

    print(f"  共识: {dist.consensus_temp_f}°F")
    print(f"  σ: {dist.sigma_f}°F")
    print(f"  各区间概率:")
    for label, prob in sorted(dist.bucket_probs.items()):
        if prob > 0.001:
            bar = "█" * int(prob * 50)
            print(f"    {label}: {prob:.1%} {bar}")

    # 验证概率总和 ≈ 1
    total = sum(dist.bucket_probs.values())
    print(f"\n  概率总和: {total:.4f}")
    assert abs(total - 1.0) < 0.05, f"概率总和不等于1: {total}"
    print("  ✅ 通过")


if __name__ == "__main__":
    init_db()

    print("\n🌤️ Polymarket 天气 Bot — Step 2 验证测试\n")

    try:
        test_forecast()
        test_gfs()
        test_probability()
        test_model_blend()
        test_historical()
        test_full_distribution()

        print("\n" + "=" * 60)
        print("🎉 Step 2 全部测试通过!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
