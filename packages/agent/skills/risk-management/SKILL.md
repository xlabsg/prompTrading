---
name: risk-management
description: Risk budgeting, volatility scaling, trailing stops, and target_weights sizing. Read when sizing positions or preventing large drawdowns.
---

# Risk Management & Position Sizing

## 1. Output Protocol: `target_weights`
The platform expects `generate_signals(data, params)` to return:
```python
return {"target_weights": target_weights.tolist()}
```
`target_weights` is a float sequence between `-1.0` (100% short) and `+1.0` (100% long), where `0.0` is cash/flat. The length of `target_weights` MUST exactly match `len(data)`.

## 2. Volatility Targeting / Inverse Volatility Sizing
Instead of binary `1.0` or `0.0`, scale position inversely with recent realized volatility:
```python
realized_vol = close.pct_change().rolling(20).std() * (365 * 24) ** 0.5  # annualized for 1h
target_annual_vol = params.get("target_vol", 0.30)  # 30% annualized vol target
raw_weight = target_annual_vol / (realized_vol + 1e-6)
scaled_weight = raw_weight.clip(0.0, 1.0)
```

## 3. ATR Trailing Stop / Volatility Exits
Protect accumulated unrealized profits:
- Calculate 14-period ATR.
- Trailing stop distance = `k * ATR` (typically `k` between 2.0 and 3.5).
- If price falls below highest high since entry minus `k * ATR`, force target weight to `0.0`.

## 4. Turnover & Transaction Cost Consideration
- Frequent whipsawing degrades real Sharpe ratio due to slippage and fees.
- Use hysteresis or deadbands: do not change target weight unless the delta exceeds a minimum rebalance threshold (e.g., `abs(new_weight - current_weight) > 0.10`).
