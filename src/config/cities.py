# 目标城市配置

from dataclasses import dataclass


@dataclass
class City:
    """目标城市"""
    name: str           # 城市英文名（用于匹配 Polymarket 市场）
    display_name: str   # 显示名
    latitude: float     # 纬度
    longitude: float    # 经度
    timezone: str       # 时区
    country: str        # 国家
    priority: int       # 优先级 0=最高, 1=高, 2=中, 3=低


# 按优先级排序的目标城市列表
CITIES = [
    # P0: Polymarket 上流动性最高的城市
    City(
        name="New York",
        display_name="纽约",
        latitude=40.7128,
        longitude=-74.0060,
        timezone="America/New_York",
        country="US",
        priority=0,
    ),
    City(
        name="London",
        display_name="伦敦",
        latitude=51.5074,
        longitude=-0.1278,
        timezone="Europe/London",
        country="GB",
        priority=0,
    ),
    City(
        name="Chicago",
        display_name="芝加哥",
        latitude=41.8781,
        longitude=-87.6298,
        timezone="America/Chicago",
        country="US",
        priority=0,
    ),
    # P1: 流动性好，经常有市场
    City(
        name="Paris",
        display_name="巴黎",
        latitude=48.8566,
        longitude=2.3522,
        timezone="Europe/Paris",
        country="FR",
        priority=1,
    ),
    City(
        name="Los Angeles",
        display_name="洛杉矶",
        latitude=34.0522,
        longitude=-118.2437,
        timezone="America/Los_Angeles",
        country="US",
        priority=1,
    ),
    City(
        name="Miami",
        display_name="迈阿密",
        latitude=25.7617,
        longitude=-80.1918,
        timezone="America/New_York",
        country="US",
        priority=1,
    ),
    City(
        name="Dallas",
        display_name="达拉斯",
        latitude=32.7767,
        longitude=-96.7970,
        timezone="America/Chicago",
        country="US",
        priority=1,
    ),
    City(
        name="Atlanta",
        display_name="亚特兰大",
        latitude=33.7490,
        longitude=-84.3880,
        timezone="America/New_York",
        country="US",
        priority=1,
    ),
    City(
        name="Seattle",
        display_name="西雅图",
        latitude=47.6062,
        longitude=-122.3321,
        timezone="America/Los_Angeles",
        country="US",
        priority=1,
    ),
    City(
        name="Toronto",
        display_name="多伦多",
        latitude=43.6532,
        longitude=-79.3832,
        timezone="America/New_York",
        country="CA",
        priority=1,
    ),
    City(
        name="Sao Paulo",
        display_name="圣保罗",
        latitude=-23.5505,
        longitude=-46.6333,
        timezone="America/Sao_Paulo",
        country="BR",
        priority=1,
    ),
    City(
        name="Buenos Aires",
        display_name="布宜诺斯艾利斯",
        latitude=-34.6037,
        longitude=-58.3816,
        timezone="America/Argentina/Buenos_Aires",
        country="AR",
        priority=1,
    ),
    # P2: 时区覆盖
    City(
        name="Seoul",
        display_name="首尔",
        latitude=37.5665,
        longitude=126.9780,
        timezone="Asia/Seoul",
        country="KR",
        priority=2,
    ),
    City(
        name="Tokyo",
        display_name="东京",
        latitude=35.6762,
        longitude=139.6503,
        timezone="Asia/Tokyo",
        country="JP",
        priority=2,
    ),
    City(
        name="Sydney",
        display_name="悉尼",
        latitude=-33.8688,
        longitude=151.2093,
        timezone="Australia/Sydney",
        country="AU",
        priority=2,
    ),
    City(
        name="Hong Kong",
        display_name="香港",
        latitude=22.3193,
        longitude=114.1694,
        timezone="Asia/Hong_Kong",
        country="HK",
        priority=2,
    ),
    City(
        name="Singapore",
        display_name="新加坡",
        latitude=1.3521,
        longitude=103.8198,
        timezone="Asia/Singapore",
        country="SG",
        priority=2,
    ),
    City(
        name="Shanghai",
        display_name="上海",
        latitude=31.2304,
        longitude=121.4737,
        timezone="Asia/Shanghai",
        country="CN",
        priority=2,
    ),
    City(
        name="Beijing",
        display_name="北京",
        latitude=39.9042,
        longitude=116.4074,
        timezone="Asia/Shanghai",
        country="CN",
        priority=2,
    ),
    # P3: Polymarket 上偶尔有市场
    City(
        name="Austin",
        display_name="奥斯汀",
        latitude=30.2672,
        longitude=-97.7431,
        timezone="America/Chicago",
        country="US",
        priority=3,
    ),
    City(
        name="Denver",
        display_name="丹佛",
        latitude=39.7392,
        longitude=-104.9903,
        timezone="America/Denver",
        country="US",
        priority=3,
    ),
    City(
        name="Houston",
        display_name="休斯顿",
        latitude=29.7604,
        longitude=-95.3698,
        timezone="America/Chicago",
        country="US",
        priority=3,
    ),
    City(
        name="San Francisco",
        display_name="旧金山",
        latitude=37.7749,
        longitude=-122.4194,
        timezone="America/Los_Angeles",
        country="US",
        priority=3,
    ),
    City(
        name="Mexico City",
        display_name="墨西哥城",
        latitude=19.4326,
        longitude=-99.1332,
        timezone="America/Mexico_City",
        country="MX",
        priority=3,
    ),
    City(
        name="Moscow",
        display_name="莫斯科",
        latitude=55.7558,
        longitude=37.6173,
        timezone="Europe/Moscow",
        country="RU",
        priority=3,
    ),
    City(
        name="Istanbul",
        display_name="伊斯坦布尔",
        latitude=41.0082,
        longitude=28.9784,
        timezone="Europe/Istanbul",
        country="TR",
        priority=3,
    ),
]


def get_cities_by_priority(priority: int = None) -> list[City]:
    """按优先级获取城市列表"""
    if priority is None:
        return sorted(CITIES, key=lambda c: c.priority)
    return [c for c in CITIES if c.priority <= priority]


def get_city_by_name(name: str) -> City | None:
    """按名称查找城市"""
    name_lower = name.lower()
    for city in CITIES:
        if name_lower in city.name.lower() or name_lower in city.display_name:
            return city
    return None
