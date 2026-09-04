import numpy as np
import pandas as pd
from backtest.indicators import (
    supertrend, ema, rsi, atr, bollinger_bands, cmf,
    cross_over, cross_under, safe_div, ts_rank
)

def generate_signals(data: pd.DataFrame, params: dict) -> dict[str, list]:
    high = data['high']
    low = data['low']
    close = data['close']
    volume = data['volume']
    funding_rate = data['funding_rate']
    open_interest = data['open_interest']

    # --- Trend: Supertrend (fast) + EMA filter (slow) ---
    st_fast = supertrend(high, low, close, period=10, multiplier=2.0)
    st_slow = supertrend(high, low, close, period=20, multiplier=3.0)
    ema_long = ema(close, window=100)

    trend_long = (st_fast > 0) & (st_slow > 0) & (close > ema_long)
    trend_short = (st_fast < 0) & (st_slow < 0) & (close < ema_long)

    # --- Momentum: RSI + zscore of close (mean reversion filter) ---
    rsi_val = rsi(close, window=14)
    close_z = (close - close.rolling(20).mean()) / close.rolling(20).std()

    mom_long = (rsi_val > 50) & (close_z > -1.0)
    mom_short = (rsi_val < 50) & (close_z < 1.0)

    # --- Volatility: ATR filter (avoid choppy low-vol) ---
    atr_val = atr(high, low, close, window=14)
    atr_ratio = safe_div(atr_val, close)
    vol_ok = atr_ratio > 0.005  # minimum volatility threshold

    # --- Volume / Flow: CMF confirms accumulation/distribution ---
    cmf_val = cmf(high, low, close, volume, window=20)
    flow_long = cmf_val > 0
    flow_short = cmf_val < 0

    # --- Sentiment / Derivatives: Funding rate extreme filter ---
    fr_z = (funding_rate - funding_rate.rolling(72).mean()) / funding_rate.rolling(72).std()
    fr_z = fr_z.fillna(0.0)

    # Avoid longs when funding is extremely positive (crowded long)
    # Avoid shorts when funding is extremely negative (crowded short)
    sentiment_ok_long = fr_z < 1.5
    sentiment_ok_short = fr_z > -1.5

    # --- Combine signals ---
    long_signal = trend_long & mom_long & vol_ok & flow_long & sentiment_ok_long
    short_signal = trend_short & mom_short & vol_ok & flow_short & sentiment_ok_short

    # --- Dynamic position sizing based on trend strength & RSI distance ---
    # Base weight = 0.8, scale by |RSI-50|/50 (max 1.0)
    rsi_strength = np.abs(rsi_val - 50) / 50.0
    rsi_strength = rsi_strength.clip(upper=1.0)

    # ATR-based position scaling: reduce size when vol is extreme
    atr_percentile = ts_rank(atr_ratio, window=100)  # 0 to 1
    vol_scale = 1.0 - 0.5 * atr_percentile  # scale from 1.0 (low vol) to 0.5 (high vol)

    # Target weight = 0.8 * rsi_strength * vol_scale
    raw_weight = 0.8 * rsi_strength * vol_scale

    target_weights = np.zeros(len(close))
    target_weights[long_signal] = raw_weight[long_signal]
    target_weights[short_signal] = -raw_weight[short_signal]

    # --- Smooth transitions (EMA of weights) to reduce turnover ---
    target_weights = pd.Series(target_weights).ewm(span=6, adjust=False).mean().values

    # --- Weight reason ---
    reason = np.empty(len(close), dtype=object)
    reason[:] = 'neutral'
    reason[long_signal] = 'trend+momentum+flow'
    reason[short_signal] = 'trend+momentum+flow'
    reason[(long_signal | short_signal) & (target_weights == 0)] = 'scaled_out'

    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": reason.tolist(),
    }