# SQLite 数据库管理

import sqlite3
from pathlib import Path
from src.config.settings import DB_PATH
from src.utils.logger import setup_logger

logger = setup_logger("db")


# 建表 SQL
SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    city TEXT NOT NULL,
    date TEXT NOT NULL,
    temperature_range TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY_YES', 'BUY_NO', 'SELL')),
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    cost REAL NOT NULL,
    edge REAL,
    kelly_fraction REAL,
    model_prob REAL,
    market_prob REAL,
    status TEXT DEFAULT 'open' CHECK(status IN ('open', 'filled', 'partial', 'cancelled', 'settled', 'simulated')),
    pnl REAL,
    settlement_price REAL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    city TEXT NOT NULL,
    date TEXT NOT NULL,
    temperature_range TEXT NOT NULL,
    yes_price REAL,
    no_price REAL,
    bid_price REAL,
    ask_price REAL,
    spread REAL,
    volume_24h REAL,
    liquidity REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    city TEXT NOT NULL,
    date TEXT NOT NULL,
    temperature_range TEXT NOT NULL,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    side TEXT NOT NULL,
    model_prob REAL NOT NULL,
    market_prob REAL NOT NULL,
    edge REAL NOT NULL,
    kelly_size REAL,
    kelly_fraction REAL,
    confidence REAL,
    score REAL,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'executed', 'skipped', 'expired')),
    skip_reason TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    city TEXT NOT NULL,
    target_date TEXT NOT NULL,
    model TEXT NOT NULL,
    forecast_temp_f REAL,
    forecast_temp_c REAL,
    sigma REAL,
    probability_json TEXT,
    raw_response TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bankroll (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    balance REAL NOT NULL,
    initial_balance REAL NOT NULL,
    total_pnl REAL DEFAULT 0,
    daily_pnl REAL DEFAULT 0,
    open_exposure REAL DEFAULT 0,
    trade_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_trades_city ON trades(city);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_city ON signals(city);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
CREATE INDEX IF NOT EXISTS idx_forecasts_city ON forecasts(city);
CREATE INDEX IF NOT EXISTS idx_forecasts_target ON forecasts(target_date);
CREATE INDEX IF NOT EXISTS idx_snapshots_city ON market_snapshots(city);
"""


def get_db() -> sqlite3.Connection:
    """获取数据库连接"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库（创建所有表）"""
    conn = get_db()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        logger.info(f"数据库初始化完成: {DB_PATH}")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise
    finally:
        conn.close()


def get_bankroll() -> dict:
    """获取最新 bankroll 状态"""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM bankroll ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def update_bankroll(balance: float, daily_pnl: float = 0, open_exposure: float = 0, trade_count: int = 0):
    """更新 bankroll 记录"""
    conn = get_db()
    try:
        # 获取上一次记录
        last = get_bankroll()
        initial = last["initial_balance"] if last else balance
        total_pnl = balance - initial

        conn.execute(
            """INSERT INTO bankroll (timestamp, balance, initial_balance, total_pnl, daily_pnl, open_exposure, trade_count)
               VALUES (datetime('now'), ?, ?, ?, ?, ?, ?)""",
            (balance, initial, total_pnl, daily_pnl, open_exposure, trade_count),
        )
        conn.commit()
    finally:
        conn.close()
