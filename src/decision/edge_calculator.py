"""
Edge 计算器

比较天气模型概率与 Polymarket 市场价格，发现定价偏差。
"""

from dataclasses import dataclass
from typing import Optional

from src.config.settings import MIN_EDGE, MAX_SPREAD
from src.utils.logger import setup_logger

logger = setup_logger("edge_calc")


@dataclass
class EdgeSignal:
    """Edge 信号"""
    city: str
    target_date: str
    label: str              # 温度区间 "54-55°F"
    market_id: str
    token_id: str           # YES token
    side: str               # "BUY_YES" or "BUY_NO"
    model_prob: float       # 模型概率
    market_prob: float      # 市场价格（隐含概率）
    edge: float             # model_prob - market_prob
    abs_edge: float         # |edge|
    yes_price: float        # 市场当前 YES 价格
    no_price: float         # 市场当前 NO 价格
    best_bid: float
    best_ask: float
    spread: float
    volume: float
    liquidity: float
    source: str             # 价格来源 "gamma" / "clob_mid" / "clob_last"


def calculate_edge(
    model_prob: float,
    market_yes_price: float,
    market_no_price: float = None,
    best_bid: float = 0,
    best_ask: float = 0,
    spread: float = 0,
    volume: float = 0,
    source: str = "gamma",
) -> Optional[EdgeSignal]:
    """
    计算单个市场的 Edge

    Edge = P_model - P_market

    正 Edge → 模型认为更可能发生 → 买入 YES
    负 Edge → 模型认为更不可能发生 → 买入 NO

    Args:
        model_prob: 模型计算的概率 [0, 1]
        market_yes_price: 市场 YES 价格 [0, 1]
        market_no_price: 市场 NO 价格 [0, 1]
        best_bid: 最佳买价
        best_ask: 最佳卖价
        spread: 价差
        volume: 交易量
        source: 价格来源

    Returns:
        EdgeSignal 或 None（如果 Edge 太小）
    """
    if market_no_price is None:
        market_no_price = 1.0 - market_yes_price

    market_prob = market_yes_price  # 市场隐含的 YES 概率
    edge = model_prob - market_prob
    abs_edge = abs(edge)

    # 确定方向
    if edge > 0:
        side = "BUY_YES"
    else:
        side = "BUY_NO"

    return EdgeSignal(
        city="",
        target_date="",
        label="",
        market_id="",
        token_id="",
        side=side,
        model_prob=round(model_prob, 4),
        market_prob=round(market_prob, 4),
        edge=round(edge, 4),
        abs_edge=round(abs_edge, 4),
        yes_price=market_yes_price,
        no_price=market_no_price,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        volume=volume,
        liquidity=0,
        source=source,
    )


def filter_signals(
    signals: list[EdgeSignal],
    min_edge: float = MIN_EDGE,
    max_spread: float = MAX_SPREAD,
    min_volume: float = 0,
) -> list[EdgeSignal]:
    """
    过滤信号：去掉 Edge 太小、spread 太宽、流动性不足的

    Args:
        signals: 原始信号列表
        min_edge: 最小 |Edge|
        max_spread: 最大 spread（超过此值说明流动性差）
        min_volume: 最小交易量

    Returns:
        过滤后的信号列表
    """
    filtered = []

    for s in signals:
        # Edge 过滤
        if s.abs_edge < min_edge:
            continue

        # Spread 过滤（只在有 spread 数据时）
        if s.spread > 0 and s.spread > max_spread:
            continue

        # 成交量过滤
        if s.volume < min_volume:
            continue

        # 市场价格极端过滤（0.001 或 0.999 的市场不碰）
        if s.yes_price < 0.005 or s.yes_price > 0.995:
            continue

        filtered.append(s)

    return filtered


def rank_signals(signals: list[EdgeSignal]) -> list[EdgeSignal]:
    """
    按 Edge 大小排序信号

    排序因子: abs_edge (越大越好)
    """
    return sorted(signals, key=lambda s: s.abs_edge, reverse=True)
