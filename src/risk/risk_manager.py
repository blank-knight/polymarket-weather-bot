"""
风控模块

所有交易前必须通过风控检查。
"""

from dataclasses import dataclass
from datetime import datetime

from src.config.settings import (
    MAX_POSITION_RATIO,
    MAX_TOTAL_EXPOSURE,
    MAX_DAILY_LOSS,
    STOP_LOSS_RATIO,
    SETTLEMENT_PROTECTION_HOURS,
    MAX_SPREAD,
    TRADING_MODE,
)
from src.utils.db import get_db, get_bankroll
from src.utils.logger import setup_logger

logger = setup_logger("risk_manager")


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    passed: bool
    reason: str = ""
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


def check_trading_mode() -> RiskCheckResult:
    """检查运行模式"""
    if TRADING_MODE == "SIMULATION":
        return RiskCheckResult(
            passed=True,
            reason="模拟模式，允许所有操作",
            details={"mode": "SIMULATION"},
        )
    return RiskCheckResult(passed=True, details={"mode": TRADING_MODE})


def check_position_limit(
    position_usd: float,
    bankroll: float,
) -> RiskCheckResult:
    """
    检查单笔仓位限制

    单笔不超过 bankroll 的 15%
    """
    if bankroll <= 0:
        return RiskCheckResult(False, "bankroll 为 0", {"position_usd": position_usd, "bankroll": bankroll})

    ratio = position_usd / bankroll
    if ratio > MAX_POSITION_RATIO:
        return RiskCheckResult(
            False,
            f"单笔仓位 {ratio:.1%} 超过上限 {MAX_POSITION_RATIO:.1%}",
            {"position_usd": position_usd, "bankroll": bankroll, "ratio": ratio},
        )
    return RiskCheckResult(True, details={"ratio": round(ratio, 4)})


def check_total_exposure(
    new_position_usd: float,
    bankroll: float,
) -> RiskCheckResult:
    """
    检查总敞口限制

    总敞口不超过 bankroll 的 50%
    """
    # 获取当前总敞口
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT SUM(cost) as total_open FROM trades WHERE status = 'open'"
        ).fetchone()
        current_exposure = float(row["total_open"] or 0)
    finally:
        conn.close()

    total = current_exposure + new_position_usd
    ratio = total / bankroll if bankroll > 0 else 1

    if ratio > MAX_TOTAL_EXPOSURE:
        return RiskCheckResult(
            False,
            f"总敞口 ${total:.2f} ({ratio:.1%}) 超过上限 {MAX_TOTAL_EXPOSURE:.1%}",
            {"current_exposure": current_exposure, "new": new_position_usd, "total": total, "ratio": ratio},
        )
    return RiskCheckResult(True, details={"total_exposure": round(total, 2), "ratio": round(ratio, 4)})


def check_daily_loss(bankroll: float) -> RiskCheckResult:
    """
    检查日亏损限制

    今日亏损不超过 bankroll 的 10%
    """
    conn = get_db()
    try:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT SUM(pnl) as daily_pnl FROM trades "
            "WHERE status = 'settled' AND DATE(updated_at) = ?",
            (today,),
        ).fetchone()
        daily_pnl = float(row["daily_pnl"] or 0)
    finally:
        conn.close()

    if daily_pnl < 0 and abs(daily_pnl) > bankroll * MAX_DAILY_LOSS:
        return RiskCheckResult(
            False,
            f"今日亏损 ${abs(daily_pnl):.2f} 超过日限 {bankroll * MAX_DAILY_LOSS:.2f}",
            {"daily_pnl": daily_pnl, "limit": bankroll * MAX_DAILY_LOSS},
        )
    return RiskCheckResult(True, details={"daily_pnl": daily_pnl})


def check_spread(spread: float) -> RiskCheckResult:
    """检查 spread 是否可接受"""
    if spread > MAX_SPREAD:
        return RiskCheckResult(
            False,
            f"Spread {spread:.4f} 超过上限 {MAX_SPREAD}",
            {"spread": spread},
        )
    return RiskCheckResult(True, details={"spread": spread})


def check_settlement_time(hours_to_settlement: float) -> RiskCheckResult:
    """检查距结算时间"""
    if hours_to_settlement < SETTLEMENT_PROTECTION_HOURS:
        return RiskCheckResult(
            False,
            f"距结算 {hours_to_settlement:.1f}h < 保护期 {SETTLEMENT_PROTECTION_HOURS}h",
            {"hours_to_settlement": hours_to_settlement},
        )
    return RiskCheckResult(True, details={"hours_to_settlement": hours_to_settlement})


def check_min_liquidity(best_bid: float, best_ask: float) -> RiskCheckResult:
    """检查最低流动性（bid 和 ask 都存在且合理）"""
    if best_bid <= 0 and best_ask <= 0:
        return RiskCheckResult(False, "无流动性（bid=0, ask=0）")
    if best_ask > 0 and best_bid > 0 and (best_ask - best_bid) > MAX_SPREAD:
        return RiskCheckResult(False, f"流动性不足，spread={best_ask - best_bid:.4f}")
    return RiskCheckResult(True)


def run_all_checks(
    position_usd: float,
    bankroll: float,
    spread: float = 0,
    best_bid: float = 0,
    best_ask: float = 0,
    hours_to_settlement: float = 24,
) -> RiskCheckResult:
    """
    运行所有风控检查

    Returns:
        RiskCheckResult (全部通过才返回 passed=True)
    """
    checks = [
        ("trading_mode", check_trading_mode()),
        ("position_limit", check_position_limit(position_usd, bankroll)),
        ("total_exposure", check_total_exposure(position_usd, bankroll)),
        ("daily_loss", check_daily_loss(bankroll)),
        ("spread", check_spread(spread) if spread > 0 else RiskCheckResult(True)),
        ("settlement", check_settlement_time(hours_to_settlement)),
        ("liquidity", check_min_liquidity(best_bid, best_ask)),
    ]

    for name, result in checks:
        if not result.passed:
            logger.warning(f"风控拦截 [{name}]: {result.reason}")
            return RiskCheckResult(False, f"[{name}] {result.reason}", result.details)

    logger.info("风控检查全部通过")
    return RiskCheckResult(True, "全部通过")
