import numpy as np
import pandas as pd
from backtest.indicators import ema, atr, rsi, zscore, ts_rank, cross_over

def generate_signals(data: pd.DataFrame, params: dict) -> dict[str, list]:
    df = data.copy()
    
    # ---------- Parameters ----------
    ema_fast_window = int(params.get("ema_fast_window", 24))
    ema_slow_window = int(params.get("ema_slow_window", 96))
    rsi_window = int(params.get("rsi_window", 14))
    atr_window = int(params.get("atr_window", 14))
    zscore_window = int(params.get("zscore_window", 48))
    vol_lookback = int(params.get("vol_lookback", 96))
    atr_band_mult = float(params.get("atr_band_mult", 1.0))
    rsi_low = float(params.get("rsi_low", 40.0))
    rsi_high = float(params.get("rsi_high", 65.0))
    
    # ---------- Core trend indicators ----------
    df["ema_fast"] = ema(df["close"], ema_fast_window)
    df["ema_slow"] = ema(df["close"], ema_slow_window)
    df["trend"] = np.sign(df["ema_fast"] - df["ema_slow"])
    
    # ---------- Momentum / RSI filter ----------
    df["rsi"] = rsi(df["close"], rsi_window)
    
    # ---------- Volatility normalization ----------
    df["atr"] = atr(df["high"], df["low"], df["close"], atr_window)
    df["vol_sma"] = df["atr"].rolling(vol_lookback).mean()
    df["vol_regime"] = df["atr"] / df["vol_sma"]  # >1 = high vol
    
    # ---------- Mean reversion / exhaustion filter ----------
    df["ret_48"] = df["close"].pct_change(zscore_window)
    df["ret_z"] = zscore(df["ret_48"], zscore_window)
    
    # ---------- ATR band breakout for entry timing ----------
    df["upper_band"] = df["ema_slow"] + atr_band_mult * df["atr"]
    df["lower_band"] = df["ema_slow"] - atr_band_mult * df["atr"]
    df["above_upper"] = df["close"] > df["upper_band"]
    df["below_lower"] = df["close"] < df["lower_band"]
    
    # ---------- Combine signals ----------
    # Long conditions: trend up, RSI not overbought, breakout above upper band, not extreme exhaustion
    long_signal = (
        (df["trend"] > 0) &
        (df["rsi"] < rsi_high) &
        (df["above_upper"]) &
        (df["ret_z"] < 2.0) &  # avoid chasing parabolic moves
        (df["vol_regime"] < 2.5)  # avoid extreme volatility spikes
    ).astype(int)
    
    # Short conditions: trend down, RSI not oversold, breakdown below lower band, not extreme panic
    short_signal = (
        (df["trend"] < 0) &
        (df["rsi"] > rsi_low) &
        (df["below_lower"]) &
        (df["ret_z"] > -2.0) &  # avoid catching falling knife
        (df["vol_regime"] < 2.5)
    ).astype(int)
    
    # ---------- Trend persistence confirmation ----------
    df["trend_ma"] = ema(df["trend"], 12)
    long_signal = long_signal & (df["trend_ma"] > 0.3)
    short_signal = short_signal & (df["trend_ma"] < -0.3)
    
    # ---------- Base target weights ----------
    raw_target = long_signal - short_signal
    
    # ---------- Position sizing by volatility ----------
    # Scale down position in high vol regimes to control drawdowns
    vol_scale = np.clip(1.0 / (df["vol_regime"].fillna(1.0)), 0.3, 1.0)
    target = raw_target * vol_scale
    
    # ---------- Smooth transitions (no whipsaw) ----------
    # Apply slow EMA to target to avoid rapid flips
    target_series = pd.Series(target, index=df.index)
    target_smooth = ts_rank(target_series.rolling(3).mean(), 5).fillna(0.0)
    
    # ---------- Final weight generation ----------
    # Convert smoothed signal to final weights with hysteresis
    final_weights = pd.Series(0.0, index=df.index)
    
    # Entry logic (from flat)
    final_weights[target_smooth > 0.6] = 1.0 * vol_scale[target_smooth > 0.6]
    final_weights[target_smooth < -0.6] = -1.0 * vol_scale[target_smooth < -0.6]
    
    # Exit logic (reduce when strength fades)
    neutral_mask = (target_smooth.abs() < 0.2)
    final_weights[neutral_mask] = 0.0
    
    # ---------- Crash protection: if RSI extreme and price far from EMA, reduce exposure ----------
    price_dev = (df["close"] - df["ema_slow"]) / df["atr"]
    overextended_long = (price_dev > 5.0) & (df["rsi"] > 75)
    overextended_short = (price_dev < -5.0) & (df["rsi"] < 25)
    final_weights[overextended_long & (final_weights > 0)] *= 0.5
    final_weights[overextended_short & (final_weights < 0)] *= 0.5
    
    # ---------- Generate reason strings ----------
    reasons = []
    for i in range(len(df)):
        w = final_weights.iloc[i]
        if w > 0.05:
            reasons.append("long_trend_breakout")
        elif w < -0.05:
            reasons.append("short_trend_breakdown")
        else:
            reasons.append("neutral_flat")
    
    # ---------- Handle NaN and forward fill ----------
    final_weights = final_weights.fillna(0.0).clip(-1.0, 1.0)
    
    return {
        "target_weights": final_weights.tolist(),
        "weight_reason": reasons
    }