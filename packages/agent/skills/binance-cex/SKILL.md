---
name: binance-cex
description: Binance Exchange trading rules, contract specifications, lot size precision filters, and CLI operations. Read when developing or verifying Binance strategies.
---

# Binance Trading Rules & Precision Reference

This guide covers Binance Spot and USDⓈ-M Futures trading specifications, precision requirements, and CLI tool usage.

## 1. Symbol & Market Naming Conventions
- **Spot & Futures Symbols**: Plain concatenated ticker without separators (e.g. `BTCUSDT`, `ETHUSDT`, `SOLUSDT`).
- **Contrast with OKX**:
  - OKX format: `BTC-USDT-SWAP` (Perpetual), `BTC-USDT` (Spot).
  - Binance format: `BTCUSDT` (both Spot and USDⓈ-M Perpetual use `BTCUSDT`).

## 2. Filters & Execution Precision
Binance enforces strict order filters via `exchangeInfo`. Submitting orders that do not conform will be rejected with `Filter failure`:

### `PRICE_FILTER`
- `tickSize`: Minimum price increment (e.g. `0.10` for BTCUSDT).
- Price must satisfy: `(price - minPrice) % tickSize == 0`.

### `LOT_SIZE` / `MARKET_LOT_SIZE`
- `stepSize`: Minimum quantity step (e.g. `0.001` BTC).
- `minQty`: Minimum quantity allowed per order.
- Quantity must satisfy: `(quantity - minQty) % stepSize == 0`.

### `MIN_NOTIONAL` / `NOTIONAL`
- The nominal value `price * quantity` must exceed the threshold (typically `$5.0` to `$10.0` USD).

## 3. Position Modes & Sides
- **One-Way Mode**: `positionSide = "BOTH"`. Single net position per symbol (positive size = Long, negative size = Short).
- **Hedge Mode**: `positionSide = "LONG"` or `positionSide = "SHORT"`. Simultaneous long and short positions on the same contract.
- *Default in platform*: The platform's `BinanceAdapter` automatically maps orders and parses net/hedge positions transparently.

## 4. Binance CLI Tool Usage (Terminal / Bash)
When `binance-cli` is installed:
```bash
# Check price ticker
binance-cli spot ticker --symbol BTCUSDT

# Inspect open orders
binance-cli futures open-orders --symbol BTCUSDT

# Query account balances
binance-cli futures balance
```
