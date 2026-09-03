---
name: risk-management
description: Risk budgeting, volatility targeting, ATR trailing stops, deadbands, and position sizing. Read when sizing positions or controlling max drawdown.
---

# Risk Management & Position Sizing

In real quantitative trading, position sizing and risk control often matter more than the raw signal.
Proper risk management prevents liquidation, curtails drawdowns, and significantly improves the Sharpe Ratio.

---

## 1. Volatility Targeting (Inverse Volatility Sizing)

Instead of naive binary weights (`1.0` or `0.0`), scale your position inversely to recent realized volatility so every trade bears an equal risk budget:

```python
import numpy as np
import pandas as pd

# Annualized realized volatility for 1h bars
ann_factor = np.sqrt(365 * 24)
realized_vol = close.pct_change().rolling(30).std() * ann_factor

target_annual_vol = float(params.get("target_vol", 0.30))  # 30% volatility target
raw_scale = target_annual_vol / (realized_vol + 1e-6)

# Cap max leverage at 1.0 (or whatever max leverage is allowed)
position_size = np.clip(raw_scale, 0.1, 1.0)
target_weights = raw_signals * position_size
```

---

## 2. ATR Trailing Stop (Dynamic Profit & Loss Protection)

Lock in paper profits when price moves favorably, and cut losses when trend breaks:

```python
from backtest.indicators import atr

vol_atr = atr(data["high"], data["low"], data["close"], window=14)
atr_multiplier = float(params.get("atr_mult", 2.5))

# Compute highest high over lookback
highest_high = data["high"].rolling(20).max().shift(1)
trailing_stop = highest_high - (atr_multiplier * vol_atr)

# Force exit if price drops below trailing stop
stop_loss_hit = (data["close"] < trailing_stop) & (raw_signals > 0)
target_weights[stop_loss_hit] = 0.0
weight_reason[stop_loss_hit] = "ATR Trailing Stop"
```

---

## 3. Turnover Control & Deadband (Hysteresis)

High turnover incurs excessive exchange transaction fees and execution slippage, destroying an otherwise profitable strategy.
Use a **Deadband**: do not adjust position weight unless the new target delta exceeds a minimum threshold (e.g. 10% change).

```python
# Prevent micro-adjustments that churn fees
rebalance_threshold = float(params.get("rebalance_threshold", 0.10))

current_pos = 0.0
filtered_weights = np.zeros(len(data))

for i in range(len(data)):
    desired_pos = target_weights[i]
    if abs(desired_pos - current_pos) >= rebalance_threshold:
        current_pos = desired_pos
    filtered_weights[i] = current_pos

target_weights = filtered_weights
```

---

## 4. Key Rules of Thumb:
1. **Never scale beyond 1.0 or below -1.0** without explicit leverage permission.
2. **Always include weight_reason** explaining why a position was scaled, held, or exited.
3. **Verify Contract**: Run `pt-quant dry-run strategy.py` to ensure your risk sizing logic does not introduce `NaN` or shape mismatches.
