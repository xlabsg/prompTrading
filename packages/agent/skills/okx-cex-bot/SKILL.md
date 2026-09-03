---
name: okx-cex-bot
description: OKX Native Trading Bot specifications covering Spot Grid, Contract (Futures) Grid, and DCA bots. Read when designing or parameterizing grid and recurring investment strategies.
---

# OKX Trading Bots Reference (Grid & DCA)

OKX provides native exchange-hosted trading bots that automate grid trading and dollar-cost averaging (DCA).

## 1. Grid Trading Bots

Grid trading automatically places a ladder of buy and sell limit orders within a defined price channel to profit from market volatility.

### Grid Types
- **Spot Grid**: Holds base currency and quotes (e.g. BTC/USDT). Sells when price climbs to a higher rung, buys when price drops to a lower rung. No liquidation risk beyond underlying asset price depreciation.
- **Contract / Futures Grid**: Operates on perpetual swaps (e.g. BTC-USDT-SWAP). Supports:
  - **Neutral Grid**: Opens shorts above current price, opens longs below current price.
  - **Long Grid**: Built with long positions for bull markets.
  - **Short Grid**: Built with short positions for bear markets.
  - Uses leverage (1x - 50x) with liquidation price monitoring.

### Key Parameters
- `minPrice`: Lower bound of the grid price range.
- `maxPrice`: Upper bound of the grid price range.
- `gridNum`: Number of grid rungs (typically 2 to 200).
- `runType`:
  - `1`: Arithmetic grid (equal dollar spacing between rungs: `\Delta P = (maxPrice - minPrice) / gridNum`).
  - `2`: Geometric grid (equal percentage spacing between rungs: `ratio = (maxPrice / minPrice) ** (1 / gridNum)`).
- `tpTriggerPx` / `slTriggerPx`: Take-profit and stop-loss price levels that cancel all open grid orders and liquidate positions to quote asset.

## 2. DCA (Dollar-Cost Averaging) Bots

DCA bots accumulate assets systematically or execute Martingale strategies during market pullbacks.

### DCA Parameters
- `investment_interval`: Time frequency for recurring purchases (e.g. daily, weekly, hourly).
- `safety_orders`: Multi-tiered dip buying scale (e.g., buy 1.5x larger volume on each 3% price drop).
- `take_profit_target`: Target percentage return (e.g., 2% average price markup) before locking profits and restarting cycle.

## 3. Best Practices
- **Volatility vs Range**: Match grid width (`maxPrice - minPrice`) with ATR (Average True Range). Grids that are too narrow incur slippage and fee drag; grids that are too wide experience low fill rates.
- **Risk Management**: Always set a stop-loss (`slTriggerPx`) when using contract grid to prevent liquidation during strong directional trends.
