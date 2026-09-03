---
name: backtest-optimization
description: How to interpret backtest reports, diagnose Sharpe and Drawdown bottlenecks, and iterate on strategy parameters without overfitting. Read after calling backtest.
---

# Backtest Report Interpretation & Strategy Iteration

## 1. Primary Evaluation Metrics
When `backtest` finishes, evaluate:
- **Sharpe Ratio**: Annualized excess return per unit of volatility.
  - `< 0.8`: Sub-optimal or noisy.
  - `1.0 - 1.5`: Solid baseline.
  - `> 2.0`: Strong, but check for lookahead bias or overfitting.
- **Max Drawdown (MDD)**: Maximum peak-to-trough decline.
  - If MDD > 25%, look into adding a trend filter or tighter ATR trailing stop.
- **Win Rate vs Profit Factor**: High win rate with huge single losses indicates missing stop-loss; low win rate with high profit factor indicates trend-following behavior.
- **Total Trades / Turnover**: Fewer than 5 trades over 500+ bars is statistically insignificant; more than 1 trade every 2 bars is likely overtrading on noise.

## 2. Iteration Discipline (Avoiding Overfitting)
- **Limit Parameter Search**: Adjust parameters based on market hypotheses, NOT by brute-force sweeping numbers.
- **Stall Limit**: If 3 consecutive backtest runs do not improve Sharpe ratio, STOP parameter tweaking and finalize the strategy. Over-optimizing on the cached dataset causes severe out-of-sample degradation.
- **Robustness Check**: A parameter should be stable across neighbor values (e.g., if period=20 works, period=18 and period=22 should also be reasonably profitable, not catastrophically negative).
