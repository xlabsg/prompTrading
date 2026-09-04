import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict[str, list]:
    # -------------------------------
    # 1. Preprocess and validate
    # -------------------------------
    df = data.copy()
    high = df['high']
    low = df['low']
    close = df['close']
    volume = df['volume']
    funding = df['funding_rate'].fillna(0.0)
    oi = df['open_interest'].fillna(0.0)

    # -------------------------------
    # 2. Trend Trigger (Supertrend)
    # -------------------------------
    # Supertrend parameters
    atr_period = params.get('atr_period', 10)
    multiplier = params.get('multiplier', 3.0)

    # ATR (Wilder's smoothing)
    tr = np.maximum(high - low, np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))))
    atr = tr.ewm(alpha=1/atr_period, min_periods=atr_period).mean()

    # Basic band calculations
    hl2 = (high + low) / 2.0
    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr

    upper_band = upper_basic.copy()
    lower_band = lower_basic.copy()
    supertrend = pd.Series(np.nan, index=df.index)

    # Iterative supertrend construction (no lookahead)
    for i in range(1, len(df)):
        # Upper band: keep previous unless new basic is lower (for uptrend)
        if upper_basic.iloc[i] < upper_band.iloc[i-1] or close.iloc[i-1] > upper_band.iloc[i-1]:
            upper_band.iloc[i] = upper_basic.iloc[i]
        else:
            upper_band.iloc[i] = upper_band.iloc[i-1]

        # Lower band: keep previous unless new basic is higher (for downtrend)
        if lower_basic.iloc[i] > lower_band.iloc[i-1] or close.iloc[i-1] < lower_band.iloc[i-1]:
            lower_band.iloc[i] = lower_basic.iloc[i]
        else:
            lower_band.iloc[i] = lower_band.iloc[i-1]

        # Determine supertrend value
        if np.isnan(supertrend.iloc[i-1]):
            supertrend.iloc[i] = lower_band.iloc[i]  # start with uptrend assumption
        elif supertrend.iloc[i-1] == upper_band.iloc[i-1]:
            # Previously in downtrend
            if close.iloc[i] > upper_band.iloc[i]:
                supertrend.iloc[i] = lower_band.iloc[i]  # flip to uptrend
            else:
                supertrend.iloc[i] = upper_band.iloc[i]
        else:
            # Previously in uptrend
            if close.iloc[i] < lower_band.iloc[i]:
                supertrend.iloc[i] = upper_band.iloc[i]  # flip to downtrend
            else:
                supertrend.iloc[i] = lower_band.iloc[i]

    # Trend signal: +1 if close above supertrend, -1 otherwise
    trend_signal = np.where(close > supertrend, 1.0, -1.0)

    # -------------------------------
    # 3. Momentum Confirmation (RSI & Volume Flow)
    # -------------------------------
    # RSI (14-period)
    rsi_period = params.get('rsi_period', 14)
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/rsi_period, min_periods=rsi_period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/rsi_period, min_periods=rsi_period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50.0)

    # Momentum score: RSI above 50 = bullish, below = bearish
    momentum_score = (rsi - 50.0) / 50.0  # range [-1, 1]

    # Volume Flow (simplified CMF-like)
    cmf_period = params.get('cmf_period', 20)
    mfm = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
    mfv = mfm * volume
    cmf = mfv.rolling(cmf_period).sum() / volume.rolling(cmf_period).sum().replace(0, np.nan)
    cmf_score = cmf.fillna(0.0).clip(-1, 1)

    # -------------------------------
    # 4. Funding Rate Filter (Squeeze Avoidance)
    # -------------------------------
    funding_z = (funding - funding.rolling(48).mean()) / funding.rolling(48).std().replace(0, np.nan)
    funding_z = funding_z.fillna(0.0).clip(-3, 3)

    # Crowded long filter: if funding extremely high, reduce long exposure
    funding_filter = np.where(funding_z > 2.0, 0.3, 1.0)  # scale down longs
    funding_filter = np.where(funding_z < -2.0, 0.3, funding_filter)  # scale down shorts

    # -------------------------------
    # 5. Volatility Sizing (ATR-based)
    # -------------------------------
    vol_period = params.get('vol_period', 48)
    vol_ma = atr.rolling(vol_period).mean()
    vol_ratio = (vol_ma / atr).fillna(1.0).clip(0.5, 2.0)  # <1 = high vol, <1 = low vol

    # -------------------------------
    # 6. Combine Signals
    # -------------------------------
    # Base target from trend * momentum
    base_signal = trend_signal * (0.6 + 0.4 * momentum_score)

    # Add volume flow confirmation (only when aligned with trend)
    volume_aligned = np.where(np.sign(cmf_score) == trend_signal, abs(cmf_score), 0.0)
    base_signal += 0.3 * volume_aligned * trend_signal

    # Apply funding filter (reduce exposure in crowded trades)
    filtered_signal = base_signal * funding_filter

    # Apply volatility sizing (scale down in high vol, scale up in low vol)
    target_weights = filtered_signal * vol_ratio

    # Clip to [-1, 1]
    target_weights = np.clip(target_weights, -1.0, 1.0)

    # -------------------------------
    # 7. Smoothing & Zero-Out Early
    # -------------------------------
    # Require at least 50 bars of history
    min_bars = 50
    target_weights[:min_bars] = 0.0

    # Optional EMA smoothing on weights to reduce turnover
    smooth_window = params.get('smooth_window', 3)
    if smooth_window > 1:
        target_series = pd.Series(target_weights).ewm(span=smooth_window, min_periods=1).mean()
        target_weights = target_series.values

    # -------------------------------
    # 8. Build Reason Strings
    # -------------------------------
    weight_reason = []
    for i in range(len(df)):
        if i < min_bars or abs(target_weights[i]) < 0.01:
            weight_reason.append("neutral")
        elif target_weights[i] > 0:
            reason = "long"
            if trend_signal[i] == 1 and momentum_score[i] > 0.2:
                reason += "_trend_mom"
            if cmf_score[i] > 0.3:
                reason += "_volflow"
            if funding_z[i] > 2.0:
                reason += "_funding_caution"
            weight_reason.append(reason)
        else:
            reason = "short"
            if trend_signal[i] == -1 and momentum_score[i] < -0.2:
                reason += "_trend_mom"
            if cmf_score[i] < -0.3:
                reason += "_volflow"
            if funding_z[i] < -2.0:
                reason += "_funding_caution"
            weight_reason.append(reason)

    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": weight_reason
    }