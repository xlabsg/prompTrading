"""Financial robustness and anti-overfitting analytics for trading strategies.

Implements:
1. Deflated Sharpe Ratio (DSR) - Bailey & López de Prado (2014)
   Adjusts observed Sharpe ratio for non-normality (skewness, kurtosis), sample length,
   and multiple testing / data snooping across N backtest iterations.
2. Monte Carlo Permutation Test - Shuffles return series to estimate empirical p-value.
3. Composite Robustness Scoring - Balances Sharpe, DSR, drawdown, and trade count.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np


EULER_MASCHERONI = 0.5772156649015329


def _norm_cdf(z: float) -> float:
    """Standard normal cumulative distribution function (CDF)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Standard normal quantile function (inverse CDF) via Acklam's algorithm."""
    if p <= 0.0:
        return -float("inf")
    if p >= 1.0:
        return float("inf")
    if p == 0.5:
        return 0.0

    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )

    p_low = 0.02425
    p_high = 1.0 - p_low

    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    elif p <= p_high:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
            * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )


def _calc_skew_kurtosis(arr: np.ndarray) -> tuple[float, float]:
    """Calculate sample skewness and Pearson kurtosis (normal distribution = 3.0)."""
    n = len(arr)
    if n < 4:
        return 0.0, 3.0
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=0))
    if std < 1e-12:
        return 0.0, 3.0
    z = (arr - mean) / std
    skew = float(np.mean(z**3))
    kurt = float(np.mean(z**4))
    return skew, kurt


@dataclass(frozen=True)
class RobustnessResult:
    observed_sharpe: float
    deflated_sharpe_ratio: float  # DSR probability in [0.0, 1.0]
    p_value: float  # Empirical p-value from Monte Carlo permutation test
    skewness: float
    kurtosis: float
    trials_count: int
    num_trades: int
    is_robust: bool
    robustness_score: float
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "observed_sharpe": round(self.observed_sharpe, 4),
            "deflated_sharpe_ratio": round(self.deflated_sharpe_ratio, 4),
            "p_value": round(self.p_value, 4),
            "skewness": round(self.skewness, 4),
            "kurtosis": round(self.kurtosis, 4),
            "trials_count": self.trials_count,
            "num_trades": self.num_trades,
            "is_robust": self.is_robust,
            "robustness_score": round(self.robustness_score, 4),
            "diagnostics": self.diagnostics,
        }


def compute_expected_max_sharpe(
    trials_count: int,
    var_sharpe: float = 1.0,
) -> float:
    """Expected maximum Sharpe ratio among N independent/weakly-correlated trials under null SR=0.

    Uses extreme value theory approximation (Bailey & Lopez de Prado 2014).
    """
    if trials_count <= 1:
        return 0.0

    std_sharpe = math.sqrt(max(1e-6, var_sharpe))
    q1 = _norm_ppf(1.0 - 1.0 / trials_count)
    q2 = _norm_ppf(1.0 - 1.0 / (trials_count * math.e))

    expected_max = std_sharpe * ((1.0 - EULER_MASCHERONI) * q1 + EULER_MASCHERONI * q2)
    return max(0.0, float(expected_max))


def compute_dsr(
    returns: np.ndarray | Sequence[float],
    observed_sharpe: float,
    trials_count: int = 1,
    var_sharpe: float = 1.0,
    periods_per_year: float = 365.0 * 24.0,
) -> tuple[float, float, float]:
    """Compute Deflated Sharpe Ratio (DSR).

    Returns:
        (dsr_probability, skewness, kurtosis)
    """
    arr = np.asarray(returns, dtype=np.float64)
    arr = arr[~np.isnan(arr) & ~np.isinf(arr)]

    n = len(arr)
    if n < 10 or abs(observed_sharpe) < 1e-6:
        return 0.5, 0.0, 3.0

    # De-annualize Sharpe to match bar-frequency returns for standard error calculation
    scale = math.sqrt(periods_per_year) if periods_per_year > 0 else 1.0
    sr_bar = observed_sharpe / scale

    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1))
    if std < 1e-12:
        return 0.0, 0.0, 3.0

    # Calculate skewness and kurtosis
    skew, kurt = _calc_skew_kurtosis(arr)

    # Standard error of Sharpe ratio under non-normality (Mertens 2002)
    se_factor = 1.0 - skew * sr_bar + ((kurt - 1.0) / 4.0) * (sr_bar**2)
    if se_factor <= 0:
        se_factor = 1.0
    se_sr = math.sqrt(se_factor / (n - 1))

    # Benchmark hurdle Sharpe ratio accounting for N trials
    expected_max_bar = compute_expected_max_sharpe(trials_count, var_sharpe=var_sharpe) / scale

    # Test statistic z
    z = (sr_bar - expected_max_bar) / max(1e-9, se_sr)
    dsr_prob = _norm_cdf(z)

    return max(0.0, min(1.0, dsr_prob)), skew, kurt


def compute_monte_carlo_p_value(
    returns: np.ndarray | Sequence[float],
    observed_sharpe: float,
    num_simulations: int = 300,
    seed: int = 42,
) -> float:
    """Monte Carlo sign-flip permutation test.

    Under the null hypothesis of no trading skill (H0: zero expected return),
    we randomly invert the return signs (Rademacher permutation) to construct
    the empirical null distribution and determine if the observed Sharpe ratio
    is statistically significant (p < 0.05).
    """
    arr = np.asarray(returns, dtype=np.float64)
    arr = arr[~np.isnan(arr) & ~np.isinf(arr)]
    n = len(arr)

    if n < 10 or observed_sharpe <= 0:
        return 1.0

    mean_actual = float(np.mean(arr))
    std_actual = float(np.std(arr, ddof=1))
    if std_actual < 1e-12 or mean_actual <= 0:
        return 1.0

    actual_t_stat = (mean_actual / std_actual) * math.sqrt(n)

    rng = np.random.default_rng(seed)
    # Rademacher sign-flip permutation
    permuted_t_stats = np.empty(num_simulations, dtype=np.float64)

    for i in range(num_simulations):
        signs = rng.choice(np.array([-1.0, 1.0]), size=n)
        shuffled = arr * signs
        mean_s = np.mean(shuffled)
        std_s = np.std(shuffled, ddof=1)
        if std_s > 1e-12:
            permuted_t_stats[i] = (mean_s / std_s) * math.sqrt(n)
        else:
            permuted_t_stats[i] = 0.0

    # Empirical p-value: proportion of null simulations achieving >= actual t-stat
    p_val = float(np.mean(permuted_t_stats >= actual_t_stat))
    return max(0.0, min(1.0, p_val))


def evaluate_strategy_robustness(
    returns: np.ndarray | Sequence[float],
    observed_sharpe: float,
    max_drawdown: float,
    num_trades: int,
    trials_count: int = 1,
    periods_per_year: float = 365.0 * 24.0,
    monte_carlo_sims: int = 200,
) -> RobustnessResult:
    """Run comprehensive robustness evaluation and return structured metrics."""
    arr = np.asarray(returns, dtype=np.float64)
    arr = arr[~np.isnan(arr) & ~np.isinf(arr)]

    dsr, skew, kurt = compute_dsr(
        returns=arr,
        observed_sharpe=observed_sharpe,
        trials_count=trials_count,
        periods_per_year=periods_per_year,
    )

    p_val = compute_monte_carlo_p_value(
        returns=arr,
        observed_sharpe=observed_sharpe,
        num_simulations=monte_carlo_sims,
    )

    diagnostics: list[str] = []

    # Trade count evaluation
    trade_confidence = min(1.0, max(0.0, num_trades / 20.0))
    if num_trades < 10:
        diagnostics.append(f"Insufficient trade sample ({num_trades} trades). Minimum recommended: 15+.")

    # Skewness diagnostics (fat-tail loss risk)
    if skew < -1.0:
        diagnostics.append(f"Strong negative return skewness ({skew:.2f}) indicates severe tail risk.")

    # Kurtosis diagnostics
    if kurt > 10.0:
        diagnostics.append(f"High kurtosis ({kurt:.2f}) indicates extreme outlier sensitivity.")

    # Multiple testing penalty
    if trials_count > 3:
        diagnostics.append(f"DSR penalizes {trials_count} trial runs to guard against data snooping.")

    # Robustness criteria:
    # 1. Observed Sharpe > 0.8
    # 2. DSR >= 0.80 (80% probability that observed edge is non-spurious)
    # 3. Monte Carlo p-value <= 0.10 (statistically significant at 90% confidence)
    # 4. At least 10 trades
    is_robust = (
        observed_sharpe >= 0.8
        and dsr >= 0.80
        and p_val <= 0.10
        and num_trades >= 10
    )

    # Composite robustness score
    # Score = max(0, Sharpe) * DSR * (1 - MDD) * trade_confidence
    mdd_clean = max(0.0, min(1.0, abs(max_drawdown)))
    effective_sharpe = max(0.0, observed_sharpe)
    robustness_score = effective_sharpe * dsr * (1.0 - mdd_clean) * trade_confidence

    return RobustnessResult(
        observed_sharpe=observed_sharpe,
        deflated_sharpe_ratio=dsr,
        p_value=p_val,
        skewness=skew,
        kurtosis=kurt,
        trials_count=trials_count,
        num_trades=num_trades,
        is_robust=is_robust,
        robustness_score=robustness_score,
        diagnostics=diagnostics,
    )
