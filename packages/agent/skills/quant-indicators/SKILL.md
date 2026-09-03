---
name: quant-indicators
description: Platform-supported vectorized technical indicators, atomic time-series operators, parameter conventions, and TA-Lib integration. Read when calculating signals without lookahead bias.
---

# Platform Technical Indicators & Quantitative Operators Reference

All indicators operate on standard market data (`pd.DataFrame`), which includes standard OHLCV columns (`['timestamp', 'open', 'high', 'low', 'close', 'volume']`) as well as crypto derivative columns when available (`['funding_rate', 'open_interest']`).

```python
# Both import styles are fully supported:
from backtest import indicators
import ta
```

---

## 1. Introspecting Available Indicators via CLI

Run `pt-quant indicators` to list all built-in indicators and inspect specific functions:
```bash
# List all platform indicators categorized
pt-quant indicators

# Check exact parameter signature and docstring
pt-quant indicators supertrend
pt-quant indicators ts_corr
pt-quant indicators vwap
```

---

## 2. Layer 1: Atomic Time-Series Operators (Alpha 101/Qlib Primitives)

Universal mathematical building blocks for custom factor design and signal transformation:

```python
from backtest.indicators import (
    ts_rank,          # Rolling percentile rank in [0.0, 1.0]
    ts_corr,          # Rolling Pearson correlation between 2 series
    ts_cov,           # Rolling covariance
    ts_decay_linear,  # Linearly weighted moving average (weights 1, 2, ..., w)
    ts_max, ts_min,   # Rolling extrema
    ts_diff,          # Period differences: x - x.shift(k)
    ts_returns,       # Period returns: x.pct_change(k)
    safe_div,         # Zero-division safe quotient (handles nan/inf)
)

# Example: Rolling Price-Volume Correlation (exhaustion / divergence detection)
pv_corr = ts_corr(data["close"], data["volume"], window=20)

# Example: Percentile Rank of Volatility (regime classification)
atr_rank = ts_rank(data["high"] - data["low"], window=60)

# Example: Linearly weighted momentum
momentum = ts_decay_linear(data["close"].pct_change(), window=10)
```

---

## 3. Layer 2: Modern Quant & Crypto Technical Indicators

Pre-built, vectorized, lookahead-free indicators:

```python
from backtest.indicators import (
    supertrend,        # Lookahead-safe SuperTrend -> (supertrend, direction)
    vwap,              # Volume-Weighted Average Price (cumulative or rolling)
    keltner_channel,   # Keltner Channel -> (upper, middle, lower)
    donchian_channel,  # Shifted lookahead-free Donchian Channel -> (upper, middle, lower)
    stoch_rsi,         # Stochastic RSI -> (k, d)
    cmf,               # Chaikin Money Flow
    bollinger_bands,   # Bollinger Bands -> (upper, middle, lower, bandwidth, percent_b)
    atr, rsi, ema, sma # Standard technical indicators
)

# 1. SuperTrend
st = supertrend(data["high"], data["low"], data["close"], period=10, multiplier=3.0)
# st.direction is +1.0 for bullish, -1.0 for bearish

# 2. VWAP
intraday_vwap = vwap(data["high"], data["low"], data["close"], data["volume"])
roll_vwap = vwap(data["high"], data["low"], data["close"], data["volume"], window=48)

# 3. Keltner & Donchian Channels (Strictly lookahead-safe)
kc = keltner_channel(data["high"], data["low"], data["close"], ema_window=20, atr_window=10)
dc = donchian_channel(data["high"], data["low"], window=24, shift=True)

# 4. Money Flow & Stochastic RSI
money_flow = cmf(data["high"], data["low"], data["close"], data["volume"], window=20)
srsi = stoch_rsi(data["close"], rsi_window=14, stoch_window=14)
```

---

## 4. Crypto Derivative Factor Helpers

When trading crypto perpetuals or futures, use derivative factors to detect squeeze and liquidity regimes:

```python
from backtest.indicators import funding_rate_zscore, oi_momentum

if "funding_rate" in data.columns:
    # Measures funding rate overbought/oversold squeeze risk (72 periods)
    fr_z = funding_rate_zscore(data["funding_rate"], window=72)

if "open_interest" in data.columns:
    # 24-period Rate of Change of Open Interest (OI)
    oi_roc = oi_momentum(data["open_interest"], window=24)
```

---

## 5. Layer 3: C-Accelerated TA-Lib Integration

The container has native `TA-Lib` installed with C-acceleration. The platform's wrapper automatically:
- Accepts `pd.Series` and `pd.DataFrame` directly.
- Translates parameter aliases seamlessly (`window=14` or `length=14` -> `timeperiod=14`).
- Preserves datetime index on returned Series and tuples of Series.

```python
import ta
# or: from backtest import indicators

macd, macdsignal, macdhist = ta.macd(data["close"], fastperiod=12, slowperiod=26, signalperiod=9)
adx_series = ta.adx(data["high"], data["low"], data["close"], window=14)
upper, middle, lower = ta.bbands(data["close"], window=20, nbdevup=2.0, nbdevdn=2.0)
```

---

## 6. Strict Lookahead Prohibition (Zero Tolerance)

Lookahead bias invalidates backtests and causes catastrophic live trading losses:
- **NO Negative Shifts**: Never use `shift(-k)`.
- **NO Backward Fills**: Never use `bfill()` or `fillna(method='bfill')`.
- **NO Future Aggregations**: At bar $t$, decisions can ONLY use information available at or before $t$.
- **Pre-execution Check**: Always run `pt-quant check strategy.py` before backtesting to verify no lookahead leaks exist.
