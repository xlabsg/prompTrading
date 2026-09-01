from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ScreeningConfig:
    max_drawdown_pct: float = 5.0
    min_years: float = 1.0
    rolling_window_days: int = 30


def _duration_years(timestamps_ms: np.ndarray) -> float:
    if timestamps_ms.size < 2:
        return 0.0
    span_ms = int(timestamps_ms[-1]) - int(timestamps_ms[0])
    if span_ms <= 0:
        return 0.0
    return float(span_ms) / (365.0 * 24.0 * 60.0 * 60.0 * 1000.0)


def annualized_return_pct(*, initial_equity: float, final_equity: float, years: float) -> float:
    if initial_equity <= 0 or final_equity <= 0 or years <= 0:
        return 0.0
    growth = final_equity / initial_equity
    if growth <= 0:
        return 0.0
    return (float(growth) ** (1.0 / years) - 1.0) * 100.0


def calmar_ratio(*, annual_return_pct: float, max_drawdown_pct: float) -> float:
    dd = float(max_drawdown_pct)
    if dd <= 0:
        return 0.0
    return float(annual_return_pct) / dd


def rolling_positive_ratio(
    equity: pd.Series,
    *,
    window_bars: int,
) -> float:
    if window_bars <= 1 or len(equity) <= window_bars:
        return 0.0
    values = equity.to_numpy(dtype=np.float64)
    base = values[:-window_bars]
    ahead = values[window_bars:]
    ok = base > 0
    if not np.any(ok):
        return 0.0
    window_returns = (ahead[ok] / base[ok]) - 1.0
    return float(np.mean(window_returns > 0))


def window_bars_from_interval(*, interval: str, days: int) -> int | None:
    s = (interval or "").strip()
    if not s:
        return None
    unit = s[-1]
    try:
        n = int(s[:-1])
    except Exception:
        return None
    if n <= 0:
        return None
    if unit == "m":
        bars_per_day = (60 * 24) / n
    elif unit == "h":
        bars_per_day = 24 / n
    elif unit == "d":
        bars_per_day = 1 / n
    else:
        return None
    return max(2, int(round(days * bars_per_day)))


def summarize_backtest_for_screening(
    equity_df: pd.DataFrame,
    metrics: dict[str, Any],
    *,
    interval: str,
    config: ScreeningConfig | None = None,
) -> dict[str, Any]:
    config = config or ScreeningConfig()
    if equity_df.empty:
        return {"is_valid": False, "reason": "empty_equity"}

    ts = equity_df["timestamp"].to_numpy(dtype=np.int64)
    years = _duration_years(ts)
    if years < float(config.min_years) * 0.95:
        return {
            "is_valid": False,
            "reason": "insufficient_history",
            "years": years,
        }

    initial_equity = float(metrics.get("initial_cash") or equity_df["equity"].iloc[0])
    final_equity = float(metrics.get("final_equity") or equity_df["equity"].iloc[-1])
    total_return_pct = float(metrics.get("total_return") or 0.0)
    max_dd_pct = float(metrics.get("max_drawdown") or 0.0)

    ann_ret = annualized_return_pct(initial_equity=initial_equity, final_equity=final_equity, years=years)
    calmar = calmar_ratio(annual_return_pct=ann_ret, max_drawdown_pct=max_dd_pct)

    wb = window_bars_from_interval(interval=interval, days=config.rolling_window_days) or 0
    pos_ratio = rolling_positive_ratio(equity_df["equity"], window_bars=wb)

    return {
        "is_valid": True,
        "years": years,
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_dd_pct,
        "annualized_return_pct": ann_ret,
        "calmar_ratio": calmar,
        "rolling_positive_ratio": pos_ratio,
        "fee_rate": metrics.get("fee_rate"),
        "slippage_bps": metrics.get("slippage_bps"),
        "total_trades": metrics.get("total_trades"),
        "sharpe_ratio": metrics.get("sharpe_ratio"),
        "profit_factor": metrics.get("profit_factor"),
        "win_rate_pct": metrics.get("win_rate"),
    }


def passes_stable5_gate(summary: dict[str, Any], *, max_drawdown_pct: float = 5.0) -> bool:
    if not summary.get("is_valid"):
        return False
    if float(summary.get("max_drawdown_pct") or 0.0) > float(max_drawdown_pct):
        return False
    if float(summary.get("total_return_pct") or 0.0) <= 0.0:
        return False
    return True

