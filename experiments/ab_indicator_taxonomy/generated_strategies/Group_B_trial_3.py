import numpy as np
import pandas as pd

def generate_signals(data: pd.DataFrame, params: dict) -> dict[str, list]:
    # Strategy: Trend-following with volatility regime filter and momentum confirmation
    
    # --- Indicator calculations (vectorized, no lookahead) ---
    close = data['close']
    high = data['high']
    low = data['low']
    volume = data['volume']
    funding = data['funding_rate']
    oi = data['open_interest']
    
    # Trend: Supertrend (default params)
    st_period = params.get('st_period', 10)
    st_mult = params.get('st_mult', 3.0)
    st = supertrend(high, low, close, period=st_period, multiplier=st_mult)
    
    # Momentum: RSI and stochastic RSI
    rsi_period = params.get('rsi_period', 14)
    rsi_val = rsi(close, window=rsi_period)
    stoch_rsi_val = stoch_rsi(close, rsi_window=14, stoch_window=14)
    
    # Volatility: ATR for regime filter and Bollinger for mean-reversion context
    atr_val = atr(high, low, close, window=14)
    bb_mid, bb_upper, bb_lower = bollinger_bands(close, window=20, num_std=2.0)
    
    # Volume: CMF to confirm trend strength
    cmf_val = cmf(high, low, close, volume, window=20)
    
    # Derivatives: OI momentum and funding regime
    oi_mom = oi_momentum(oi, window=24)
    funding_z = funding_rate_zscore(funding, window=72)
    
    # --- Composite signals ---
    # 1. Trend direction from supertrend (1=up, -1=down)
    trend_dir = np.where(st > 0, 1.0, -1.0)  # supertrend returns +value for uptrend, -value for downtrend
    
    # 2. Momentum score: combine RSI momentum and stochastic RSI
    rsi_component = np.where(rsi_val > 50, 1.0, -1.0)
    stoch_component = np.where(stoch_rsi_val > 0.5, 1.0, -1.0)
    momentum_score = (rsi_component + stoch_component) / 2.0
    
    # 3. Volatility regime: scale down positions in high vol (ATR percentile)
    atr_ma = sma(atr_val, window=100)
    vol_regime = np.where(atr_val < atr_ma, 1.0, 0.5)  # reduce in high vol
    
    # 4. Volume confirmation: only full weight if CMF positive in uptrend, negative in downtrend
    cmf_conf = np.where((trend_dir > 0) & (cmf_val > 0), 1.0,
                        np.where((trend_dir < 0) & (cmf_val < 0), 1.0, 0.5))
    
    # 5. Derivatives filter: avoid longs when OI momentum strongly negative and funding very high
    oi_filter = np.where((trend_dir > 0) & (oi_mom < -0.5), 0.5, 1.0)
    funding_filter = np.where((trend_dir > 0) & (funding_z > 2.0), 0.5, 1.0)
    
    # Combine into raw target weight (between -1 and 1)
    raw_weight = trend_dir * momentum_score * vol_regime * cmf_conf * oi_filter * funding_filter
    
    # --- Smoothing and clipping ---
    # Apply EMA to reduce turnover / whipsaws
    window_smooth = params.get('smooth_window', 3)
    target = ema(pd.Series(raw_weight), window=window_smooth).fillna(0.0)
    
    # Clip to [-1, 1] and apply optional max leverage
    max_lev = params.get('max_leverage', 1.0)
    target_weights = np.clip(target.values, -max_lev, max_lev)
    
    # --- Reason string for each bar (optional but useful) ---
    weight_reason = []
    for i in range(len(data)):
        if target_weights[i] > 0.3:
            reason = "Long: trend up, momentum bullish"
        elif target_weights[i] < -0.3:
            reason = "Short: trend down, momentum bearish"
        else:
            reason = "Neutral/Reduced risk"
        weight_reason.append(reason)
    
    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": weight_reason,
    }