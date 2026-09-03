---
name: okx-cex-smartmoney
description: OKX Smart Money analytics, top trader leaderboard metrics, and consensus signal generation. Read when developing sentiment-based or smart-money following alpha strategies.
---

# OKX Smart Money & Sentiment Alpha Reference

OKX Agent Trade Kit provides smart money analytics aggregating top trader performance, consensus positioning, and whale fund movements.

## 1. Top Trader Leaderboards
- **Ranking Metrics**:
  - `pnl`: Cumulative net profit in USD.
  - `pnlRatio`: Return on Investment (ROI) percentage.
  - `winRatio`: Percentage of profitable closed trades over rolling periods (7d, 30d, 90d).
  - `mdd`: Maximum drawdown percentage over the evaluated window.
- **Trader Position Tracking**:
  - Long/short bias ratio among the top 100 profitable accounts.
  - Average holding duration and leverage distribution.

## 2. Consensus Signal Generation
- **Whale / Smart Money Flow**:
  - Significant net buying or net selling by large accounts on perpetual contracts.
  - Large orderbook imbalances (bids vs asks depth ratio) near key support/resistance zones.
- **Contrarian vs Trend-Following Applications**:
  - *Extreme Consensus*: When retail long ratio exceeds 80% while smart money is reducing longs, high risk of long liquidation cascades.
  - *Breakout Confirmation*: When price breaks resistance simultaneously accompanied by smart money net inflow, signals high-probability trend continuation.

## 3. Implementation in Strategy Code
```python
# Conceptual smart money integration in strategy decision:
# If price momentum is bullish and market sentiment/funding supports upside:
if momentum_score > 0 and funding_rate < 0.0003:
    target_weights = 1.0  # Full long exposure
elif momentum_score < 0 and funding_rate > 0.0005:
    target_weights = -1.0  # Full short exposure
else:
    target_weights = 0.0  # Neutral / Cash
```
