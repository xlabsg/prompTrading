---
name: data-exploration
description: Inspect the active market dataset (frequency, volatility, price range, ATR) using `pt-quant inspect-data` before coding. Read first when starting a new strategy or adapting to an unknown asset.
---

# Market Data Exploration & Profile Inspection

Do NOT guess the time interval, volatility, or price scale of the asset you are trading.
Different market regimes and bar intervals (e.g. 15m vs 1h vs 1d) require completely different indicator lookbacks.

## 1. How to Inspect Active Dataset

Run `pt-quant inspect-data` via terminal `bash`:
```bash
pt-quant inspect-data
```
Or for programmatic JSON output:
```bash
pt-quant inspect-data --json
```

This returns:
- **Symbol & Exchange**: The exact trading pair (e.g. `BTC-USDT-SWAP` on `okx`).
- **Interval & Total Bars**: Bar duration (e.g. `1h`) and sample size (e.g. `2000` bars).
- **Time Range**: Start date/time to End date/time.
- **Annualized Volatility**: Asset annualized volatility percentage.
- **ATR(14) and % of Price**: Average True Range and its relative percentage to current price.
- **NaN Check**: Verifies whether data is clean without missing bars.

## 2. Setting Lookback Parameters According to Bar Interval

Always align indicator periods with the actual time frequency:

| Bar Interval | 1 Day Lookback | 1 Week Lookback | Fast Signal | Slow Signal |
| :--- | :--- | :--- | :--- | :--- |
| **15m** | 96 bars | 672 bars | 16 - 32 bars (~4h) | 96 - 192 bars (~1-2 days) |
| **1h** | 24 bars | 168 bars | 12 - 24 bars (~0.5-1 day) | 48 - 96 bars (~2-4 days) |
| **4h** | 6 bars | 42 bars | 6 - 12 bars (~1-2 days) | 24 - 42 bars (~4-7 days) |
| **1d** | 1 bar | 7 bars | 5 - 10 bars | 20 - 50 bars |

> [!TIP]
> If trading high volatility assets (Annualized Vol > 70%), widen your ATR stop multiples (e.g., 3.0x - 4.0x ATR) to avoid premature stop-outs during intraday noise.
