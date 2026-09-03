---
name: alpha-patterns
description: Industrial quantitative strategy architectural patterns and signal generation logic. Read when designing trend-following, breakout, mean-reversion, or regime-switching strategies.
---

# Quantitative Alpha Strategy Patterns

Every strategy MUST follow the platform contract:
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

## Pattern 1: Dual-Momentum Trend Following with Volatility Filter

Best for trending markets; filters whipsaws during low-volume consolidation.

```python
import numpy as np
import pandas as pd
from backtest.indicators import ema, atr

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    fast_period = int(params.get("fast_period", 20))
    slow_period = int(params.get("slow_period", 50))
    atr_mult = float(params.get("atr_mult", 2.5))
    
    close = data["close"]
    fast_ema = ema(close, window=fast_period)
    slow_ema = ema(close, window=slow_period)
    vol_atr = atr(data["high"], data["low"], close, window=14)
    
    # Trend direction
    is_bullish = (fast_ema > slow_ema) & (close > slow_ema)
    is_bearish = (fast_ema < slow_ema) & (close < slow_ema)
    
    target_weights = np.zeros(len(data), dtype=float)
    weight_reason = np.full(len(data), "Flat", dtype=object)
    
    target_weights[is_bullish] = 1.0
    weight_reason[is_bullish] = "Bullish Trend"
    
    target_weights[is_bearish] = -1.0  # Or 0.0 if long-only
    weight_reason[is_bearish] = "Bearish Trend"
    
    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": weight_reason.tolist(),
    }
```

---

## Pattern 2: Volatility Breakout (Donchian / Keltner)

Captures structural regime shifts and explosive momentum breakouts.

```python
import numpy as np
import pandas as pd
from backtest.indicators import atr

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    channel_period = int(params.get("channel_period", 24))
    
    # CRITICAL: shift(1) prevents looking ahead to the breakout bar's extreme
    upper_channel = data["high"].rolling(channel_period).max().shift(1)
    lower_channel = data["low"].rolling(channel_period).min().shift(1)
    
    close = data["close"]
    target_weights = np.zeros(len(data), dtype=float)
    weight_reason = np.full(len(data), "Neutral Channel", dtype=object)
    
    breakout_up = close > upper_channel
    breakout_down = close < lower_channel
    
    target_weights[breakout_up] = 1.0
    weight_reason[breakout_up] = "Upper Breakout"
    
    target_weights[breakout_down] = 0.0  # Exit to flat or short
    weight_reason[breakout_down] = "Lower Channel Exit"
    
    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": weight_reason.tolist(),
    }
```

---

## Pattern 3: Mean Reversion with Statistical Z-Score & Volatility Bands

Best in ranging or sideways regimes; captures overextended deviations.

```python
import numpy as np
import pandas as pd
from backtest.indicators import zscore, rsi

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    lookback = int(params.get("lookback", 20))
    z_entry = float(params.get("z_entry", 2.0))
    
    close = data["close"]
    z = zscore(close, window=lookback)
    rsi_14 = rsi(close, window=14)
    
    target_weights = np.zeros(len(data), dtype=float)
    weight_reason = np.full(len(data), "Range Mid", dtype=object)
    
    # Oversold entry
    long_mask = (z < -z_entry) & (rsi_14 < 35)
    # Overbought exit
    short_or_flat_mask = (z > z_entry) | (rsi_14 > 70)
    
    target_weights[long_mask] = 1.0
    weight_reason[long_mask] = "Oversold Bounce"
    
    target_weights[short_or_flat_mask] = 0.0
    weight_reason[short_or_flat_mask] = "Overbought Exit"
    
    return {
        "target_weights": target_weights.tolist(),
        "weight_reason": weight_reason.tolist(),
    }
```

---

## Pattern 4: Regime-Adaptive Switching

Switches between Trend Following and Mean Reversion according to market regime (ATR / Bandwidth).

```python
# Measure market regime
atr_pct = vol_atr / close
high_vol_regime = atr_pct > atr_pct.rolling(100).median()

# Trending Regime -> apply trend logic
# Range Regime -> apply mean-reversion or stay in cash
```

---

## Common Implementation Pitfalls to Avoid:
1. **List Slicing Error**:
   - ❌ `weight_reason = [""] * len(data); weight_reason[mask] = "Buy"` (Causes TypeError: only integer scalar arrays can be converted to a scalar index).
   - ✅ `weight_reason = np.full(len(data), "", dtype=object); weight_reason[mask] = "Buy"`
2. **Missing Shifting on Channels**:
   - ❌ `data["high"].rolling(20).max()` on the current bar includes the current bar itself!
   - ✅ `data["high"].rolling(20).max().shift(1)`
