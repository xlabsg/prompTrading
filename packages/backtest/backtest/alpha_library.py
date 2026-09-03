"""Alpha Library: High-performance, vectorized quantitative factor building blocks.

Provides pre-validated, zero-lookahead quantitative indicators for strategy authors
and the autonomous coding agent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (ATR) with zero lookahead bias."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def calc_supertrend(
    df: pd.DataFrame,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    """SuperTrend indicator with dynamic trailing bands and trend regime flag.

    Returns:
        DataFrame with columns: ['supertrend', 'trend_direction'] (1 for bull, -1 for bear)
    """
    atr = calc_atr(df, period).bfill().fillna(0.0)
    hl2 = (df["high"] + df["low"]) / 2.0

    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    n = len(df)
    final_upper = basic_upper.values.copy()
    final_lower = basic_lower.values.copy()
    supertrend = np.zeros(n)
    direction = np.ones(n)  # 1 = long, -1 = short

    close = df["close"].values
    b_upper = basic_upper.values
    b_lower = basic_lower.values

    for i in range(1, n):
        # Upper band adjustment
        if b_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
            final_upper[i] = b_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Lower band adjustment
        if b_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
            final_lower[i] = b_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # Trend direction determination
        if direction[i - 1] == 1:
            if close[i] < final_lower[i]:
                direction[i] = -1
                supertrend[i] = final_upper[i]
            else:
                direction[i] = 1
                supertrend[i] = final_lower[i]
        else:
            if close[i] > final_upper[i]:
                direction[i] = 1
                supertrend[i] = final_lower[i]
            else:
                direction[i] = -1
                supertrend[i] = final_upper[i]

    return pd.DataFrame(
        {
            "supertrend": supertrend,
            "trend_direction": direction,
            "upper_band": final_upper,
            "lower_band": final_lower,
        },
        index=df.index,
    )


def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index (ADX) measuring trend strength (0-100)."""
    high = df["high"]
    low = df["low"]
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = calc_atr(df, period=1)  # 1-period true range
    tr_smooth = tr.rolling(period).sum()
    plus_di = 100.0 * (pd.Series(plus_dm, index=df.index).rolling(period).sum() / tr_smooth.replace(0, np.nan))
    minus_di = 100.0 * (pd.Series(minus_dm, index=df.index).rolling(period).sum() / tr_smooth.replace(0, np.nan))

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100.0
    adx = dx.rolling(period).mean()
    return adx.fillna(0.0)


def calc_keltner_channels(
    df: pd.DataFrame,
    ema_period: int = 20,
    atr_period: int = 10,
    multiplier: float = 2.0,
) -> pd.DataFrame:
    """Keltner Channels: Volatility-based envelopes above and below an EMA."""
    ema = df["close"].ewm(span=ema_period, adjust=False).mean()
    atr = calc_atr(df, atr_period)
    upper = ema + (multiplier * atr)
    lower = ema - (multiplier * atr)

    return pd.DataFrame(
        {
            "middle": ema,
            "upper": upper,
            "lower": lower,
        },
        index=df.index,
    )


def calc_donchian_channels(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Donchian Channels: High/Low breakout bands over N periods (lagged by 1 to avoid lookahead)."""
    upper = df["high"].shift(1).rolling(window=period).max()
    lower = df["low"].shift(1).rolling(window=period).min()
    middle = (upper + lower) / 2.0

    return pd.DataFrame(
        {
            "upper": upper,
            "middle": middle,
            "lower": lower,
        },
        index=df.index,
    )


def calc_vwap_deviation(df: pd.DataFrame, rolling_bars: int = 24) -> pd.Series:
    """Rolling Volume-Weighted Average Price (VWAP) Z-Score / Deviation."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["volume"]
    pv = typical_price * vol

    rolling_pv = pv.rolling(rolling_bars).sum()
    rolling_vol = vol.rolling(rolling_bars).sum()
    vwap = rolling_pv / rolling_vol.replace(0, np.nan)

    std = df["close"].rolling(rolling_bars).std()
    z_score = (df["close"] - vwap) / std.replace(0, np.nan)
    return z_score.fillna(0.0)
