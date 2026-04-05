"""
历史温度数据管理

从 Open-Meteo 获取历史同日温度，缓存到 SQLite。
"""

import json
from datetime import datetime

from src.weather.open_meteo_client import get_historical_temperature
from src.utils.db import get_db
from src.utils.logger import setup_logger

logger = setup_logger("historical")


def get_cached_historical(city_name: str, date_mmdd: str) -> list[float] | None:
    """
    从缓存获取历史温度数据

    Args:
        city_name: 城市名
        date_mmdd: "MM-DD"

    Returns:
        历史最高温列表（°F）或 None
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT probability_json FROM forecasts "
            "WHERE city = ? AND target_date LIKE ? AND model = 'historical' "
            "ORDER BY timestamp DESC LIMIT 1",
            (city_name, f"%-{date_mmdd}"),
        ).fetchone()

        if row:
            data = json.loads(row["probability_json"])
            temps = data.get("historical_highs_f", [])
            if temps:
                logger.info(f"[{city_name}] 历史缓存命中: {len(temps)} 年")
                return temps
        return None
    finally:
        conn.close()


def save_historical_cache(city_name: str, date_mmdd: str, temps_f: list[float]):
    """保存历史温度到缓存"""
    conn = get_db()
    try:
        year = datetime.utcnow().year
        conn.execute(
            "INSERT INTO forecasts (timestamp, city, target_date, model, probability_json, raw_response) "
            "VALUES (datetime('now'), ?, ?, 'historical', ?, '')",
            (
                city_name,
                f"{year}-{date_mmdd}",
                json.dumps({"historical_highs_f": temps_f}),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_historical_base_rates(
    city,
    target_date: str,
    buckets: list,
    years_back: int = 10,
    use_cache: bool = True,
) -> dict[str, float]:
    """
    获取历史同日各温度区间的基准概率

    Args:
        city: City 对象
        target_date: "YYYY-MM-DD"
        buckets: TemperatureBucket 列表
        years_back: 回溯年数
        use_cache: 是否使用缓存

    Returns:
        {"50-55°F": 0.12, "55-60°F": 0.35, ...}
    """
    date_mmdd = target_date[5:]  # "04-06"

    # 尝试缓存
    if use_cache:
        cached = get_cached_historical(city.name, date_mmdd)
        if cached:
            temps_f = cached
        else:
            temps_f = get_historical_temperature(city, target_date, years_back)
            if temps_f:
                save_historical_cache(city.name, date_mmdd, temps_f)
    else:
        temps_f = get_historical_temperature(city, target_date, years_back)
        if temps_f:
            save_historical_cache(city.name, date_mmdd, temps_f)

    if not temps_f:
        logger.warning(f"[{city.name}] 无历史数据，返回均匀分布")
        n = len(buckets)
        return {b.label: round(1.0 / n, 4) for b in buckets} if n > 0 else {}

    # 统计各区间频率
    result = {}
    for bucket in buckets:
        count = sum(1 for t in temps_f if bucket.low_f <= t < bucket.high_f)
        result[bucket.label] = round(count / len(temps_f), 4)

    logger.info(f"[{city.name}] 历史基准概率 ({len(temps_f)} 年, {date_mmdd}):")
    for label, prob in result.items():
        if prob > 0:
            logger.info(f"  {label}: {prob:.0%}")

    return result
