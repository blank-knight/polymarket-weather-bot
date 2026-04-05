"""
Step 5 验证测试: CLOB 价格查询
"""

import sys
sys.path.insert(0, ".")

from src.market.gamma_client import discover_weather_events
from src.market.clob_client import (
    get_last_trade_price,
    get_midpoint,
    get_order_book,
    get_market_price,
    get_prices_for_event,
)
from src.utils.db import init_db
from src.utils.logger import setup_logger

logger = setup_logger("test_step5")


def test_single_price():
    """测试: 获取单个 token 价格"""
    print("\n" + "=" * 60)
    print("测试 1: 单个 token 价格查询")
    print("=" * 60)

    # 先获取一个真实的 token ID
    events = discover_weather_events(limit=50)
    assert len(events) > 0, "无天气市场"

    event = events[0]
    market = event.markets[0]
    token_id = market.yes_token_id

    print(f"  市场: {market.question[:60]}...")
    print(f"  Token: {token_id[:50]}...")

    # 最近成交价
    last_price = get_last_trade_price(token_id)
    print(f"  最近成交价: {last_price}")

    # 中间价
    mid = get_midpoint(token_id)
    print(f"  中间价: {mid}")

    assert last_price is not None or mid is not None, "价格查询全部失败"
    print("  ✅ 通过")


def test_order_book():
    """测试: 订单簿深度"""
    print("\n" + "=" * 60)
    print("测试 2: 订单簿深度")
    print("=" * 60)

    events = discover_weather_events(limit=50)
    event = events[0]
    market = event.markets[0]

    book = get_order_book(market.yes_token_id, depth=5)

    print(f"  市场: {market.label}")
    print(f"  Best Bid: {book.best_bid}")
    print(f"  Best Ask: {book.best_ask}")
    print(f"  Spread: {book.spread}")
    print(f"  Mid Price: {book.mid_price}")
    print(f"  Bid 深度: {len(book.bid_levels)} 档")
    print(f"  Ask 深度: {len(book.ask_levels)} 档")

    if book.bid_levels:
        print(f"\n  {'价格':>8} {'数量':>10}")
        for level in book.bid_levels[:5]:
            print(f"  {level.price:>8.4f} {level.size:>10.2f}")

    if book.ask_levels:
        print(f"\n  {'价格':>8} {'数量':>10}")
        for level in book.ask_levels[:5]:
            print(f"  {level.price:>8.4f} {level.size:>10.2f}")

    print("  ✅ 通过")


def test_market_price():
    """测试: 完整市场价格"""
    print("\n" + "=" * 60)
    print("测试 3: 完整市场价格")
    print("=" * 60)

    events = discover_weather_events(limit=50)
    event = events[0]

    print(f"  Event: {event.title}")
    print()

    for m in event.markets:
        price = get_market_price(m.yes_token_id, gamma_price=m.yes_price)
        if price:
            # 对比 Gamma API 返回的价格和 CLOB 价格
            gamma_yes = m.yes_price
            clob_yes = price.yes_price
            diff = abs(gamma_yes - clob_yes)
            match = "✓" if diff < 0.05 else "✗"

            print(f"  {m.label:<20} Gamma={gamma_yes:.4f} CLOB={clob_yes:.4f} "
                  f"spread={price.spread:.4f} {match}")
        else:
            print(f"  {m.label:<20} (无CLOB数据)")

    print("  ✅ 通过")


def test_batch_prices():
    """测试: 批量获取价格"""
    print("\n" + "=" * 60)
    print("测试 4: 批量获取 NYC 市场价格")
    print("=" * 60)

    from datetime import datetime
    tomorrow = datetime.now().strftime("%Y-%m-%d")
    # 计算明天
    from datetime import timedelta
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    events = discover_weather_events(
        city_filter=["New York"],
        date_filter=tomorrow,
    )

    if not events:
        print(f"  NYC {tomorrow} 无市场，跳过")
        print("  ✅ 跳过")
        return

    event = events[0]
    prices = get_prices_for_event(event.markets)

    print(f"  Event: {event.title}")
    print(f"  获取到 {len(prices)} 个市场价格")
    print()
    print(f"  {'区间':<20} {'YES':>6} {'Bid':>8} {'Ask':>8} {'Spread':>8}")
    print(f"  {'─'*20} {'─'*6} {'─'*8} {'─'*8} {'─'*8}")

    for label, price in sorted(prices.items()):
        print(f"  {label:<20} {price.yes_price:>6.2%} {price.best_bid:>8.4f} "
              f"{price.best_ask:>8.4f} {price.spread:>8.4f}")

    print("  ✅ 通过")


if __name__ == "__main__":
    init_db()

    print("\n📊 Polymarket 天气 Bot — Step 5 验证测试\n")

    try:
        test_single_price()
        test_order_book()
        test_market_price()
        test_batch_prices()

        print("\n" + "=" * 60)
        print("🎉 Step 5 全部测试通过!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
