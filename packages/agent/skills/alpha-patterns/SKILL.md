---
name: alpha-patterns
description: Common quantitative strategy architectural patterns and signal generation logic. Read when designing trend-following, breakout, mean-reversion, or regime-switching strategies.
---

# Quantitative Strategy Alpha Patterns

## 1. Dual-Momentum Trend Following
- **Hypothesis**: Assets outperforming their historical averages tend to continue outperforming in trending markets.
- **Signal Logic**:
  - Compute fast EMA (e.g., 20) and slow EMA (e.g., 50).
  - Trend filter: Confirm `close > slow_ema` and `fast_ema > slow_ema`.
  - Target Weights: Long (+1.0) when bullish, Flat (0.0) or Short (-1.0) when trend reverses.
  - Optional confirmation: ADX > 25 (strong trend) or Volume expansion > 1.2x 20-period average volume.

## 2. Mean Reversion with Volatility Channel
- **Hypothesis**: Price deviations from moving averages beyond statistical boundaries will revert to the mean in range-bound regimes.
- **Signal Logic**:
  - Calculate Bollinger Bands (20 periods, 2.0 standard deviations) or Z-score of price.
  - Entry Oversold: `close < lower_band` and `rsi < 30` -> Long (+1.0).
  - Entry Overbought: `close > upper_band` and `rsi > 70` -> Short (-1.0) or Flat (0.0).
  - Exit condition: `close` crosses back across moving average (mid band).

## 3. Donchian / Volatility Breakout
- **Hypothesis**: Breaking out of N-period high/low with elevated volatility signifies the start of a structural regime transition.
- **Signal Logic**:
  - `upper_channel = high.rolling(window=20).max().shift(1)`
  - `lower_channel = low.rolling(window=20).min().shift(1)`
  - If `close > upper_channel`: Long (+1.0).
  - If `close < lower_channel`: Exit to 0.0 or Short (-1.0).

## 4. Regime-Adaptive Switching
- **Hypothesis**: Trend-following suffers during low-volatility chop; mean-reversion suffers during high-volatility breakouts.
- **Signal Logic**:
  - Measure volatility / regime via ATR / Close or Bollinger Bandwidth.
  - High Bandwidth / Trending -> Apply Trend Follower.
  - Low Bandwidth / Choppy -> Apply Mean Reversion or Hold Cash.
