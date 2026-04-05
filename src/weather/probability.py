"""
概率分布计算模块

核心功能:
1. 多模型加权融合 → 共识温度 + 标准差
2. 正态 CDF 概率计算 → 各温度区间概率
3. 贝叶斯融合 → 模型概率 + 历史基准
4. 集合预报概率 → 从 31 成员统计
"""

import numpy as np
from scipy.stats import norm
from dataclasses import dataclass

from src.config.settings import (
    MODEL_WEIGHTS,
    OUTLIER_SIGMA_THRESHOLD,
    OUTLIER_PENALTY_FACTOR,
    FORECAST_SIGMA,
)
from src.utils.logger import setup_logger

logger = setup_logger("probability")


@dataclass
class TemperatureBucket:
    """温度区间"""
    low_f: float     # 区间下限 (°F)
    high_f: float    # 区间上限 (°F)

    @property
    def label(self) -> str:
        return f"{self.low_f}-{self.high_f}°F"


@dataclass
class ProbabilityDistribution:
    """概率分布结果"""
    city: str
    target_date: str
    consensus_temp_f: float        # 加权共识温度 (°F)
    sigma_f: float                 # 标准差 (°F)
    model_temps_f: dict[str, float]  # 各模型温度
    bucket_probs: dict[str, float]    # 区间 → 概率


def _get_dynamic_sigma(hours_to_settlement: float) -> float:
    """
    根据距结算时间动态计算标准差

    Args:
        hours_to_settlement: 距结算的小时数

    Returns:
        标准差 (°F)
    """
    # °C → °F 转换因子: 1°C = 1.8°F
    f_factor = 1.8

    if hours_to_settlement <= 6:
        sigma_c = FORECAST_SIGMA["6h"]
    elif hours_to_settlement <= 24:
        sigma_c = FORECAST_SIGMA["1d"]
    elif hours_to_settlement <= 72:
        sigma_c = FORECAST_SIGMA["3d"]
    elif hours_to_settlement <= 168:
        sigma_c = FORECAST_SIGMA["7d"]
    else:
        sigma_c = FORECAST_SIGMA["10d"]

    return sigma_c * f_factor


def blend_models(
    model_temps_f: dict[str, float],
    hours_to_settlement: float = 24,
) -> tuple[float, float, dict[str, float]]:
    """
    多模型加权融合，输出共识温度和标准差

    Args:
        model_temps_f: {"gfs_seamless": 58.5, "ecmwf_ifs025": 60.2, ...}
        hours_to_settlement: 距结算时间

    Returns:
        (consensus_temp_f, sigma_f, adjusted_weights)
    """
    if not model_temps_f:
        raise ValueError("无模型数据")

    # 1. 计算初始加权共识
    weights = {}
    for model, temp in model_temps_f.items():
        base_weight = MODEL_WEIGHTS.get(model, 0.10)
        weights[model] = base_weight

    # 2. 计算初步共识（用于离群值检测）
    total_w = sum(weights.values())
    preliminary = sum(t * (weights[m] / total_w) for m, t in model_temps_f.items())

    # 3. 离群值检测和降权
    temps = list(model_temps_f.values())
    std = np.std(temps) if len(temps) > 1 else 5.0

    for model, temp in model_temps_f.items():
        deviation = abs(temp - preliminary)
        if std > 0 and deviation / std > OUTLIER_SIGMA_THRESHOLD:
            weights[model] *= OUTLIER_PENALTY_FACTOR
            logger.info(f"离群值降权: {model} temp={temp:.1f}°F, "
                        f"偏离共识 {deviation:.1f}°F ({deviation/std:.1f}σ)")

    # 4. 重新计算加权共识
    total_w = sum(weights.values())
    consensus = sum(t * (weights[m] / total_w) for m, t in model_temps_f.items())

    # 5. 标准差 = 动态标准差 + 模型偏差修正（保守）
    # 使用动态标准差作为基础（基于预报时长）
    # 如果模型间差异大，加一个修正项，但不是直接用模型间标准差
    model_std_c = float(np.std(list(model_temps_f.values()))) if len(model_temps_f) > 1 else 0
    model_std_f = model_std_c * 1.8  # °C → °F
    dynamic_sigma = _get_dynamic_sigma(hours_to_settlement)

    # σ = 动态标准差 + 模型偏差附加项（取 sqrt 和而非直接相加）
    # 这样当模型一致时 σ 就是动态标准差，模型分歧大时 σ 适度增大
    sigma = np.sqrt(dynamic_sigma**2 + (model_std_f * 0.5)**2)

    logger.info(f"共识温度: {consensus:.1f}°F, σ={sigma:.1f}°F, "
                f"(模型间σ={model_std_c:.1f}°C, 动态σ={dynamic_sigma:.1f}°F)")

    return consensus, sigma, weights


def calc_bucket_probability(
    consensus_temp_f: float,
    sigma_f: float,
    bucket: TemperatureBucket,
) -> float:
    """
    计算温度落入指定区间的概率（正态 CDF）

    P(low ≤ T ≤ high) = Φ((high - μ) / σ) - Φ((low - μ) / σ)

    Args:
        consensus_temp_f: 共识温度 (°F)
        sigma_f: 标准差 (°F)
        bucket: 温度区间

    Returns:
        概率 [0, 1]
    """
    if sigma_f <= 0:
        sigma_f = 1.0

    # P(T ≤ high)
    p_upper = norm.cdf((bucket.high_f - consensus_temp_f) / sigma_f)
    # P(T ≤ low)
    p_lower = norm.cdf((bucket.low_f - consensus_temp_f) / sigma_f)

    prob = p_upper - p_lower
    return max(0.0, min(1.0, prob))


def calc_all_bucket_probs(
    consensus_temp_f: float,
    sigma_f: float,
    buckets: list[TemperatureBucket],
) -> dict[str, float]:
    """
    计算所有温度区间的概率分布

    Args:
        consensus_temp_f: 共识温度 (°F)
        sigma_f: 标准差 (°F)
        buckets: 温度区间列表

    Returns:
        {"50-55°F": 0.15, "55-60°F": 0.45, ...}
    """
    result = {}
    for bucket in buckets:
        prob = calc_bucket_probability(consensus_temp_f, sigma_f, bucket)
        result[bucket.label] = round(prob, 4)

    # 归一化（确保概率总和为 1）
    total = sum(result.values())
    if total > 0:
        result = {k: round(v / total, 4) for k, v in result.items()}

    return result


def bayesian_blend(
    model_prob: float,
    historical_prob: float,
    model_weight: float = 0.85,
) -> float:
    """
    贝叶斯融合：模型概率 + 历史基准概率

    P_blended = w * P_model + (1-w) * P_historical

    模型权重较高（0.85），因为现代天气预报比历史平均更准。
    但历史数据提供了先验概率，避免模型极端输出。

    Args:
        model_prob: 模型计算的概率
        historical_prob: 历史同日基准概率
        model_weight: 模型权重（默认 0.85）

    Returns:
        融合后概率
    """
    blended = model_weight * model_prob + (1 - model_weight) * historical_prob
    return max(0.0, min(1.0, blended))


def ensemble_probability(
    members_high_f: list[float],
    bucket: TemperatureBucket,
) -> float:
    """
    从集合预报成员计算区间概率

    P = (成员中温度落入区间的数量) / (总成员数)

    Args:
        members_high_f: 各成员的最高温 (°F)
        bucket: 温度区间

    Returns:
        概率 [0, 1]
    """
    if not members_high_f:
        return 0.0

    count = sum(1 for t in members_high_f if bucket.low_f <= t < bucket.high_f)
    return count / len(members_high_f)


def build_probability_distribution(
    city: str,
    target_date: str,
    model_temps_f: dict[str, float],
    buckets: list[TemperatureBucket],
    hours_to_settlement: float = 24,
    historical_probs: dict[str, float] = None,
    ensemble_members_f: list[float] = None,
) -> ProbabilityDistribution:
    """
    构建完整的概率分布

    整合所有概率计算：
    1. 多模型融合 → 共识温度
    2. 正态 CDF → 各区间基础概率
    3. 集合预报概率 → 与正态概率交叉验证
    4. 贝叶斯融合 → 加入历史基准

    Args:
        city: 城市名
        target_date: 目标日期
        model_temps_f: 各模型预报温度
        buckets: 温度区间列表
        hours_to_settlement: 距结算时间
        historical_probs: 历史基准概率 {"50-55°F": 0.12, ...}
        ensemble_members_f: 集合预报各成员温度

    Returns:
        ProbabilityDistribution
    """
    # 1. 多模型融合
    consensus, sigma, adjusted_weights = blend_models(
        model_temps_f, hours_to_settlement
    )

    # 2. 正态 CDF 各区间概率
    normal_probs = calc_all_bucket_probs(consensus, sigma, buckets)

    # 3. 集合预报概率（如果可用）
    ensemble_probs = {}
    if ensemble_members_f:
        for bucket in buckets:
            ensemble_probs[bucket.label] = round(
                ensemble_probability(ensemble_members_f, bucket), 4
            )

    # 4. 融合最终概率
    final_probs = {}
    for bucket in buckets:
        label = bucket.label

        # 基础概率 = 正态 CDF
        prob = normal_probs.get(label, 0.0)

        # 如果有集合预报，取加权平均
        if label in ensemble_probs:
            ens_prob = ensemble_probs[label]
            # 正态 0.6, 集合 0.4
            prob = 0.6 * prob + 0.4 * ens_prob

        # 贝叶斯融合历史概率
        if historical_probs and label in historical_probs:
            prob = bayesian_blend(prob, historical_probs[label])

        final_probs[label] = round(prob, 4)

    # 归一化
    total = sum(final_probs.values())
    if total > 0:
        final_probs = {k: round(v / total, 4) for k, v in final_probs.items()}

    logger.info(f"[{city}] {target_date}: 共识 {consensus:.1f}°F, σ={sigma:.1f}°F")
    for label, prob in sorted(final_probs.items()):
        if prob > 0.01:
            logger.info(f"  {label}: {prob:.1%}")

    return ProbabilityDistribution(
        city=city,
        target_date=target_date,
        consensus_temp_f=round(consensus, 2),
        sigma_f=round(sigma, 2),
        model_temps_f={m: round(t, 2) for m, t in model_temps_f.items()},
        bucket_probs=final_probs,
    )
