"""Utility functions for strategy templates."""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any


def cross_over(series1: pd.Series, series2: pd.Series) -> pd.Series:
    """Detect when series1 crosses above series2."""
    return (series1 > series2) & (series1.shift(1) <= series2.shift(1))


def cross_under(series1: pd.Series, series2: pd.Series) -> pd.Series:
    """Detect when series1 crosses below series2."""
    return (series1 < series2) & (series1.shift(1) >= series2.shift(1))


def normalize(series: pd.Series, window: int | None = None) -> pd.Series:
    """Normalize series to [0, 1] range."""
    if window:
        min_val = series.rolling(window).min()
        max_val = series.rolling(window).max()
    else:
        min_val = series.min()
        max_val = series.max()
    return (series - min_val) / (max_val - min_val)


def zscore(series: pd.Series, window: int) -> pd.Series:
    """Calculate z-score (standard deviations from mean)."""
    return (series - series.rolling(window).mean()) / series.rolling(window).std()


def resample_candles(
    df: pd.DataFrame,
    interval: str,
) -> pd.DataFrame:
    """Resample OHLCV data to a different interval.

    Args:
        df: DataFrame with columns [timestamp, open, high, low, close, volume]
        interval: Pandas resample rule (e.g., '1H', '4H', '1D')

    Returns:
        Resampled DataFrame
    """
    df = df.copy()
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("datetime")

    resampled = df.resample(interval).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()

    resampled["timestamp"] = resampled.index.astype("int64") // 10**6
    return resampled.reset_index(drop=True)


def compute_position_size(
    capital_usdt: float,
    price: float,
    target_allocation: float,
    max_position_pct: float,
) -> float:
    """Compute position size based on allocation and risk parameters.

    Args:
        capital_usdt: Total capital in USDT
        price: Current price
        target_allocation: Target allocation (0 to 1)
        max_position_pct: Maximum position as percentage of capital

    Returns:
        Position size in base units
    """
    max_position_usdt = capital_usdt * (max_position_pct / 100)
    target_usdt = max_position_usdt * abs(target_allocation)
    return target_usdt / price


def compute_risk_reward(
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    direction: str = "long",
) -> float:
    """Compute risk/reward ratio.

    Args:
        entry_price: Entry price
        stop_loss: Stop loss price
        take_profit: Take profit price
        direction: "long" or "short"

    Returns:
        Risk/reward ratio
    """
    if direction == "long":
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
    else:  # short
        risk = abs(stop_loss - entry_price)
        reward = abs(entry_price - take_profit)

    return reward / risk if risk > 0 else 0


def find_support_resistance(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 20,
    num_levels: int = 3,
) -> dict[str, list[float]]:
    """Find support and resistance levels.

    Args:
        high: High prices
        low: Low prices
        close: Close prices
        window: Lookback window
        num_levels: Number of levels to return

    Returns:
        {"support": [...], "resistance": [...]}
    """
    recent_high = high.tail(window)
    recent_low = low.tail(window)
    recent_close = close.tail(window)

    # Pivot points
    pivot_levels = []
    for i in range(2, len(recent_high) - 2):
        # Resistance: local high
        if (recent_high.iloc[i] > recent_high.iloc[i-1] and
            recent_high.iloc[i] > recent_high.iloc[i-2] and
            recent_high.iloc[i] > recent_high.iloc[i+1] and
            recent_high.iloc[i] > recent_high.iloc[i+2]):
            pivot_levels.append(("resistance", recent_high.iloc[i]))

        # Support: local low
        if (recent_low.iloc[i] < recent_low.iloc[i-1] and
            recent_low.iloc[i] < recent_low.iloc[i-2] and
            recent_low.iloc[i] < recent_low.iloc[i+1] and
            recent_low.iloc[i] < recent_low.iloc[i+2]):
            pivot_levels.append(("support", recent_low.iloc[i]))

    # Separate and sort
    support_levels = sorted([level for typ, level in pivot_levels if typ == "support"], reverse=True)[:num_levels]
    resistance_levels = sorted([level for typ, level in pivot_levels if typ == "resistance"])[:num_levels]

    # Add current close as reference
    current_price = float(recent_close.iloc[-1])

    # Filter levels far from current price
    support_levels = [s for s in support_levels if s < current_price * 0.99]
    resistance_levels = [r for r in resistance_levels if r > current_price * 1.01]

    return {
        "support": support_levels,
        "resistance": resistance_levels,
    }
