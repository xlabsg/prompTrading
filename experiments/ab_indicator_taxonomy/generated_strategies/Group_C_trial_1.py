import pandas as pd
import numpy as np
from backtest.indicators import (
    supertrend,
    ema,
    vwap,
    rsi,
    atr,
    funding_rate_zscore,
    oi_momentum,
    safe_div,
)


def generate_signals(data: pd.DataFrame, params: dict) -> dict[str, list]:
    # --- Params ---
    trend_window = params.get("trend_window", 10)
    atr_window = params.get("atr_window", 14)
    atr_mult = params.get("atr_mult", 3.0)
    vwap_window = params.get("vwap_window", 24)
    rsi_window = params.get("rsi_window", 14)
    rsi_ob = params.get("rsi_ob", 70)
    rsi_os = params.get("rsi_os", 30)
    funding_z = params.get("funding_z", 2.0)
    oi_window = params.get("oi_window", 10)
    oi_thresh = params.get("oi_thresh", 0.0)
    vol_target = params.get("vol_target", 0.02)
    max_leverage = params.get("max_leverage", 3.0)

    high = data["high"]
    low = data["low"]
    close = data["close"]
    volume = data["volume"]
    funding = data["funding_rate"]
    oi = data["open_interest"]

    # --- Indicators ---
    # Trend trigger
    trend_signal = supertrend(high, low, close, window=trend_window, multiplier=atr_mult)

    # Momentum / trend filter (EMA slope)
    ema_short = ema(close, window=trend_window)
    ema_long = ema(close, window=trend_window * 3)
    slope = ema_short - ema_long

    # Volume confirmation: VWAP deviation
    vwap_val = vwap(high, low, close, volume, window=vwap_window)
    vwap_dev = safe_div(close - vwap_val, vwap_val)

    # Momentum confirmation: RSI
    rsi_val = rsi(close, window=rsi_window)

    # OI momentum confirmation
    oi_mom = oi_momentum(oi, window=oi_window)

    # Filter: funding rate z-score (crowded squeeze guard)
    funding_zscore = funding_rate_zscore(funding)

    # --- Composite signal ---
    # Long: supertrend up + EMA slope up + close above VWAP + RSI not extreme
    # Short: supertrend down + EMA slope down + close below VWAP + RSI not extreme
    long_trigger = (trend_signal > 0) & (slope > 0)
    short_trigger = (trend_signal < 0) & (slope < 0)

    long_conf = (vwap_dev > 0) & (rsi_val < rsi_ob) & (rsi_val > 50)
    short_conf = (vwap_dev < 0) & (rsi_val > rsi_os) & (rsi_val < 50)

    # OI momentum: confirm only if OI is not strongly against (filter out extreme crowding)
    oi_filter = (oi_mom * trend_signal) > oi_thresh

    # Funding filter: avoid crowded trades (z-score beyond threshold -> reduce/stop)
    funding_ok = np.abs(funding_zscore) < funding_z

    # Raw direction
    direction = np.where(long_trigger & long_conf & oi_filter & funding_ok, 1.0, 0.0)
    direction = np.where(short_trigger & short_conf & oi_filter & funding_ok, -1.0, direction)

    # --- Volatility-based sizing ---
    atr_val = atr(high, low, close, window=atr_window)
    vol_estimate = safe_div(atr_val, close)
    size = safe_div(vol_target, vol_estimate)
    size = np.clip(size, 0.0, max_leverage)

    # Apply direction * size
    target_weights = direction * size

    # --- Reason log ---
    weight_reason = []
    for i in range(len(data)):
        if direction[i] > 0:
            reason = "LONG|trend+vol_conf+oi+fund_ok"
        elif direction[i] < 0:
            reason = "SHORT|trend+vol_conf+oi+fund_ok"
        else:
            reason = "FLAT|no_signal_or_filter"
        weight_reason.append(reason)

    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": weight_reason,
    }