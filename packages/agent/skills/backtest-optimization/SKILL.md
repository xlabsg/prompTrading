---
name: backtest-optimization
description: Diagnose backtest metrics, troubleshoot bottlenecks, and follow disciplined iteration. Read after calling backtest or before parameter fine-tuning.
---

# Backtest Diagnostics & Iterative Optimization

Backtests are limited by an evaluation budget (e.g. 5 runs). Spend every run deliberately.
**Never** change random numbers without an economic hypothesis.

---

## 1. Diagnostic Decision Tree

### Issue A: Low Sharpe Ratio (< 0.8)
- **Check Trade Count**:
  - If `< 5` trades over 1000+ bars: Your entry condition is too strict. Loosen parameters (e.g., lower RSI threshold, shorten EMA periods).
  - If `> 200` trades: Overtrading on noise. Add a trend filter (e.g., ADX > 20 or `close > 50-EMA`) or implement a minimum deadband.
- **Check Win Rate vs Profit Factor**:
  - High win rate (>65%) but low profit factor (<1.1): The strategy lets losses run while cutting winners short. Add an ATR trailing stop.
  - Low win rate (<40%) with high profit factor (>1.8): Typical of trend following. Ensure you have enough bars to capture large tails.

### Issue B: Severe Max Drawdown (> 25%)
- **Remedy 1**: Add Volatility Scaling (read `.tau/skills/risk-management/SKILL.md`).
- **Remedy 2**: Tighten exit rules — exit when the fast moving average crosses under the slow moving average instead of waiting for a stop loss.
- **Remedy 3**: Add Regime Detection — do not trade during low-volatility chop.

### Issue C: Unrealistic Sharpe Ratio (> 3.5)
- **Warning**: Almost certainly a bug or lookahead leakage!
- Run:
  ```bash
  pt-quant check strategy.py
  ```
- Inspect whether you accidentally used `shift(-1)` or evaluated future prices.

---

## 2. Recommended Workflow with `pt-quant`

Before spending a precious `backtest` run:
```bash
# 1. Check syntax, imports, and lookahead leaks
pt-quant check strategy.py

# 2. Verify return dictionary structure and array length in-memory
pt-quant dry-run strategy.py
```
Only when both succeed, call the `backtest` tool.

---

## 3. The 3-Run Stall Rule
If 3 consecutive backtest runs do not improve your primary target score (`sharpe_ratio`), **STOP tweaking parameters**.
Over-optimizing on the cached dataset causes severe out-of-sample degradation. Proceed to write `overview.md` and call `task_done`.
