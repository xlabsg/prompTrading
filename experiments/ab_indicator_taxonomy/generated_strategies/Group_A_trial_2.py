import numpy as np
import pandas as pd
from backtest.indicators import (
    ema, atr, rsi, zscore, supertrend, ts_rank, cross_over, cross_under
)

def generate_signals(data: pd.DataFrame, params: dict) -> dict[str, list]:
    # Strategy parameters
    fast_ema = params.get("fast_ema", 24)       # ~1 day
    slow_ema = params.get("slow_ema", 96)       # ~4 days
    trend_ema = params.get("trend_ema", 168)    # ~7 days
    atr_window = params.get("atr_window", 14)
    atr_mult = params.get("atr_mult", 2.0)      # ATR filter threshold
    rsi_window = params.get("rsi_window", 14)
    rsi_high = params.get("rsi_high", 70)
    rsi_low = params.get("rsi_low", 30)
    momentum_window = params.get("mom_window", 48)
    vol_target = params.get("vol_target", 0.02) # 2% vol target
    max_pos = params.get("max_pos", 0.9)

    close = data["close"]
    high = data["high"]
    low = data["low"]

    # --- Trend signals ---
    # Primary trend filter: price above/below slow EMA
    trend_ema_series = ema(close, trend_ema)
    primary_trend = np.where(close > trend_ema_series, 1.0, -1.0)

    # Trend momentum: EMA crossover for entry timing
    fast_ema_series = ema(close, fast_ema)
    slow_ema_series = ema(close, slow_ema)
    ema_diff = fast_ema_series - slow_ema_series

    # --- Momentum filters ---
    # RSI for overbought/oversold momentum confirmation
    rsi_series = rsi(close, rsi_window)

    # Short-term momentum: price change over lookback window
    momentum = close.pct_change(momentum_window).fillna(0)
    momentum_z = zscore(momentum, momentum_window)

    # --- Volatility filters ---
    # ATR as a proxy for current volatility regime
    atr_series = atr(high, low, close, atr_window)
    atr_pct = atr_series / close
    atr_filter = np.where(atr_pct > atr_mult * atr_pct.rolling(100).mean(), 0.0, 1.0)

    # --- Signal construction ---
    # Long: primary uptrend + EMA momentum + RSI not overbought
    long_signal = (
        (primary_trend > 0) &
        (ema_diff > 0) &
        (rsi_series < rsi_high) &
        (momentum_z > 0)
    )

    # Short: primary downtrend + EMA momentum + RSI not oversold
    short_signal = (
        (primary_trend < 0) &
        (ema_diff < 0) &
        (rsi_series > rsi_low) &
        (momentum_z < 0)
    )

    # --- Position sizing with volatility targeting ---
    # Base position scaled by inverse volatility (ATR%)
    vol_scale = np.clip(vol_target / (atr_pct + 1e-6), 0, max_pos)
    
    # Combine signals with scaling
    raw_position = np.where(long_signal, 1.0, 0.0) - np.where(short_signal, 1.0, 0.0)
    target_weights = raw_position * vol_scale * atr_filter

    # Smooth transitions with 3-period rolling mean (no lookahead)
    target_weights = pd.Series(target_weights).rolling(3, min_periods=1).mean().values

    # Clamp to [-max_pos, max_pos]
    target_weights = np.clip(target_weights, -max_pos, max_pos)

    # --- Reason mapping ---
    strength = np.abs(target_weights) / max_pos
    reasons = []
    for i in range(len(data)):
        if abs(target_weights[i]) < 0.01:
            reasons.append("neutral")
        elif target_weights[i] > 0:
            if strength[i] > 0.7:
                reasons.append("strong_long_trend_momentum")
            else:
                reasons.append("long_trend_momentum")
        else:
            if strength[i] > 0.7:
                reasons.append("strong_short_trend_momentum")
            else:
                reasons.append("short_trend_momentum")

    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": reasons,
    }