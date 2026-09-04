import numpy as np
import pandas as pd
from backtest.indicators import ema, rsi, atr, supertrend, ts_rank, safe_div

def generate_signals(data: pd.DataFrame, params: dict) -> dict[str, list]:
    high = data['high']
    low = data['low']
    close = data['close']
    volume = data['volume']
    funding_rate = data['funding_rate']

    # --- Trend filter: Supertrend (multi-timeframe bias) ---
    st_period = int(params.get('st_period', 10))
    st_mult = float(params.get('st_mult', 3.0))
    st_dir, st_line = supertrend(high, low, close, period=st_period, multiplier=st_mult)
    # st_dir: +1 for uptrend, -1 for downtrend

    # --- Momentum: RSI with regime smoothing ---
    rsi_window = int(params.get('rsi_window', 14))
    rsi_val = rsi(close, window=rsi_window)

    # --- Volatility: ATR for dynamic position sizing / risk gate ---
    atr_window = int(params.get('atr_window', 14))
    atr_val = atr(high, low, close, window=atr_window)

    # --- Trend strength: EMA slope (normalized by ATR) ---
    ema_fast = ema(close, window=20)
    ema_slow = ema(close, window=50)
    slope = safe_div(ema_fast - ema_slow, atr_val)

    # --- Volume confirmation: volume z-score via ts_rank ---
    vol_ratio = safe_div(volume, ema(volume, window=50))
    vol_rank = ts_rank(vol_ratio, window=20)

    # --- Funding rate contrarian filter (extreme positioning) ---
    fr_rank = ts_rank(funding_rate, window=72)

    # --- Build signal components ---
    # Trend & momentum core signal
    trend_up = (st_dir > 0)
    trend_dn = (st_dir < 0)
    mom_up = (rsi_val > 50) & (rsi_val < 75)  # avoid overbought blow-off
    mom_dn = (rsi_val < 50) & (rsi_val > 25)

    # Slope strength: require positive for long, negative for short
    slope_pos = slope > 0.05
    slope_neg = slope < -0.05

    # Volume confirmation: not low volume (rank > 0.2)
    vol_ok = vol_rank > 0.2

    # Funding rate: avoid crowded longs if extremely positive, avoid crowded shorts if extremely negative
    fr_not_too_long = fr_rank < 0.9
    fr_not_too_short = fr_rank > 0.1

    # --- Long condition ---
    long_cond = trend_up & mom_up & slope_pos & vol_ok & fr_not_too_long
    # --- Short condition ---
    short_cond = trend_dn & mom_dn & slope_neg & vol_ok & fr_not_too_short

    # --- Position scaling based on trend strength (slope) and volatility (ATR percentile) ---
    # ATR percentile via ts_rank to avoid over-leverage in high vol
    atr_rank = ts_rank(atr_val, window=100)
    vol_factor = 1.0 - 0.5 * atr_rank  # reduce size when vol is high

    # Base weight 0.75, adjusted by slope magnitude (capped)
    slope_abs = np.abs(slope)
    strength_factor = np.clip(slope_abs / 0.5, 0.5, 1.0)

    raw_weight = np.where(long_cond, 0.75 * strength_factor * vol_factor,
                 np.where(short_cond, -0.75 * strength_factor * vol_factor, 0.0))

    # --- Smooth transitions: use EMA of raw weight to avoid whipsaw ---
    target_weights = ema(pd.Series(raw_weight), window=3).values

    # --- Reason string ---
    reason = np.where(long_cond, "long_trend_mom",
            np.where(short_cond, "short_trend_mom",
            np.where((st_dir > 0), "neutral_trend_up", "neutral_trend_dn")))

    # Clip to [-1, 1]
    target_weights = np.clip(target_weights, -1.0, 1.0)

    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": reason.tolist()
    }