# Flow Right Strategy

High-frequency order flow trading strategy.

## Strategy Overview

- **Risk Level**: High
- **Trading Frequency**: High-frequency (sub-minute to minute)
- **Complexity**: 3/5 (Moderate-High)
- **Minimum Capital**: 500 USDT
- **Supported Exchanges**: OKX, Binance

## Strategy Logic

### Order Flow Analysis

Flow Right analyzes real-time buy/sell pressure to detect momentum shifts:

1. **Flow Imbalance**: [−1, 1]
   - +1 = All buying pressure
   - −1 = All selling pressure
   - Calculated from trade side and notional

2. **Multi-Timeframe Windows**
   - Short window (10s): Fast signal
   - Medium window (30s): Confirmation
   - Long window (60s): Trend context

3. **Composite Score**: Weighted sum across windows
   - Short window: 100% weight
   - Medium window: 70% weight
   - Long window: 50% weight

### Signal Generation

- **Long Signal**: Score > +0.3 (buying pressure)
- **Short Signal**: Score < −0.3 (selling pressure)
- **Exit**: Score crosses zero or time-based (5 min max)

### Trade Management

- **Entry**: With composite score threshold
- **Stop Loss**: 1.5x ATR from entry
- **Take Profit**: 2x ATR from entry (2:1 RR)
- **Time Exit**: 5 minutes max hold

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `flow_windows` | [10, 30, 60] | Time windows in seconds |
| `window_weights` | [1.0, 0.7, 0.5] | Weight per window |
| `score_threshold` | 0.3 | Min score for signal |
| `min_notional_usdt` | 1000 | Min notional for validity |
| `velocity_threshold_bps` | 5.0 | Min velocity (bps/sec) |
| `atr_period` | 14 | ATR calculation period |
| `atr_sl_multiplier` | 1.5 | ATR multiplier for SL |
| `position_size_pct` | 0.15 | Position size (% of margin) |

## Architecture

### FlowAnalyzer Class

For production HFT, use WebSocket trade stream:

```python
# Real-time analysis with trade stream
analyzer = FlowAnalyzer(FlowConfig(windows=[10, 30, 60]))

# On each trade:
state = analyzer.update(
    price=50000.0,
    side="buy",  # or "sell"
    notional=1000.0,  # USDT value
    timestamp_ms=1704067200000,
)

# Get current signal
if state["score"] > 0.3:
    # Enter long
```

### Bar-Based Analysis (Simplified)

For backtesting or lower-frequency trading:

```python
signal = analyze_flow_from_bars(
    history=df,  # OHLCV DataFrame
    windows=[10, 30, 60],
    score_threshold=0.3,
    atr_period=14,
)
```

## Best Practices

- **Capital**: Start with 500+ USDT
- **Leverage**: 5-20x depending on risk tolerance
- **Symbols**: BTC and ETH have best flow data
- **Timing**: Avoid low-volume periods
- **Monitoring**: Watch for score reversals

## Risks

- **High Frequency**: Many trades, accumulate fees
- **False Signals**: Flow can reverse quickly
- **Latency**: Real HFT needs <100ms execution
- **Slippage**: Fast moves = more slippage
- **Capital Intensity**: Needs sufficient notional

## Performance Notes

Expected characteristics:
- Win rate: 55-65%
- Average trade: 1-5 minutes
- Daily trades: 10-50 per symbol
- Fees: Significant factor (use maker orders)

## Usage

```python
from strategy_templates.templates.flow_right import create_live_strategy

# Create strategy instance
strategy = create_live_strategy()

# Initialize with context
strategy.initialize(context)

# Called automatically on each bar
strategy.on_bar(bar, history, broker)
```

## Backtest Results

TODO: Add backtest results after migration testing.
