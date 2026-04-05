"""
信号生成器

整合天气模型概率、市场价格、Edge 计算、Kelly Sizing，
生成最终交易信号。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.weather.open_meteo_client import get_forecast
from src.weather.probability import (
    TemperatureBucket,
    build_probability_distribution,
)
from src.weather.historical import get_historical_base_rates
from src.market.gamma_client import discover_weather_events, TempMarket
from src.market.clob_client import get_market_price
from src.decision.edge_calculator import EdgeSignal, calculate_edge, filter_signals, rank_signals
from src.decision.kelly_sizer import calculate_position_size
from src.config.settings import MIN_EDGE
from src.config.cities import get_city_by_name
from src.utils.logger import setup_logger

logger = setup_logger("signal_gen")


@dataclass
class TradeSignal:
    """完整交易信号"""
    city: str
    target_date: str
    label: str                # 温度区间
    side: str                 # "BUY_YES" / "BUY_NO"
    token_id: str             # 买入方向的 token ID
    market_id: str
    model_prob: float
    market_prob: float
    edge: float
    shares: float
    limit_price: float
    cost_usd: float
    expected_value: float
    kelly_raw: float
    kelly_scaled: float
    confidence: str           # "high" / "medium" / "low"
    generated_at: str


def _market_to_bucket(market: TempMarket) -> Optional[TemperatureBucket]:
    """将 TempMarket 转换为 TemperatureBucket"""
    if market.temp_low_f is not None and market.temp_high_f is not None:
        return TemperatureBucket(low_f=market.temp_low_f, high_f=market.temp_high_f)
    elif market.temp_high_f is not None and market.temp_low_f is None:
        # "X°F or below" → 无下限
        return TemperatureBucket(low_f=-999, high_f=market.temp_high_f)
    elif market.temp_low_f is not None and market.temp_high_f is None:
        # "X°F or higher" → 无上限
        return TemperatureBucket(low_f=market.temp_low_f, high_f=999)
    return None


def _estimate_hours_to_settlement(target_date: str) -> float:
    """估算距结算的小时数"""
    try:
        target = datetime.strptime(target_date, "%Y-%m-%d")
        # 假设结算时间是目标日期的 23:59 UTC
        now = datetime.utcnow()
        delta = target - now
        return max(0, delta.total_seconds() / 3600)
    except ValueError:
        return 24  # 默认 24h


def generate_signals_for_city(
    city_name: str,
    target_date: str,
    bankroll: float,
) -> list[TradeSignal]:
    """
    为指定城市和日期生成交易信号

    流程:
    1. 获取天气模型预报
    2. 获取 Polymarket 市场
    3. 对每个温度区间计算 Edge
    4. Kelly Sizing
    5. 生成信号

    Args:
        city_name: 城市名 (如 "New York")
        target_date: 目标日期 "YYYY-MM-DD"
        bankroll: 当前资金

    Returns:
        TradeSignal 列表
    """
    signals = []

    # 1. 查找城市配置
    city = get_city_by_name(city_name)
    if not city:
        logger.warning(f"城市未找到: {city_name}")
        return []

    # 2. 获取 Polymarket 市场
    events = discover_weather_events(
        city_filter=[city_name],
        date_filter=target_date,
    )
    if not events:
        logger.info(f"[{city_name}] {target_date}: 无活跃市场")
        return []

    event = events[0]
    logger.info(f"[{city_name}] {target_date}: 找到 {len(event.markets)} 个温度区间市场")

    # 3. 获取天气预报
    forecasts = get_forecast(city, forecast_days=3)
    if not forecasts:
        logger.warning(f"[{city_name}] 天气预报获取失败")
        return []

    # 汇总各模型温度
    model_temps = {}
    for f in forecasts:
        if f.target_date == target_date:
            model_temps[f.model] = f.temp_high_f

    if not model_temps:
        logger.warning(f"[{city_name}] {target_date}: 无该日期预报")
        return []

    # 4. 构建温度区间列表（从市场数据提取）
    buckets = []
    for m in event.markets:
        bucket = _market_to_bucket(m)
        if bucket:
            buckets.append(bucket)

    if not buckets:
        return []

    # 5. 获取历史基准概率
    hours_to_settlement = _estimate_hours_to_settlement(target_date)
    historical_probs = get_historical_base_rates(city, target_date, buckets)

    # 6. 构建概率分布
    dist = build_probability_distribution(
        city=city_name,
        target_date=target_date,
        model_temps_f=model_temps,
        buckets=buckets,
        hours_to_settlement=hours_to_settlement,
        historical_probs=historical_probs,
    )

    # 7. 对每个市场计算 Edge
    edge_signals = []
    for m in event.markets:
        # 找到对应的模型概率
        bucket = _market_to_bucket(m)
        if not bucket:
            continue

        model_prob = dist.bucket_probs.get(m.label, 0)
        if model_prob <= 0:
            continue

        # 获取市场价格
        price = get_market_price(m.yes_token_id, gamma_price=m.yes_price)
        if not price:
            continue

        # 计算 Edge
        signal = calculate_edge(
            model_prob=model_prob,
            market_yes_price=price.yes_price,
            market_no_price=price.no_price,
            best_bid=price.best_bid,
            best_ask=price.best_ask,
            spread=price.spread,
            volume=m.volume,
            source=price.source if hasattr(price, 'source') else "gamma",
        )

        if signal:
            signal.city = city_name
            signal.target_date = target_date
            signal.label = m.label
            signal.market_id = m.market_id
            signal.token_id = m.yes_token_id
            edge_signals.append(signal)

    # 8. 过滤和排序
    filtered = filter_signals(edge_signals)
    ranked = rank_signals(filtered)

    logger.info(f"[{city_name}] {target_date}: "
                f"{len(edge_signals)} 个信号 → {len(filtered)} 个通过过滤")

    # 9. Kelly Sizing
    for s in ranked:
        # 确定买入方向
        if s.side == "BUY_YES":
            buy_price = s.yes_price
            token_id = s.token_id  # YES token
        else:
            buy_price = s.no_price
            # 需要找到 NO token
            # 从 event 中找对应的 no_token_id
            no_token = ""
            for m in event.markets:
                if m.label == s.label:
                    no_token = m.no_token_id
                    break
            token_id = no_token

        if buy_price <= 0:
            continue

        # 计算模型概率（买入方向）
        if s.side == "BUY_YES":
            prob = s.model_prob
        else:
            prob = 1 - s.model_prob

        sizing = calculate_position_size(
            prob=prob,
            price=buy_price,
            bankroll=bankroll,
        )

        if sizing["shares"] <= 0:
            continue

        # 置信度
        if s.abs_edge >= 0.20:
            confidence = "high"
        elif s.abs_edge >= 0.10:
            confidence = "medium"
        else:
            confidence = "low"

        signal = TradeSignal(
            city=city_name,
            target_date=target_date,
            label=s.label,
            side=s.side,
            token_id=token_id,
            market_id=s.market_id,
            model_prob=round(prob if s.side == "BUY_YES" else 1 - s.model_prob, 4),
            market_prob=s.market_prob,
            edge=s.edge,
            shares=sizing["shares"],
            limit_price=round(buy_price, 4),
            cost_usd=sizing["position_usd"],
            expected_value=sizing["expected_value"],
            kelly_raw=sizing["kelly_raw"],
            kelly_scaled=sizing["kelly_scaled"],
            confidence=confidence,
            generated_at=datetime.utcnow().isoformat(),
        )
        signals.append(signal)

    return signals


def generate_all_signals(
    bankroll: float,
    city_names: list[str] = None,
    days_ahead: int = 2,
) -> list[TradeSignal]:
    """
    扫描所有目标城市，生成全部交易信号

    优化: 一次性获取所有天气市场，再在本地按城市和日期过滤

    Args:
        bankroll: 当前资金
        city_names: 城市列表（默认使用 P0+P1 城市）
        days_ahead: 扫描未来几天

    Returns:
        TradeSignal 列表，按 Edge 排序
    """
    from datetime import datetime, timedelta

    if city_names is None:
        city_names = ["New York", "London", "Chicago", "Paris", "Los Angeles", "Miami"]

    # 计算目标日期
    target_dates = []
    for day_offset in range(1, days_ahead + 1):
        target_dates.append(
            (datetime.utcnow() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        )

    # 一次性获取所有天气市场
    logger.info(f"获取所有天气市场 (city_filter={city_names})...")
    all_events = discover_weather_events(
        limit=200,
        city_filter=city_names,
    )

    if not all_events:
        logger.warning("未发现任何天气市场")
        return []

    logger.info(f"发现 {len(all_events)} 个天气市场事件")

    all_signals = []

    for event in all_events:
        # 跳过非目标日期
        if event.target_date not in target_dates:
            continue

        try:
            signals = generate_signals_for_event(
                event=event,
                bankroll=bankroll,
            )
            all_signals.extend(signals)
        except Exception as e:
            logger.error(f"[{event.city}] {event.target_date} 信号生成失败: {e}")

    # 按 abs(edge) 排序
    all_signals.sort(key=lambda s: abs(s.edge), reverse=True)

    logger.info(f"共生成 {len(all_signals)} 个交易信号")
    return all_signals


def generate_signals_for_event(
    event,
    bankroll: float,
) -> list[TradeSignal]:
    """
    为单个 CityWeatherEvent 生成交易信号

    Args:
        event: CityWeatherEvent
        bankroll: 当前资金

    Returns:
        TradeSignal 列表
    """
    from src.market.clob_client import get_market_price

    city_name = event.city
    target_date = event.target_date
    signals = []

    # 获取城市配置
    city = get_city_by_name(city_name)
    if not city:
        logger.debug(f"城市未找到: {city_name}")
        return []

    logger.info(f"[{city_name}] {target_date}: 找到 {len(event.markets)} 个温度区间市场")

    # 获取天气预报
    forecasts = get_forecast(city, forecast_days=3)
    if not forecasts:
        logger.warning(f"[{city_name}] 天气预报获取失败")
        return []

    model_temps = {}
    for f in forecasts:
        if f.target_date == target_date:
            model_temps[f.model] = f.temp_high_f

    if not model_temps:
        logger.warning(f"[{city_name}] {target_date}: 无该日期预报")
        return []

    # 构建温度区间
    buckets = []
    for m in event.markets:
        bucket = _market_to_bucket(m)
        if bucket:
            buckets.append(bucket)

    if not buckets:
        return []

    # 历史基准概率
    hours_to_settlement = _estimate_hours_to_settlement(target_date)
    historical_probs = get_historical_base_rates(city, target_date, buckets)

    # 概率分布
    dist = build_probability_distribution(
        city=city_name,
        target_date=target_date,
        model_temps_f=model_temps,
        buckets=buckets,
        hours_to_settlement=hours_to_settlement,
        historical_probs=historical_probs,
    )

    # Edge + Kelly
    edge_signals = []
    for m in event.markets:
        bucket = _market_to_bucket(m)
        if not bucket:
            continue

        model_prob = dist.bucket_probs.get(m.label, 0)
        if model_prob <= 0:
            continue

        price = get_market_price(m.yes_token_id, gamma_price=m.yes_price)
        if not price:
            continue

        signal = calculate_edge(
            model_prob=model_prob,
            market_yes_price=price.yes_price,
            market_no_price=price.no_price,
            best_bid=price.best_bid,
            best_ask=price.best_ask,
            spread=price.spread,
            volume=m.volume,
            source="gamma",
        )

        if signal:
            signal.city = city_name
            signal.target_date = target_date
            signal.label = m.label
            signal.market_id = m.market_id
            signal.token_id = m.yes_token_id
            edge_signals.append(signal)

    # 过滤和排序
    filtered = filter_signals(edge_signals)
    ranked = rank_signals(filtered)

    logger.info(f"[{city_name}] {target_date}: "
                f"{len(edge_signals)} 个信号 → {len(filtered)} 个通过过滤")

    for s in ranked:
        if s.side == "BUY_YES":
            buy_price = s.yes_price
            token_id = s.token_id
            prob = s.model_prob
        else:
            buy_price = s.no_price
            no_token = ""
            for m in event.markets:
                if m.label == s.label:
                    no_token = m.no_token_id
                    break
            token_id = no_token
            prob = 1 - s.model_prob

        if buy_price <= 0:
            continue

        sizing = calculate_position_size(prob=prob, price=buy_price, bankroll=bankroll)
        if sizing["shares"] <= 0:
            continue

        confidence = "high" if s.abs_edge >= 0.20 else ("medium" if s.abs_edge >= 0.10 else "low")

        signal = TradeSignal(
            city=city_name,
            target_date=target_date,
            label=s.label,
            side=s.side,
            token_id=token_id,
            market_id=s.market_id,
            model_prob=round(prob if s.side == "BUY_YES" else 1 - s.model_prob, 4),
            market_prob=s.market_prob,
            edge=s.edge,
            shares=sizing["shares"],
            limit_price=round(buy_price, 4),
            cost_usd=sizing["position_usd"],
            expected_value=sizing["expected_value"],
            kelly_raw=sizing["kelly_raw"],
            kelly_scaled=sizing["kelly_scaled"],
            confidence=confidence,
            generated_at=datetime.utcnow().isoformat(),
        )
        signals.append(signal)

    return signals
