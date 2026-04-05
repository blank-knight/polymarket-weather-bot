# 全局配置

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env
load_dotenv()

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ========== Polymarket ==========

# Polygon 链 ID
POLYGON_CHAIN_ID = 137

# CLOB API
CLOB_API_URL = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")

# Gamma API
GAMMA_API_URL = os.getenv("GAMMA_API_URL", "https://gamma-api.polymarket.com")

# WebSocket
CLOB_WS_URL = os.getenv("CLOB_WS_URL", "wss://ws-subscriptions-clob.polymarket.com/ws/market")

# 钱包私钥
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")

# 资金地址
FUNDER_ADDRESS = os.getenv("FUNDER_ADDRESS", "")

# ========== 天气 API ==========

# Open-Meteo
OPENMETEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPENMETEO_ENSEMBLE_URL = "https://api.open-meteo.com/v1/ensemble"
OPENMETEO_GFS_URL = "https://api.open-meteo.com/v1/gfs"
OPENMETEO_HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"

# ========== 模型权重 ==========

MODEL_WEIGHTS = {
    "ecmwf_ifs": 0.35,
    "gfs_seamless": 0.25,
    "ukmo_seamless": 0.20,
    "nws_seamless": 0.20,
}

# 离群值降权阈值（偏离共识超过此值时降权至 0.5x）
OUTLIER_SIGMA_THRESHOLD = 2.0
OUTLIER_PENALTY_FACTOR = 0.5

# 动态标准差（按预报时长）
FORECAST_SIGMA = {
    "6h": 0.8,
    "1d": 1.5,
    "3d": 2.5,
    "7d": 4.0,
    "10d": 5.5,
}

# ========== 交易参数 ==========

# 最小 Edge
MIN_EDGE = 0.05

# Kelly 缩放因子 (Quarter-Kelly)
KELLY_FRACTION = 0.25

# 单笔最大仓位占 bankroll 比例
MAX_POSITION_RATIO = 0.15

# 单笔最小金额 (USD)
MIN_TRADE_AMOUNT = 1.0

# ========== 风控 ==========

# 总敞口上限占 bankroll 比例
MAX_TOTAL_EXPOSURE = 0.50

# 日亏损上限占 bankroll 比例
MAX_DAILY_LOSS = 0.10

# 止损比例
STOP_LOSS_RATIO = -0.15

# 止盈：Edge 捕获比例
TAKE_PROFIT_EDGE_CAPTURE = 0.60

# 追踪止损回撤比例
TRAILING_STOP_PULLBACK = 0.40

# Edge 收敛退出阈值
EDGE_CONVERGENCE_EXIT = 0.02

# 结算前保护时间（小时）
SETTLEMENT_PROTECTION_HOURS = 2

# 最大 bid/ask spread
MAX_SPREAD = 0.05

# ========== 运行模式 ==========

# SIMULATION 模拟模式 / LIVE 实盘模式
TRADING_MODE = os.getenv("TRADING_MODE", "SIMULATION")

# 初始资金
INITIAL_BANKROLL = float(os.getenv("INITIAL_BANKROLL", "100"))

# ========== 数据库 ==========

DB_PATH = BASE_DIR / "data" / "weather_bot.db"

# ========== 日志 ==========

LOG_DIR = BASE_DIR / "logs"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
