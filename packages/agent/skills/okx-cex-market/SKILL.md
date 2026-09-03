---
name: okx-cex-market
description: OKX Exchange market data, order books, funding rates, open interest, and 70+ official built-in technical indicators. Read when designing indicators or screening crypto market regimes.
---

# OKX CEX Market & Technical Indicators Reference

The OKX Agent Trade Kit provides comprehensive public market data endpoints and over 70 pre-calculated technical indicators that do not require API authentication.

## 1. 70+ Pre-Calculated Technical Indicators

OKX calculates standard and advanced indicators directly on exchange candles. When designing strategies or verifying signals, use these standard indicators:

### Core Momentum & Trend Indicators
- `MA` (Moving Average): Simple moving average of closing prices.
- `EMA` (Exponential Moving Average): Weighted moving average giving higher weight to recent prices.
- `RSI` (Relative Strength Index): Momentum oscillator measuring speed and change of price movements (range 0-100, default period 14).
- `MACD` (Moving Average Convergence Divergence): Trend-following momentum indicator (fast=12, slow=26, signal=9).
- `KDJ` (Stochastic Oscillator): Momentum indicator with %K, %D, %J lines for overbought/oversold conditions.
- `DMI` / `ADX` (Directional Movement Index): Trend strength and direction.
- `SAR` (Parabolic Stop and Reverse): Trailing stop and reversal price points.

### Volatility & Volume Indicators
- `BOLL` / `BB` (Bollinger Bands): Volatility bands with upper, middle, and lower bands based on standard deviations.
- `ATR` (Average True Range): Volatility indicator measuring market range across bars.
- `OBV` (On-Balance Volume): Cumulative volume indicator measuring buying and selling pressure.
- `VOL` (Volume MA): Volume moving average comparison.

### Macro & Sentiment Indicators
- `BTCRAINBOW` (Bitcoin Rainbow Chart): Logarithmic regression curves identifying Bitcoin cycle stages.
- `AHR999` (AHR999 Hoarding Indicator): Valuation index assessing accumulation vs buying opportunities for BTC.

## 2. Market Filters & Screening

OKX Market tools allow screening coins by real-time quantitative metrics:
- **Funding Rate**: Real-time perpetual swap funding rate (e.g., funding rate > 0.01% indicates heavy long bias).
- **Open Interest (OI) & OI Change**: Aggregate open interest expansion/contraction indicating new money inflow or liquidation cascade.
- **Volume & Price Change**: Filter by 24h trading volume, top gainers/losers, or market cap ranking.

## 3. Best Practices in Strategy Design
- Always align timeframe (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`) with strategy horizon.
- Ensure all indicator calculations in `strategy.py` operate vectorially over historical rows up to bar `t`, avoiding lookahead bias.
