---
name: quant-indicators
description: Platform-supported vectorized technical indicators, parameter conventions, and pandas calculations. Read when calculating momentum, trend, volatility, or mean-reversion signals without lookahead bias.
---

# Platform Technical Indicators Reference

All indicator functions should operate on standard bar data (`pd.DataFrame`) with columns:
`['timestamp', 'open', 'high', 'low', 'close', 'volume']`.

Available pre-built indicators from `backtest.indicators` (or vectorized pandas implementations):

## 1. Moving Averages & Trend
- **SMA**: `close.rolling(window).mean()`
- **EMA**: `close.ewm(span=window, adjust=False).mean()`
- **MACD**:
  ```python
  ema_fast = close.ewm(span=12, adjust=False).mean()
  ema_slow = close.ewm(span=26, adjust=False).mean()
  macd_line = ema_fast - ema_slow
  signal_line = macd_line.ewm(span=9, adjust=False).mean()
  hist = macd_line - signal_line
  ```

## 2. Momentum & Oscillators
- **RSI**:
  ```python
  delta = close.diff()
  gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
  loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
  rs = gain / (loss + 1e-9)
  rsi = 100 - (100 / (1 + rs))
  ```
- **Z-Score (Standardized Distance)**:
  ```python
  rolling_mean = close.rolling(window=20).mean()
  rolling_std = close.rolling(window=20).std()
  zscore = (close - rolling_mean) / (rolling_std + 1e-9)
  ```

## 3. Volatility & Bands
- **Bollinger Bands**:
  ```python
  mid = close.rolling(window=20).mean()
  std = close.rolling(window=20).std()
  upper = mid + 2.0 * std
  lower = mid - 2.0 * std
  bandwidth = (upper - lower) / (mid + 1e-9)
  ```
- **ATR (Average True Range)**:
  ```python
  tr1 = high - low
  tr2 = (high - close.shift(1)).abs()
  tr3 = (low - close.shift(1)).abs()
  tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
  atr = tr.rolling(window=14).mean()
  ```

## Strict Lookahead Prohibition (Zero Tolerance)
- NEVER use future data: NO `shift(-1)`, NO `bfill()`, NO future window rolling.
- At bar `t`, decisions can ONLY use information available at or before `t`.
- When calculating signals on bar closes, the target position will be executed on the next available interval.
