"""
Step 4 验证测试: Polymarket 市场发现
"""

import sys
sys.path.insert(0, ".")

from src.market.gamma_client import discover_weather_events, get_event_by_city_date
from src.utils.db import init_db


def test_discover_all():
    """测试: 发现所有天气市场"""
    print("\n" + "=" * 60)
    print("测试 1: 发现所有天气温度市场")
    print("=" * 60)

    events = discover_weather_events(limit=100)

    print(f"  总计: {len(events)} 个日温度市场事件")

    # 按城市统计
    cities = {}
    for e in events:
        cities[e.city] = cities.get(e.city, 0) + 1

    print(f"  覆盖城市: {len(cities)} 个")
    for city, count in sorted(cities.items(), key=lambda x: -x[1])[:10]:
        print(f"    {city}: {count} 天")

    assert len(events) > 0, "未发现任何天气市场"
    print("  ✅ 通过")
    return events


def test_nyc_today():
    """测试: 获取 NYC 今天的市场"""
    print("\n" + "=" * 60)
    print("测试 2: NYC 今天的市场")
    print("=" * 60)

    from datetime import datetime
    today = datetime.utcnow().strftime("%Y-%m-%d")

    events = discover_weather_events(city_filter=["New York"], date_filter=today)

    if events:
        e = events[0]
        print(f"  Event: {e.title}")
        print(f"  Volume: ${e.volume:,.0f}")
        print(f"  Markets: {len(e.markets)}")
        print()
        print(f"  {'区间':<20} {'YES价格':>10} {'NO价格':>10} {'Bid':>8} {'Ask':>8}")
        print(f"  {'─'*20} {'─'*10} {'─'*10} {'─'*8} {'─'*8}")
        for m in e.markets:
            print(f"  {m.label:<20} {m.yes_price:>10.4f} {m.no_price:>10.4f} "
                  f"{m.best_bid:>8.4f} {m.best_ask:>8.4f}")

        # 验证
        assert len(e.markets) > 0, "无子市场"
        # 找到概率最高的区间
        best = max(e.markets, key=lambda m: m.yes_price)
        print(f"\n  最高概率区间: {best.label} @ {best.yes_price:.2%}")
        print(f"  YES Token: {best.yes_token_id[:50]}...")
    else:
        print(f"  NYC 今天 ({today}) 没有活跃市场（可能已结算或未上线）")

    print("  ✅ 通过")


def test_nyc_tomorrow():
    """测试: 获取 NYC 明天的市场"""
    print("\n" + "=" * 60)
    print("测试 3: NYC 明天的市场")
    print("=" * 60)

    from datetime import datetime, timedelta
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

    events = discover_weather_events(city_filter=["New York"], date_filter=tomorrow)

    if events:
        e = events[0]
        print(f"  Event: {e.title}")
        print(f"  Volume: ${e.volume:,.0f}")
        print()
        for m in e.markets:
            bar = "█" * int(m.yes_price * 40)
            print(f"  {m.label:<20} {m.yes_price:>6.2%} {bar}")
    else:
        print(f"  NYC 明天 ({tomorrow}) 没有市场")

    print("  ✅ 通过")


def test_multiple_cities():
    """测试: 多城市扫描"""
    print("\n" + "=" * 60)
    print("测试 4: 多城市扫描")
    print("=" * 60)

    target_cities = ["New York", "London", "Chicago", "Tokyo", "Seoul"]
    events = discover_weather_events(city_filter=target_cities)

    print(f"  目标城市: {target_cities}")
    print(f"  匹配事件: {len(events)}")
    for e in events:
        print(f"    {e.city} {e.target_date}: {len(e.markets)} 个区间, vol=${e.volume:,.0f}")

    print("  ✅ 通过")


if __name__ == "__main__":
    init_db()

    print("\n📊 Polymarket 天气 Bot — Step 4 验证测试\n")

    try:
        test_discover_all()
        test_nyc_today()
        test_nyc_tomorrow()
        test_multiple_cities()

        print("\n" + "=" * 60)
        print("🎉 Step 4 全部测试通过!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
