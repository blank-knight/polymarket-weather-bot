"""
Open-Meteo API 客户端

获取多模型天气预报数据：
- GFS 31成员集合预报
- ECMWF IFS
- UKMO
- NWS
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import requests
from src.config.settings import (
    OPENMETEO_FORECAST_URL,
    OPENMETEO_ENSEMBLE_URL,
    OPENMETEO_GFS_URL,
    OPENMETEO_HISTORICAL_URL,
)
from src.config.cities import City
from src.utils.logger import setup_logger

logger = setup_logger("weather_api")


@dataclass
class ForecastResult:
    """单个模型的预报结果"""
    city: str
    model: str
    target_date: str           # YYYY-MM-DD
    temp_high_c: float         # 当日最高温 (°C)
    temp_high_f: float         # 当日最高温 (°F)
    temp_low_c: float          # 当日最低温 (°C)
    hourly_temps_c: list[float]  # 逐时温度 (°C)
    fetched_at: str            # 获取时间


@dataclass
class EnsembleResult:
    """GFS 集合预报结果（31个成员）"""
    city: str
    target_date: str
    members_high_c: list[float]  # 31个成员各自的最高温
    mean_high_c: float           # 平均最高温
    std_high_c: float            # 标准差
    fetched_at: str


def _c_to_f(celsius: float) -> float:
    """摄氏转华氏"""
    return celsius * 9.0 / 5.0 + 32.0


def _f_to_c(fahrenheit: float) -> float:
    """华氏转摄氏"""
    return (fahrenheit - 32.0) * 5.0 / 9.0


def get_forecast(
    city: City,
    models: list[str] = None,
    forecast_days: int = 3,
) -> list[ForecastResult]:
    """
    获取单模型预报（非集合）

    Args:
        city: 目标城市
        models: 模型列表，默认 ["gfs_seamless", "ecmwf_ifs025", "ukmo_seamless"]
        forecast_days: 预报天数（1-16）

    Returns:
        每个模型每天一个 ForecastResult
    """
    if models is None:
        models = ["gfs_seamless", "ecmwf_ifs025", "ukmo_seamless"]

    results = []

    for model in models:
        try:
            params = {
                "latitude": city.latitude,
                "longitude": city.longitude,
                "hourly": "temperature_2m",
                "models": model,
                "forecast_days": forecast_days,
                "timezone": city.timezone,
            }

            resp = requests.get(OPENMETEO_FORECAST_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # Open-Meteo 返回结构: {"hourly": {"time": [...], "temperature_2m": [...]}}
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])

            if not times or not temps:
                logger.warning(f"[{city.name}] {model}: 无数据返回")
                continue

            # 按天分组
            daily_groups = {}
            for t, temp in zip(times, temps):
                if temp is None:
                    continue
                date_str = t[:10]  # "2026-04-06"
                daily_groups.setdefault(date_str, []).append(temp)

            for date_str, day_temps in sorted(daily_groups.items()):
                high_c = max(day_temps)
                low_c = min(day_temps)
                results.append(ForecastResult(
                    city=city.name,
                    model=model,
                    target_date=date_str,
                    temp_high_c=round(high_c, 2),
                    temp_high_f=round(_c_to_f(high_c), 2),
                    temp_low_c=round(low_c, 2),
                    hourly_temps_c=[round(t, 2) for t in day_temps],
                    fetched_at=datetime.utcnow().isoformat(),
                ))

            logger.info(f"[{city.name}] {model}: 获取 {len(daily_groups)} 天预报成功")

        except Exception as e:
            logger.error(f"[{city.name}] {model}: 获取预报失败 - {e}")

    return results


def get_ensemble_forecast(
    city: City,
    forecast_days: int = 3,
) -> list[EnsembleResult]:
    """
    获取 GFS 集合预报（31个成员）

    Args:
        city: 目标城市
        forecast_days: 预报天数

    Returns:
        每天一个 EnsembleResult
    """
    try:
        params = {
            "latitude": city.latitude,
            "longitude": city.longitude,
            "hourly": "temperature_2m",
            "models": "gfs_seamless",
            "ensemble": "true",
            "forecast_days": forecast_days,
            "timezone": city.timezone,
        }

        resp = requests.get(OPENMETEO_ENSEMBLE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        # 集合预报返回多个成员的数据
        # 结构可能是: {"hourly": {"time": [...], "temperature_2m": [[member1...], [member2...], ...]}}
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps_data = hourly.get("temperature_2m", [])

        if not times:
            logger.warning(f"[{city.name}] ensemble: 无数据返回")
            return []

        import numpy as np

        results = []

        # 判断是否为集合数据（嵌套列表）
        if temps_data and isinstance(temps_data[0], list):
            # 多成员集合数据
            # temps_data: [[member0_hour0, member0_hour1, ...], [member1_hour0, ...], ...]
            # 需要转置为: [[hour0_member0, hour0_member1, ...], ...]
            # 但 Open-Meteo ensemble 格式可能是按成员分组的
            members_count = len(temps_data)
            logger.info(f"[{city.name}] ensemble: 收到 {members_count} 个成员数据")

            # 按天分组每个成员
            daily_member_highs = {}
            for member_idx, member_temps in enumerate(temps_data):
                for t_idx, temp in enumerate(member_temps):
                    if temp is None:
                        continue
                    date_str = times[t_idx][:10]
                    daily_member_highs.setdefault(date_str, []).append(temp)

            for date_str in sorted(daily_member_highs.keys()):
                # 这里简化处理：取所有成员在该天的最高温
                # 实际应该按成员分组后取每个成员的最高温
                all_temps = daily_member_highs[date_str]
                # 按小时数分组成员（24小时一个成员）
                hours_per_member = 24
                member_highs = []
                for i in range(0, len(all_temps), hours_per_member):
                    member_day = all_temps[i:i + hours_per_member]
                    if member_day:
                        member_highs.append(max(member_day))

                if member_highs:
                    results.append(EnsembleResult(
                        city=city.name,
                        target_date=date_str,
                        members_high_c=[round(t, 2) for t in member_highs],
                        mean_high_c=round(float(np.mean(member_highs)), 2),
                        std_high_c=round(float(np.std(member_highs)), 2),
                        fetched_at=datetime.utcnow().isoformat(),
                    ))
        else:
            # 单一数据，尝试用标准格式处理
            logger.warning(f"[{city.name}] ensemble: 未收到集合数据，可能 API 不支持")

        logger.info(f"[{city.name}] ensemble: 获取 {len(results)} 天集合预报")
        return results

    except Exception as e:
        logger.error(f"[{city.name}] ensemble: 获取失败 - {e}")
        return []


def get_gfs_forecast(
    city: City,
    forecast_days: int = 3,
) -> list[ForecastResult]:
    """
    使用 GFS 专用端点获取预报
    """
    try:
        params = {
            "latitude": city.latitude,
            "longitude": city.longitude,
            "hourly": "temperature_2m",
            "forecast_days": forecast_days,
            "timezone": city.timezone,
        }

        resp = requests.get(OPENMETEO_GFS_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])

        if not times:
            return []

        results = []
        daily_groups = {}
        for t, temp in zip(times, temps):
            if temp is None:
                continue
            date_str = t[:10]
            daily_groups.setdefault(date_str, []).append(temp)

        for date_str, day_temps in sorted(daily_groups.items()):
            high_c = max(day_temps)
            results.append(ForecastResult(
                city=city.name,
                model="gfs",
                target_date=date_str,
                temp_high_c=round(high_c, 2),
                temp_high_f=round(_c_to_f(high_c), 2),
                temp_low_c=round(min(day_temps), 2),
                hourly_temps_c=[round(t, 2) for t in day_temps],
                fetched_at=datetime.utcnow().isoformat(),
            ))

        logger.info(f"[{city.name}] GFS: 获取 {len(results)} 天预报")
        return results

    except Exception as e:
        logger.error(f"[{city.name}] GFS: 获取失败 - {e}")
        return []


def get_historical_temperature(
    city: City,
    target_date: str,
    years_back: int = 10,
) -> list[float]:
    """
    获取历史同日最高温度（°F），用于贝叶斯融合基准

    Args:
        city: 目标城市
        target_date: 目标日期 "MM-DD"
        years_back: 回溯年数

    Returns:
        历年同日最高温列表（°F）
    """
    month_day = target_date[5:]  # "04-06"
    current_year = datetime.utcnow().year
    historical_highs_f = []

    for year_offset in range(1, years_back + 1):
        year = current_year - year_offset
        date_str = f"{year}-{month_day}"

        try:
            params = {
                "latitude": city.latitude,
                "longitude": city.longitude,
                "start_date": date_str,
                "end_date": date_str,
                "daily": "temperature_2m_max",
                "timezone": city.timezone,
            }

            resp = requests.get(OPENMETEO_HISTORICAL_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            daily = data.get("daily", {})
            max_temps = daily.get("temperature_2m_max", [])

            for t in max_temps:
                if t is not None:
                    historical_highs_f.append(round(_c_to_f(t), 2))

        except Exception as e:
            logger.debug(f"[{city.name}] 历史 {date_str}: {e}")
            continue

    logger.info(f"[{city.name}] 获取 {len(historical_highs_f)} 年历史数据 ({month_day})")
    return historical_highs_f
