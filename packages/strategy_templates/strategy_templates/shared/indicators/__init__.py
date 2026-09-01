"""Technical indicators for strategy templates.

All indicators are vectorized for performance with pandas DataFrames.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Literal


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=window, min_periods=1).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=window, adjust=False).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder smoothing)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    result = 100 - (100 / (1 + rs))
    return result.fillna(50)


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD indicator.

    Returns:
        (macd_line, signal_line, histogram)
    """
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_window: int = 14,
    d_window: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """Stochastic Oscillator.

    Returns:
        (%K, %D)
    """
    lowest_low = low.rolling(window=k_window).min()
    highest_high = high.rolling(window=k_window).max()
    k_percent = 100 * (close - lowest_low) / (highest_high - lowest_low)
    d_percent = k_percent.rolling(window=d_window).mean()
    return k_percent, d_percent


def stochastic_oscillator(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
    smooth_k: int = 3,
) -> pd.DataFrame:
    lowest_low = low.rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.rolling(window=k_period, min_periods=k_period).max()

    raw_k = (close - lowest_low) / (highest_high - lowest_low) * 100
    smooth_k_series = raw_k.rolling(window=smooth_k, min_periods=smooth_k).mean()
    d_line = smooth_k_series.rolling(window=d_period, min_periods=d_period).mean()

    return pd.DataFrame({"stoch_k": smooth_k_series, "stoch_d": d_line})


def bollinger_bands(
    series: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands.

    Returns:
        (upper_band, middle_band, lower_band)
    """
    middle_band = sma(series, window)
    std = series.rolling(window=window).std()
    upper_band = middle_band + (std * num_std)
    lower_band = middle_band - (std * num_std)
    return upper_band, middle_band, lower_band


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 14,
) -> pd.Series:
    """Average True Range."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(span=window, adjust=False).mean()


def mfi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: int = 14,
) -> pd.Series:
    if period <= 0:
        raise ValueError("MFI period must be positive")

    tp = (high + low + close) / 3.0
    rmf = tp * volume
    delta = tp.diff()

    pos = rmf.where(delta > 0, 0.0)
    neg = rmf.where(delta < 0, 0.0)

    pos_sum = pos.rolling(window=period, min_periods=period).sum()
    neg_sum = neg.rolling(window=period, min_periods=period).sum()

    ratio = pos_sum / neg_sum.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + ratio))

    out = out.where(~((neg_sum == 0) & (pos_sum > 0)), 100.0)
    out = out.where(~((pos_sum == 0) & (neg_sum > 0)), 0.0)
    out = out.where(~((pos_sum == 0) & (neg_sum == 0)), 50.0)

    return out.fillna(50.0)


def cci(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
) -> pd.Series:
    if period <= 0:
        raise ValueError("CCI period must be positive")
    tp = (high + low + close) / 3.0
    sma_tp = tp.rolling(window=period, min_periods=period).mean()
    mean_dev = (tp - sma_tp).abs().rolling(window=period, min_periods=period).mean()
    denom = (0.015 * mean_dev).replace(0, pd.NA)
    out = (tp - sma_tp) / denom
    return out.fillna(0.0)


def volume_weighted_macd(
    close: pd.Series,
    volume: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast_vwema = _vwema(close, volume, fast)
    slow_vwema = _vwema(close, volume, slow)
    vw_macd_line = fast_vwema - slow_vwema
    vw_signal_line = ema(vw_macd_line, signal)
    vw_histogram = vw_macd_line - vw_signal_line
    return vw_macd_line, vw_signal_line, vw_histogram


def _vwema(price: pd.Series, volume: pd.Series, span: int) -> pd.Series:
    weighted_price = price * volume
    numerator = weighted_price.ewm(span=span, adjust=False).mean()
    denominator = volume.ewm(span=span, adjust=False).mean()
    vwema_series = numerator / denominator.replace(0, pd.NA)
    return vwema_series.bfill().ffill()


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    delta = close.diff()
    obv_step = volume.where(delta > 0, 0) - volume.where(delta < 0, 0)
    obv_series = obv_step.fillna(0).cumsum()
    return obv_series


def detect_pivots(
    high: pd.Series,
    low: pd.Series,
    window: int = 5,
    min_strength: int = 1,
) -> tuple[pd.Series, pd.Series]:
    """Detect pivot highs and lows.

    Args:
        high: High prices
        low: Low prices
        window: Number of bars on each side to check
        min_strength: Minimum strength (1 = minor, 2 = major, etc.)

    Returns:
        (pivot_highs, pivot_lows) - Series with 1 at pivot points, 0 elsewhere
    """
    pivot_highs = pd.Series(0, index=high.index)
    pivot_lows = pd.Series(0, index=low.index)

    for i in range(window, len(high) - window):
        # Check for pivot high
        is_high = True
        for j in range(1, window + 1):
            if high.iloc[i] <= high.iloc[i - j] or high.iloc[i] <= high.iloc[i + j]:
                is_high = False
                break
        if is_high:
            pivot_highs.iloc[i] = 1

        # Check for pivot low
        is_low = True
        for j in range(1, window + 1):
            if low.iloc[i] >= low.iloc[i - j] or low.iloc[i] >= low.iloc[i + j]:
                is_low = False
                break
        if is_low:
            pivot_lows.iloc[i] = 1

    return pivot_highs, pivot_lows
