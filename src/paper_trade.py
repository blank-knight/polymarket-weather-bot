"""
Step 12: 模拟交易报告生成器

Paper Trading 模式：
1. 获取当前真实市场数据
2. 获取真实天气预报
3. 模拟下单（不花真钱）
4. 生成交易报告
5. 统计命中率、模拟盈亏、最大回撤
"""

import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from src.config.settings import INITIAL_BANKROLL
from src.config.cities import get_cities_by_priority
from src.decision.signal_generator import generate_all_signals
from src.risk.risk_manager import run_all_checks
from src.execution.trader import execute_trade, get_trading_summary
from src.utils.db import init_db, update_bankroll, get_db
from src.utils.logger import setup_logger

logger = setup_logger("paper_trade")


@dataclass
class SimulationReport:
    """模拟交易报告"""
    start_time: str
    end_time: str
    bankroll_start: float
    bankroll_end: float
    total_signals: int
    total_trades: int
    total_rejected: int
    total_cost: float
    total_pnl: float
    roi: float
    win_count: int = 0
    loss_count: int = 0
    pending_count: int = 0
    trades: list[dict] = field(default_factory=list)


def run_paper_trading_session(
    bankroll: float = None,
    city_names: list[str] = None,
    days_ahead: int = 2,
) -> SimulationReport:
    """
    执行一次模拟交易会话

    Args:
        bankroll: 模拟资金
        city_names: 目标城市
        days_ahead: 扫描天数

    Returns:
        SimulationReport
    """
    start_time = datetime.utcnow().isoformat()

    if bankroll is None:
        bankroll = INITIAL_BANKROLL

    if city_names is None:
        cities = get_cities_by_priority(priority=1)
        city_names = [c.name for c in cities]

    logger.info(f"📊 模拟交易会话开始")
    logger.info(f"  资金: ${bankroll:.2f}")
    logger.info(f"  城市: {city_names}")
    logger.info(f"  天数: {days_ahead}")

    # 生成信号
    try:
        signals = generate_all_signals(
            bankroll=bankroll,
            city_names=city_names,
            days_ahead=days_ahead,
        )
    except Exception as e:
        logger.error(f"信号生成失败: {e}")
        signals = []

    total_signals = len(signals)
    executed_trades = []
    rejected = 0
    total_cost = 0

    for signal in signals:
        # 估算距结算时间
        try:
            target_dt = datetime.strptime(signal.target_date, "%Y-%m-%d")
            hours_to_settlement = max(0, (target_dt - datetime.utcnow()).total_seconds() / 3600)
        except ValueError:
            hours_to_settlement = 24

        # 风控
        risk = run_all_checks(
            position_usd=signal.cost_usd,
            bankroll=bankroll,
            spread=signal.limit_price,
            best_bid=signal.limit_price * 0.99,
            best_ask=signal.limit_price * 1.01,
            hours_to_settlement=hours_to_settlement,
        )

        # 执行
        from src.risk.risk_manager import RiskCheckResult
        result = execute_trade(signal, risk)

        if result["status"] in ("simulated", "open"):
            total_cost += signal.cost_usd
            executed_trades.append({
                "trade_id": result.get("trade_id", 0),
                "city": signal.city,
                "date": signal.target_date,
                "range": signal.label,
                "side": signal.side,
                "shares": signal.shares,
                "price": signal.limit_price,
                "cost": signal.cost_usd,
                "edge": signal.edge,
                "model_prob": signal.model_prob,
                "confidence": signal.confidence,
            })
        else:
            rejected += 1

    # 获取汇总
    summary = get_trading_summary()

    end_time = datetime.utcnow().isoformat()

    report = SimulationReport(
        start_time=start_time,
        end_time=end_time,
        bankroll_start=bankroll,
        bankroll_end=bankroll - total_cost,  # 暂时
        total_signals=total_signals,
        total_trades=len(executed_trades),
        total_rejected=rejected,
        total_cost=total_cost,
        total_pnl=summary["total_pnl"],
        roi=0,
        trades=executed_trades,
    )

    return report


def print_report(report: SimulationReport):
    """打印模拟交易报告"""
    print("\n" + "=" * 60)
    print("📊 Polymarket 天气交易 Bot — 模拟交易报告")
    print("=" * 60)

    print(f"\n⏱️  时间: {report.start_time[:19]} → {report.end_time[:19]}")
    print(f"💰 资金: ${report.bankroll_start:.2f} → ${report.bankroll_end:.2f}")
    print(f"📈 投入: ${report.total_cost:.2f}")

    print(f"\n📋 信号统计:")
    print(f"  总信号数: {report.total_signals}")
    print(f"  已执行:   {report.total_trades}")
    print(f"  被拦截:   {report.total_rejected}")

    if report.trades:
        print(f"\n{'城市':<12} {'日期':<12} {'区间':<15} {'方向':<8} "
              f"{'股数':>6} {'价格':>6} {'投入':>7} {'Edge':>7}")
        print("-" * 85)
        for t in report.trades:
            print(f"  {t['city']:<12} {t['date']:<12} {t['range']:<15} "
                  f"{t['side']:<8} {t['shares']:>6.1f} ${t['price']:>5.3f} "
                  f"${t['cost']:>6.2f} {t['edge']:>+6.1%}")
    else:
        print("\n  无交易执行")

    print(f"\n" + "=" * 60)

    if report.total_trades == 0:
        print("📝 本轮无交易。可能原因:")
        print("  1. 市场流动性不足（spread太宽）")
        print("  2. 模型概率和市场价格偏差太小（Edge < 5%）")
        print("  3. 市场价格极端（$0.001 或 $0.999）")
        print("  💡 等 GFS/ECMWF 模型更新后（每6小时），价格波动会产生机会")
    else:
        print(f"✅ 已执行 {report.total_trades} 笔模拟交易")

    print("=" * 60)


def save_report(report: SimulationReport, filepath: str = "data/paper_trade_report.json"):
    """保存报告到 JSON"""
    report_dict = {
        "start_time": report.start_time,
        "end_time": report.end_time,
        "bankroll_start": report.bankroll_start,
        "bankroll_end": report.bankroll_end,
        "total_signals": report.total_signals,
        "total_trades": report.total_trades,
        "total_rejected": report.total_rejected,
        "total_cost": report.total_cost,
        "total_pnl": report.total_pnl,
        "trades": report.trades,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2, ensure_ascii=False)

    logger.info(f"报告已保存到 {filepath}")


if __name__ == "__main__":
    init_db()
    update_bankroll(INITIAL_BANKROLL)

    report = run_paper_trading_session()
    print_report(report)
    save_report(report)
