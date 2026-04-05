"""
Kelly Criterion 仓位计算

使用 Quarter-Kelly（保守）策略确定每次下注大小。
"""

from src.config.settings import KELLY_FRACTION, MAX_POSITION_RATIO, MIN_TRADE_AMOUNT
from src.utils.logger import setup_logger

logger = setup_logger("kelly")


def kelly_fraction(
    prob: float,
    price: float,
    fraction: float = KELLY_FRACTION,
) -> float:
    """
    计算 Kelly 仓位比例

    f* = (p * b - q) / b
    其中:
      p = 模型概率
      b = 赔率 = (1 - price) / price  (花 price 买 YES，赢了得 $1)
      q = 1 - p

    然后乘以 fraction（Quarter-Kelly = 0.25）

    Args:
        prob: 模型概率
        price: 市场价格
        fraction: Kelly 缩放因子（默认 Quarter-Kelly = 0.25）

    Returns:
        建议投入的 bankroll 比例 [0, 1]
    """
    if price <= 0 or price >= 1:
        return 0

    q = 1 - prob
    b = (1 - price) / price  # 赔率

    f_star = (prob * b - q) / b

    # 如果 f* < 0，说明没有正 EV，不下注
    if f_star <= 0:
        return 0

    # 应用缩放因子
    f = f_star * fraction

    # 上限
    f = min(f, MAX_POSITION_RATIO)

    return round(f, 4)


def calculate_position_size(
    prob: float,
    price: float,
    bankroll: float,
    fraction: float = KELLY_FRACTION,
) -> dict:
    """
    计算具体仓位大小

    Args:
        prob: 模型概率
        price: 市场价格
        bankroll: 当前资金
        fraction: Kelly 缩放因子

    Returns:
        {
            "kelly_raw": 原始 Kelly,
            "kelly_scaled": 缩放后 Kelly,
            "position_ratio": 最终比例,
            "position_usd": 投入金额,
            "shares": 可买股数,
            "cost_per_share": 每股成本,
            "expected_value": 每股期望收益,
        }
    """
    if bankroll <= 0:
        return _zero_result()

    # 原始 Kelly
    q = 1 - prob
    b = (1 - price) / price if 0 < price < 1 else 0

    if b <= 0:
        return _zero_result()

    kelly_raw = (prob * b - q) / b
    if kelly_raw <= 0:
        return _zero_result()

    # Quarter-Kelly
    kelly_scaled = kelly_raw * fraction

    # 上限
    position_ratio = min(kelly_scaled, MAX_POSITION_RATIO)

    # 金额
    position_usd = bankroll * position_ratio
    if position_usd < MIN_TRADE_AMOUNT:
        return _zero_result()

    # 股数
    shares = position_usd / price if price > 0 else 0

    # 期望收益
    ev_per_share = prob * (1 - price) - (1 - prob) * price

    return {
        "kelly_raw": round(kelly_raw, 4),
        "kelly_scaled": round(kelly_scaled, 4),
        "position_ratio": round(position_ratio, 4),
        "position_usd": round(position_usd, 2),
        "shares": round(shares, 1),
        "cost_per_share": round(price, 4),
        "expected_value": round(ev_per_share, 4),
    }


def _zero_result() -> dict:
    """返回零仓位结果"""
    return {
        "kelly_raw": 0,
        "kelly_scaled": 0,
        "position_ratio": 0,
        "position_usd": 0,
        "shares": 0,
        "cost_per_share": 0,
        "expected_value": 0,
    }
