"""
交易执行引擎

通过 Polymarket CLOB API 执行交易。
模拟模式下只记录不实际下单。
"""

from datetime import datetime
from src.config.settings import TRADING_MODE
from src.utils.db import get_db
from src.utils.logger import setup_logger

logger = setup_logger("execution")


def execute_trade(
    signal,  # TradeSignal
    risk_result,  # RiskCheckResult
) -> dict:
    """
    执行一笔交易

    Args:
        signal: TradeSignal
        risk_result: 风控检查结果

    Returns:
        执行结果
    """
    if not risk_result.passed:
        logger.warning(f"交易被风控拦截: {risk_result.reason}")
        return {
            "status": "rejected",
            "reason": risk_result.reason,
            "signal": signal,
        }

    if TRADING_MODE == "SIMULATION":
        return _simulate_trade(signal)
    else:
        return _live_trade(signal)


def _simulate_trade(signal) -> dict:
    """
    模拟交易：记录但不实际下单
    """
    logger.info(
        f"[模拟] {signal.side} {signal.city} {signal.target_date} "
        f"{signal.label}: {signal.shares:.1f}股 @ ${signal.limit_price:.4f} "
        f"(投入 ${signal.cost_usd:.2f}, Edge={signal.edge:+.1%})"
    )

    # 写入数据库
    trade_id = _save_trade(
        city=signal.city,
        target_date=signal.target_date,
        temp_range=signal.label,
        side=signal.side,
        quantity=signal.shares,
        price=signal.limit_price,
        cost=signal.cost_usd,
        edge=signal.edge,
        model_prob=signal.model_prob,
        market_prob=signal.market_prob,
        token_id=signal.token_id,
        market_id=signal.market_id,
        status="simulated",
    )

    return {
        "status": "simulated",
        "trade_id": trade_id,
        "signal": signal,
        "message": (
            f"模拟买入 {signal.shares:.1f}股 {signal.label} "
            f"@ ${signal.limit_price:.4f} = ${signal.cost_usd:.2f}"
        ),
    }


def _live_trade(signal) -> dict:
    """
    实盘交易：通过 CLOB API 下单

    TODO: 需要配置钱包私钥和 API 认证后才能使用
    """
    logger.info(
        f"[实盘] {signal.side} {signal.city} {signal.target_date} "
        f"{signal.label}: {signal.shares:.1f}股 @ ${signal.limit_price:.4f}"
    )

    # TODO: 实现 py_clob_client 下单
    # from py_clob_client.client import ClobClient
    # client = ClobClient(...)
    # order = client.create_and_post_order(...)

    trade_id = _save_trade(
        city=signal.city,
        target_date=signal.target_date,
        temp_range=signal.label,
        side=signal.side,
        quantity=signal.shares,
        price=signal.limit_price,
        cost=signal.cost_usd,
        edge=signal.edge,
        model_prob=signal.model_prob,
        market_prob=signal.market_prob,
        token_id=signal.token_id,
        market_id=signal.market_id,
        status="open",
    )

    return {
        "status": "open",
        "trade_id": trade_id,
        "signal": signal,
    }


def _save_trade(
    city: str,
    target_date: str,
    temp_range: str,
    side: str,
    quantity: float,
    price: float,
    cost: float,
    edge: float,
    model_prob: float,
    market_prob: float,
    token_id: str,
    market_id: str,
    status: str = "open",
) -> int:
    """保存交易记录到数据库"""
    conn = get_db()
    try:
        cursor = conn.execute(
            """INSERT INTO trades
               (timestamp, market_id, token_id, city, date, temperature_range,
                side, quantity, price, cost, edge, kelly_fraction, model_prob,
                market_prob, status, created_at, updated_at)
               VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (
                market_id, token_id, city, target_date, temp_range,
                side, quantity, price, cost, edge, 0, model_prob,
                market_prob, status,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_open_positions() -> list[dict]:
    """获取当前所有未平仓仓位"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status IN ('open', 'simulated') ORDER BY timestamp DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def close_position(trade_id: int, pnl: float = 0, status: str = "settled"):
    """平仓"""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE trades SET status = ?, pnl = ?, updated_at = datetime('now') WHERE id = ?",
            (status, pnl, trade_id),
        )
        conn.commit()
        logger.info(f"平仓 #{trade_id}: PnL=${pnl:.2f}")
    finally:
        conn.close()


def get_trading_summary() -> dict:
    """获取交易汇总"""
    conn = get_db()
    try:
        # 总交易数
        total = conn.execute("SELECT COUNT(*) as c FROM trades").fetchone()["c"]
        # 未平仓
        open_count = conn.execute(
            "SELECT COUNT(*) as c FROM trades WHERE status IN ('open', 'simulated')"
        ).fetchone()["c"]
        # 已结算
        settled = conn.execute(
            "SELECT COUNT(*) as c FROM trades WHERE status = 'settled'"
        ).fetchone()["c"]
        # 总 PnL
        pnl_row = conn.execute(
            "SELECT SUM(pnl) as total_pnl FROM trades WHERE status = 'settled'"
        ).fetchone()
        total_pnl = float(pnl_row["total_pnl"] or 0)
        # 总投入
        cost_row = conn.execute(
            "SELECT SUM(cost) as total_cost FROM trades WHERE status IN ('open', 'simulated')"
        ).fetchone()
        open_cost = float(cost_row["total_cost"] or 0)

        return {
            "total_trades": total,
            "open_positions": open_count,
            "settled": settled,
            "total_pnl": round(total_pnl, 2),
            "open_exposure": round(open_cost, 2),
            "mode": TRADING_MODE,
        }
    finally:
        conn.close()
