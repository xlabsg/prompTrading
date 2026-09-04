---
name: alpha-patterns
description: Quantitative strategy architectural patterns and signal composition grammar. Read when designing trend-following, breakout, mean-reversion, regime-switching, or crypto derivative strategies.
---

# Quantitative Strategy Composition Grammar

> **CORE PRINCIPLE**: The snippets and modules below are **architectural building blocks (primitives)**, NOT static templates to copy verbatim. Every strategy you produce should be an original synthesis tailored specifically to the user's prompt, asset dynamics, and timeframe. Do not default to trivial moving-average crossovers.

Every platform strategy MUST satisfy the contract:
```python
def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    ...
    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": weight_reason.tolist()  # Or numpy array / list of strings
    }
```
`target_weights` are normalized between `-1.0` (100% short) and `+1.0` (100% long), with `0.0` being cash/flat.

---

## The 4-Dimensional Orthogonal Strategy Matrix

High-performing quantitative strategies are composed of 4 orthogonal dimensions:

```
┌─────────────────────────┐     ┌─────────────────────────┐
│  1. Regime Identifier   │ ──► │     2. Alpha Core       │
│ (Trend / Vol / Crowding)│     │(Momentum/Revert/Breakout│
└─────────────────────────┘     └────────────┬────────────┘
                                             │
┌─────────────────────────┐                  ▼
│    4. Dynamic Sizing    │ ◄── ┌─────────────────────────┐
│ (Continuous/Vol-Scaled) │     │  3. Filter/Confirmation │
└─────────────────────────┘     │(Volume/Derivatives/Risk)│
                                └─────────────────────────┘
```

---

### Pillar 1: Market Regime Identification

Classify whether the market is trending, consolidating, high-volatility, or crowded before applying signals:

```python
from backtest.indicators import atr, bollinger_bands, supertrend, ts_rank

# 1. Volatility Regime: Squeeze vs Expansion (Bollinger Bandwidth Percentile)
bb = bollinger_bands(data["close"], window=20)
is_vol_squeeze = ts_rank(bb.bandwidth, window=100) < 0.20  # In lowest 20% volatility
is_vol_expansion = ts_rank(bb.bandwidth, window=100) > 0.80

# 2. Trend Regime via SuperTrend or ADX
st = supertrend(data["high"], data["low"], data["close"], period=10, multiplier=3.0)
is_uptrend = st.direction == 1.0
is_downtrend = st.direction == -1.0

# 3. Crypto Derivative Crowding Regime (if funding_rate available)
if "funding_rate" in data.columns:
    fr_rank = ts_rank(data["funding_rate"], window=72)
    is_long_crowded = fr_rank > 0.90   # Extreme long crowding -> squeeze risk
    is_short_crowded = fr_rank < 0.10  # Extreme short crowding -> squeeze risk
```

---

### Pillar 2: Alpha Signal Cores

Select or synthesize the primary signal generator:

#### Option A: Cross-Metric Quant Alpha (Price-Volume Correlation)
```python
from backtest.indicators import ts_corr, ts_decay_linear

# Rolling correlation between close and volume over 20 bars
# When price rises but volume correlation drops -> volume exhaustion / reversal signal
pv_corr = ts_corr(data["close"], data["volume"], window=20)
smoothed_momentum = ts_decay_linear(data["close"].pct_change(), window=10)
```

#### Option B: Dynamic Breakout (Donchian / Keltner Channels)
```python
from backtest.indicators import donchian_channel, keltner_channel

# CRITICAL: Always use lookahead-safe channels (shifted by 1 bar)
dc = donchian_channel(data["high"], data["low"], window=24, shift=True)
breakout_long = data["close"] > dc.upper
breakout_short = data["close"] < dc.lower
```

#### Option C: Mean Reversion with Statistical Z-Score
```python
from backtest.indicators import zscore, rsi, stoch_rsi

z = zscore(data["close"], window=30)
srsi = stoch_rsi(data["close"], rsi_window=14, stoch_window=14)
oversold = (z < -2.0) & (srsi.k < 20.0)
overbought = (z > 2.0) & (srsi.k > 80.0)
```

#### Option D: Crypto Derivative Dislocation (Funding Rate & OI Squeeze)
```python
from backtest.indicators import funding_rate_zscore, oi_momentum

if "funding_rate" in data.columns and "open_interest" in data.columns:
    fr_z = funding_rate_zscore(data["funding_rate"], window=72)
    oi_roc = oi_momentum(data["open_interest"], window=24)
    # Price rising + OI dropping + high funding = Short Squeeze exhaustion -> Fade/Short
    squeeze_exhaustion = (data["close"] > data["close"].shift(12)) & (oi_roc < -0.05) & (fr_z > 2.0)
```

---

### Pillar 3: Confirmation & Anti-Whipsaw Filtering

Filter out false signals using secondary independent drivers:

```python
from backtest.indicators import vwap, cmf

# 1. Volume confirmation via Chaikin Money Flow (CMF)
money_flow = cmf(data["high"], data["low"], data["close"], data["volume"], window=20)
has_buying_pressure = money_flow > 0.05

# 2. Intraday institutional benchmark confirmation via VWAP
benchmark_vwap = vwap(data["high"], data["low"], data["close"], data["volume"])
above_vwap = data["close"] > benchmark_vwap

# 3. Time-decay volume filter
vol_ma = data["volume"].rolling(20).mean()
volume_filter = data["volume"] > 1.2 * vol_ma
```

---

### Pillar 4: Dynamic Position Sizing & Allocation

Move beyond naive binary (+1.0 / -1.0) allocations to maximize Sharpe ratio:

```python
import numpy as np

# Method 1: Continuous Linear Scaling from Signal Strength
# Maps z-score to continuous target weights [-1.0, 1.0] with clipping
raw_signal = -z / 3.0  # Mean reversion: high z -> negative weight
target_weights = np.clip(raw_signal, -1.0, 1.0)

# Method 2: Volatility-Targeted Inverse Sizing (Vol-Parity)
vol_atr = atr(data["high"], data["low"], data["close"], window=14)
norm_vol = vol_atr / data["close"]
median_vol = norm_vol.rolling(100).median()
vol_scale = np.clip(median_vol / (norm_vol + 1e-9), 0.3, 1.5)
target_weights = np.clip(raw_direction * vol_scale, -1.0, 1.0)
```

---

## Synthesis Example (Combining Pillars)

```python
import numpy as np
import pandas as pd
from backtest.indicators import (
    supertrend,
    donchian_channel,
    cmf,
    bollinger_bands,
    ts_rank,
)

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    channel_len = int(params.get("channel_len", 20))
    cmf_thresh = float(params.get("cmf_thresh", 0.02))

    close = data["close"]
    n = len(data)

    # 1. Regime: Volatility squeeze check
    bb = bollinger_bands(close, window=channel_len)
    is_expanding = ts_rank(bb.bandwidth, window=60) > 0.30

    # 2. Alpha Core: Channel breakout (lookahead-safe)
    dc = donchian_channel(data["high"], data["low"], window=channel_len, shift=True)

    # 3. Confirmation: Volume money flow
    flow = cmf(data["high"], data["low"], close, data["volume"], window=channel_len)

    # Combine
    long_condition = (close > dc.upper) & (flow > cmf_thresh) & is_expanding
    short_condition = (close < dc.lower) & (flow < -cmf_thresh) & is_expanding
    exit_condition = (close < dc.middle) & (close.shift(1) >= dc.middle)

    target_weights = np.zeros(n, dtype=float)
    weight_reason = np.full(n, "Cash", dtype=object)

    target_weights[long_condition] = 1.0
    weight_reason[long_condition] = "Breakout + Vol Expansion"

    target_weights[short_condition] = -1.0
    weight_reason[short_condition] = "Breakdown + Vol Expansion"

    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": weight_reason.tolist(),
    }
```

---

## Critical Rules to Prevent Backtest Failure:
1. **Always Use `np.full(len(data), '', dtype=object)` for `weight_reason`** (Never standard Python lists).
2. **Always Use `.shift(1)` for rolling channels** (Prevents lookahead leaks on breakout bars).
3. **Handle NaNs Gracefully** (Ensure indicators have completed warmup before generating non-zero weights).
