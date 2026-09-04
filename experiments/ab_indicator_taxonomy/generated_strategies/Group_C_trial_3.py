import pandas as pd
import numpy as np
from backtest.indicators import (
    supertrend,
    ema,
    vwap,
    cmf,
    rsi,
    funding_rate_zscore,
    bollinger_bands,
    atr,
    ts_rank,
    safe_div,
)

def generate_signals(data: pd.DataFrame, params: dict) -> dict[str, list]:
    df = data.copy()
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    volume = df['volume'].values
    oi = df['open_interest'].values
    funding = df['funding_rate'].values

    # --- Trend Trigger: Supertrend ---
    st_dir, st_line = supertrend(high, low, close, period=10, multiplier=3.0)
    # +1 long regime, -1 short regime (derived from close vs supertrend line)
    trend_signal = np.where(close > st_line, 1.0, -1.0)

    # --- Momentum Confirmation: EMA slope + RSI ---
    ema_fast = ema(close, window=20)
    ema_slow = ema(close, window=50)
    ema_slope = ema_fast - ema_slow
    # Normalize slope via ts_rank to make it comparable
    slope_rank = ts_rank(ema_slope, window=100)
    mom_confirm = np.where(slope_rank > 0.5, 1.0, -1.0)

    rsi_val = rsi(close, window=14)
    # Avoid overbought/oversold extremes in trend direction
    rsi_filter = np.where(
        ((rsi_val > 55) & (trend_signal > 0)) | ((rsi_val < 45) & (trend_signal < 0)),
        1.0, 0.0
    )

    # --- Volume Flow Confirmation: VWAP + CMF ---
    vwap_val = vwap(high, low, close, volume)
    vwap_signal = np.where(close > vwap_val, 1.0, -1.0)

    cmf_val = cmf(high, low, close, volume, window=20)
    cmf_signal = np.where(cmf_val > 0, 1.0, -1.0)

    # --- OI Momentum (derivatives conviction) ---
    oi_mom = np.gradient(oi, window=5)  # simple proxy, or use oi_momentum if available
    # Use ts_rank for stability
    oi_rank = ts_rank(oi_mom, window=50)
    oi_signal = np.where(oi_rank > 0.5, 1.0, -1.0)

    # --- Filter: Funding squeeze / crowded trade ---
    funding_z = funding_rate_zscore(funding, window=96)  # ~4 days hourly
    # Avoid crowded longs when funding is too high, and crowded shorts when too low
    squeeze_filter = np.where(
        ((funding_z < 1.5) & (funding_z > -1.5)) | 
        ((funding_z >= 1.5) & (trend_signal < 0)) |
        ((funding_z <= -1.5) & (trend_signal > 0)),
        1.0, 0.0
    )

    # --- Volatility Filter: Bollinger Band width contraction (optional) ---
    bb_upper, bb_middle, bb_lower = bollinger_bands(close, window=20, num_std=2.0)
    bb_width = safe_div(bb_upper - bb_lower, bb_middle)
    bb_rank = ts_rank(bb_width, window=100)
    # Only trade when not in extreme low volatility (avoid chop) -- optional
    vol_filter = np.where(bb_rank > 0.1, 1.0, 0.0)

    # --- Composite Signal (Orthogonal dimensions) ---
    # Trigger x Confirmations x Filters
    raw_signal = trend_signal * mom_confirm * vwap_signal * cmf_signal * oi_signal
    # Apply rsi_filter to ensure alignment with trend, and squeeze/vol filters
    raw_signal = raw_signal * rsi_filter * squeeze_filter * vol_filter

    # --- Dynamic Sizing: ATR-based volatility targeting ---
    atr_val = atr(high, low, close, window=14)
    # Target risk per trade ~ 0.5% of price movement (annualized ~ 8% daily vol)
    # Use inverse ATR scaling, capped between 0.2 and 1.0
    vol_scalar = safe_div(1.0, atr_val)
    # Normalize by rolling mean of vol_scalar to get relative sizing
    vol_scalar_rank = ts_rank(vol_scalar, window=100)
    size_factor = 0.5 + 0.5 * vol_scalar_rank  # range 0.5-1.0

    # Final target weights: raw_signal (either -1 or +1 after filters) * size_factor
    # But raw_signal is -1/0/1; we want continuous scaling for trend strength
    # Use slope_rank as strength multiplier (0.5-1.0) to avoid overtrading
    strength = 0.5 + 0.5 * np.abs(slope_rank - 0.5) * 2  # 0.5 to 1.0
    target_weights = raw_signal * size_factor * strength

    # Clip to [-1, 1]
    target_weights = np.clip(target_weights, -1.0, 1.0)

    # --- Weight Reason ---
    weight_reason = []
    for i in range(len(df)):
        if abs(target_weights[i]) < 1e-6:
            reason = "neutral"
        elif target_weights[i] > 0:
            reason = f"long_trend_mom_vol"
        else:
            reason = f"short_trend_mom_vol"
        weight_reason.append(reason)

    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": weight_reason,
    }