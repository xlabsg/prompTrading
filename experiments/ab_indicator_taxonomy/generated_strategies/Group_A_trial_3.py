import numpy as np
import pandas as pd
from backtest.indicators import ema, atr, zscore, ts_rank, safe_div, cross_over, cross_under, supertrend, keltner_channel, ts_corr


def generate_signals(data: pd.DataFrame, params: dict) -> dict[str, list]:
    # ---------- Parameters ----------
    ema_fast = params.get("ema_fast", 20)
    ema_slow = params.get("ema_slow", 100)
    atr_window = params.get("atr_window", 14)
    atr_mult = params.get("atr_mult", 2.0)
    z_window = params.get("z_window", 30)
    z_thresh = params.get("z_thresh", 0.5)
    corr_window = params.get("corr_window", 24)
    corr_thresh = params.get("corr_thresh", -0.3)
    vol_window = params.get("vol_window", 48)
    vol_scale = params.get("vol_scale", 0.02)
    max_pos = params.get("max_pos", 0.9)
    trend_filter = params.get("trend_filter", True)

    close = data["close"]
    high = data["high"]
    low = data["low"]
    volume = data["volume"]

    # ---------- Indicators ----------
    ema_f = ema(close, ema_fast)
    ema_s = ema(close, ema_slow)
    atr_val = atr(high, low, close, atr_window)

    # Stochastic momentum via z-score of price vs its recent mean
    price_z = zscore(close, z_window)

    # Trend quality: correlation between price and time (R² proxy)
    time_idx = np.arange(len(close))
    price_corr = ts_corr(close, pd.Series(time_idx), corr_window)

    # Volatility scaling (target vol = 2% per hour)
    realized_vol = close.pct_change().rolling(vol_window).std()
    vol_scaler = np.clip(vol_scale / realized_vol, 0.5, 2.0)

    # Supertrend for strong trend confirmation
    st = supertrend(high, low, close, period=10, multiplier=3.0)

    # ---------- Core signals ----------
    # Trend direction
    trend = np.where(ema_f > ema_s, 1.0, -1.0)
    if trend_filter:
        # Only allow long if supertrend positive, short if negative
        trend = trend * np.where(st.direction > 0, 1.0, -1.0)

    # Momentum magnitude (normalized by ATR)
    mom = (close - ema_f).rolling(atr_window).mean()
    mom_signal = np.clip(mom / (atr_val + 1e-9), -1, 1)

    # Z-score mean reversion guard: fade extreme moves only if trend intact
    z_signal = np.where(price_z > z_thresh, -0.3, np.where(price_z < -z_thresh, 0.3, 0.0))

    # Trend quality filter: require positive correlation (uptrend) or negative (downtrend)
    corr_filter = np.where(price_corr > corr_thresh, 1.0, 0.0)

    # ---------- Combine ----------
    raw = trend * (0.6 * mom_signal + 0.4 * z_signal)
    raw = raw * corr_filter

    # Apply volatility targeting
    raw = raw * vol_scaler

    # ---------- Position sizing & smoothness ----------
    # Smooth with EMA to reduce churn
    raw_sm = ema(pd.Series(raw), 5)

    # Clip to max exposure
    target_weights = np.clip(raw_sm, -max_pos, max_pos)

    # Optional deadband to stay neutral when signal too small
    deadband = params.get("deadband", 0.05)
    target_weights = np.where(np.abs(target_weights) < deadband, 0.0, target_weights)

    # Reason string
    weight_reason = []
    for i in range(len(data)):
        if target_weights[i] > 0.1:
            reason = f"Long: trend={trend[i]:+.2f}, z={price_z.iloc[i]:+.2f}"
        elif target_weights[i] < -0.1:
            reason = f"Short: trend={trend[i]:+.2f}, z={price_z.iloc[i]:+.2f}"
        else:
            reason = "Neutral"
        weight_reason.append(reason)

    # Ensure no lookahead (all indicators are past-based)
    return {
        "target_weights": target_weights,
        "weight_reason": weight_reason,
    }