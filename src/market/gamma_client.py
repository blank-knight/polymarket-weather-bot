"""
Polymarket Gamma API 客户端

自动发现天气温度市场，解析城市、日期、温度区间。
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional

import requests
from src.config.settings import GAMMA_API_URL
from src.utils.logger import setup_logger

logger = setup_logger("gamma_api")


@dataclass
class TempMarket:
    """单个温度区间市场"""
    question: str               # 完整问题
    city: str                   # 城市名
    target_date: str            # YYYY-MM-DD
    temp_low_f: Optional[float]  # 区间下限 (°F), None = 无下限
    temp_high_f: Optional[float] # 区间上限 (°F), None = 无上限
    label: str                  # 区间标签 "67°F or below", "68-69°F", "86°F or higher"
    yes_price: float            # YES 价格 (0-1)
    no_price: float             # NO 价格 (0-1)
    yes_token_id: str           # YES token ID (用于下单)
    no_token_id: str            # NO token ID
    market_id: str              # 市场 ID
    condition_id: str           # 条件 ID
    volume: float = 0           # 交易量
    liquidity: float = 0        # 流动性
    best_bid: float = 0         # 最佳买价
    best_ask: float = 0         # 最佳卖价


@dataclass
class CityWeatherEvent:
    """一个城市一天的所有温度区间市场"""
    title: str                  # Event 标题
    city: str                   # 城市名
    target_date: str            # YYYY-MM-DD
    volume: float               # 总交易量
    markets: list[TempMarket] = field(default_factory=list)

    def get_market_for_range(self, low: float, high: float) -> Optional[TempMarket]:
        """根据温度范围查找对应市场"""
        for m in self.markets:
            if m.temp_low_f == low and m.temp_high_f == high:
                return m
        return None


# 城市名映射（Polymarket 用名 → 我们的城市配置名）
CITY_NAME_MAP = {
    "nyc": "New York",
    "new york city": "New York",
    "new york": "New York",
    "london": "London",
    "chicago": "Chicago",
    "paris": "Paris",
    "los angeles": "Los Angeles",
    "miami": "Miami",
    "seoul": "Seoul",
    "tokyo": "Tokyo",
    "sydney": "Sydney",
    "toronto": "Toronto",
    "seattle": "Seattle",
    "dallas": "Dallas",
    "atlanta": "Atlanta",
    "austin": "Austin",
    "denver": "Denver",
    "houston": "Houston",
    "san francisco": "San Francisco",
    "hong kong": "Hong Kong",
    "shanghai": "Shanghai",
    "beijing": "Beijing",
    "singapore": "Singapore",
    "moscow": "Moscow",
    "istanbul": "Istanbul",
    "mexico city": "Mexico City",
    "buenos aires": "Buenos Aires",
    "sao paulo": "Sao Paulo",
    "ankara": "Ankara",
    "munich": "Munich",
    "madrid": "Madrid",
    "milan": "Milan",
    "warsaw": "Warsaw",
    "taipei": "Taipei",
    "tel aviv": "Tel Aviv",
    "lucknow": "Lucknow",
    "wellington": "Wellington",
    "chongqing": "Chongqing",
    "wuhan": "Wuhan",
    "chengdu": "Chengdu",
    "shenzhen": "Shenzhen",
    "guangzhou": "Guangzhou",
    "hangzhou": "Hangzhou",
    "nanjing": "Nanjing",
    "osaka": "Osaka",
    "bangkok": "Bangkok",
    "delhi": "Delhi",
    "mumbai": "Mumbai",
    "dubai": "Dubai",
    "cairo": "Cairo",
    "lagos": "Lagos",
    "nairobi": "Nairobi",
}

# 解析温度区间的正则
# "Will the highest temperature in New York City be between 68-69°F on April 5?"
# "Will the highest temperature in New York City be 67°F or below on April 5?"
# "Will the highest temperature in New York City be 86°F or higher on April 5?"

PATTERN_BETWEEN = re.compile(
    r"be between (\d+)-(\d+)°F on (\w+ \d+)", re.IGNORECASE
)
PATTERN_BELOW = re.compile(
    r"be (\d+)°F or below on (\w+ \d+)", re.IGNORECASE
)
PATTERN_ABOVE = re.compile(
    r"be (\d+)°F or higher on (\w+ \d+)", re.IGNORECASE
)
PATTERN_CITY = re.compile(
    r"temperature in (.+?) (?:be between|be \d|on )", re.IGNORECASE
)


def _parse_temp_market(market_data: dict, event_title: str) -> Optional[TempMarket]:
    """解析单个市场数据为 TempMarket"""
    question = market_data.get("question", "")

    # 解析价格
    prices_raw = market_data.get("outcomePrices", "[]")
    if isinstance(prices_raw, str):
        try:
            prices = json.loads(prices_raw)
        except json.JSONDecodeError:
            prices = []
    else:
        prices = prices_raw

    if not prices or len(prices) < 2:
        return None

    yes_price = round(float(prices[0]), 4)
    no_price = round(float(prices[1]), 4)

    # 解析 token IDs
    tokens_raw = market_data.get("clobTokenIds", "[]")
    if isinstance(tokens_raw, str):
        try:
            tokens = json.loads(tokens_raw)
        except json.JSONDecodeError:
            tokens = []
    else:
        tokens = tokens_raw

    if not tokens or len(tokens) < 2:
        return None

    # 解析温度区间
    temp_low = None
    temp_high = None
    label = ""

    match = PATTERN_BETWEEN.search(question)
    if match:
        temp_low = int(match.group(1))
        temp_high = int(match.group(2))
        label = f"{temp_low}-{temp_high}°F"
    else:
        match = PATTERN_BELOW.search(question)
        if match:
            temp_high = int(match.group(1))
            label = f"{temp_high}°F or below"
        else:
            match = PATTERN_ABOVE.search(question)
            if match:
                temp_low = int(match.group(1))
                label = f"{temp_low}°F or higher"

    if not label:
        return None

    # 解析城市名
    city = _extract_city(question)

    # 解析日期
    target_date = _extract_date(question)

    return TempMarket(
        question=question,
        city=city,
        target_date=target_date,
        temp_low_f=float(temp_low) if temp_low is not None else None,
        temp_high_f=float(temp_high) if temp_high is not None else None,
        label=label,
        yes_price=yes_price,
        no_price=no_price,
        yes_token_id=tokens[0],
        no_token_id=tokens[1],
        market_id=market_data.get("id", ""),
        condition_id=market_data.get("conditionId", ""),
        volume=float(market_data.get("volumeNum", 0) or 0),
        liquidity=float(market_data.get("liquidityNum", 0) or 0),
        best_bid=float(market_data.get("bestBid", 0) or 0),
        best_ask=float(market_data.get("bestAsk", 0) or 0),
    )


def _extract_city(question: str) -> str:
    """从问题中提取城市名"""
    # "Will the highest temperature in New York City be..."
    match = re.search(r"temperature in (.+?) be", question, re.IGNORECASE)
    if match:
        city_raw = match.group(1).strip().lower()
        return CITY_NAME_MAP.get(city_raw, city_raw.title())
    return "Unknown"


def _extract_date(question: str) -> str:
    """从问题中提取日期"""
    from datetime import datetime
    # "on April 5?" "on April 6?"
    match = re.search(r"on (\w+ \d+)\??$", question, re.IGNORECASE)
    if match:
        date_str = match.group(1)
        try:
            # 假设当前年份
            dt = datetime.strptime(f"{datetime.utcnow().year} {date_str}", "%Y %B %d")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return date_str
    return "Unknown"


def discover_weather_events(
    limit: int = 100,
    city_filter: list[str] = None,
    date_filter: str = None,
) -> list[CityWeatherEvent]:
    """
    发现 Polymarket 天气温度市场

    Args:
        limit: 最大获取事件数
        city_filter: 只返回指定城市（如 ["New York", "London"]）
        date_filter: 只返回指定日期 ("YYYY-MM-DD")

    Returns:
        CityWeatherEvent 列表
    """
    try:
        resp = requests.get(
            f"{GAMMA_API_URL}/events",
            params={
                "limit": limit,
                "tag_slug": "weather",
                "active": "true",
                "closed": "false",
            },
            timeout=30,
        )
        resp.raise_for_status()
        events = resp.json()

        logger.info(f"Gamma API 返回 {len(events)} 个天气事件")

    except Exception as e:
        logger.error(f"Gamma API 请求失败: {e}")
        return []

    results = []

    for event in events:
        title = event.get("title", "")

        # 只处理 "Highest temperature in XXX" 格式
        if "highest temperature" not in title.lower():
            continue

        # 解析所有子市场
        markets = []
        for m_data in event.get("markets", []):
            tm = _parse_temp_market(m_data, title)
            if tm:
                markets.append(tm)

        if not markets:
            continue

        # 取第一个市场的城市和日期
        city = markets[0].city
        target_date = markets[0].target_date

        # 过滤
        if city_filter and city not in city_filter:
            continue
        if date_filter and target_date != date_filter:
            continue

        cwe = CityWeatherEvent(
            title=title,
            city=city,
            target_date=target_date,
            volume=float(event.get("volume", 0) or 0),
            markets=markets,
        )
        results.append(cwe)

    logger.info(f"发现 {len(results)} 个日温度市场事件, "
                f"覆盖 {len(set(e.city for e in results))} 个城市")

    return results


def get_event_by_city_date(
    city_name: str,
    date_str: str,
) -> Optional[CityWeatherEvent]:
    """
    获取指定城市和日期的温度市场

    Args:
        city_name: 城市名（如 "New York"）
        date_str: 日期 "YYYY-MM-DD"

    Returns:
        CityWeatherEvent 或 None
    """
    events = discover_weather_events(
        city_filter=[city_name],
        date_filter=date_str,
    )
    return events[0] if events else None
