---
name: quant-indicators
description: Platform-supported vectorized technical indicators, parameter conventions, and pandas calculations. Read when calculating momentum, trend, volatility, or mean-reversion signals without lookahead bias.
---

# Platform Technical Indicators Reference

All indicator functions operate on standard bar data (`pd.DataFrame`) with columns:
`['timestamp', 'open', 'high', 'low', 'close', 'volume']`.

## 1. Introspecting Available Indicators via CLI

Run `pt-quant indicators` to list all built-in indicators and inspect specific functions:
```bash
# List all platform indicators
pt-quant indicators

# Check exact parameter signature and docstring
pt-quant indicators rsi
pt-quant indicators atr
```

## 2. Using Pre-Built Platform Indicators (`backtest.indicators`)

The platform provides vectorized, lookahead-free indicators under `backtest.indicators`:

```python
from backtest.indicators import sma, ema, rsi, atr, zscore, cross_over, cross_under

# Simple Moving Average
fast_ma = sma(data["close"], window=10)

# Exponential Moving Average
slow_ma = ema(data["close"], window=30)

# Relative Strength Index (Wilder's smoothing)
rsi_val = rsi(data["close"], window=14)

# Average True Range (True Range smoothed with Wilder's method)
vol_atr = atr(data["high"], data["low"], data["close"], window=14)

# Standardized Z-Score
z_score = zscore(data["close"], window=20)

# Crossings (Lookahead-free boolean series)
golden_cross = cross_over(fast_ma, slow_ma)
death_cross = cross_under(fast_ma, slow_ma)
```

## 3. Custom Pandas / Vectorized Indicator Implementations

If you need indicators not directly in `backtest.indicators`, implement them using vectorized pandas operations:

### Bollinger Bands
```python
mid = data["close"].rolling(20).mean()
std = data["close"].rolling(20).std(ddof=0)
upper = mid + 2.0 * std
lower = mid - 2.0 * std
bandwidth = (upper - lower) / (mid + 1e-9)
```

### Donchian Channel
```python
# MUST shift(1) to avoid lookahead on the breakout bar!
upper_channel = data["high"].rolling(20).max().shift(1)
lower_channel = data["low"].rolling(20).min().shift(1)
```

### Average Directional Index (ADX) / Trend Strength
```python
up_move = data["high"] - data["high"].shift(1)
down_move = data["low"].shift(1) - data["low"]
plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
# smooth via 14-period EMA or Wilder's smoothing
```

## 4. Strict Lookahead Prohibition (Zero Tolerance)

Lookahead bias invalidates backtests and causes real-world strategy failure:
- **NO Negative Shifts**: Never use `shift(-k)`.
- **NO Backward Fills**: Never use `bfill()` or `fillna(method='bfill')`.
- **NO Future Aggregations**: At bar `t`, decisions can ONLY use information available at or before `t`.
- **Pre-execution Check**: Always run `pt-quant check strategy.py` before backtesting to verify no lookahead leaks exist.
