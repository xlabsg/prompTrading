# Trading SDK Quick Reference for LLMs

**Purpose**: This document provides a quick reference for AI assistants to understand the Trading SDK capabilities and where to find detailed documentation.

## Overview

The Trading SDK is a comprehensive risk management and order execution framework integrated into the PrompTrading. It provides:

- **侵入式风险控制** (Invasive Risk Control) - Orders are automatically validated and rejected if they violate risk rules
- **移动止损** (Trailing Stop Loss) - Automatically adjusts stop loss as price moves in profitable direction
- **动态 TP/SL** (Dynamic Take Profit/Stop Loss) - Calculates TP/SL based on support/resistance levels
- **对账机制** (Reconciliation) - Periodic synchronization with exchange to detect discrepancies
- **订单管理** (Order Management) - Snowflake ID generation, lifecycle tracking, stale order cleanup

## Documentation Structure

### Main Documentation Files

1. **TRADING_SDK_API.md** (~1200 lines)
   - Complete API reference designed for LLM consumption
   - Every class, method, parameter documented with examples
   - Read this for: API details, method signatures, usage examples

2. **README.md** (~1000 lines)
   - Feature overview, installation, quick start
   - Read this for: High-level understanding, basic usage patterns

3. **INTEGRATION_GUIDE.md** (~500 lines)
   - Step-by-step integration instructions
   - Read this for: How to integrate SDK into existing systems

4. **DESIGN.md** (~1500 lines)
   - Complete design documentation, architecture, design decisions
   - Read this for: Understanding why things work the way they do

## Quick Component Lookup

### Risk Control (`packages/trading_sdk/risk/`)
- **RiskValidator** - Validates orders against risk rules (9 checks)
- **StopLossManager** - Manages fixed and trailing stop loss
- **PositionManager** - Calculates TP/SL using support/resistance + ATR
- **DrawdownTracker** - Monitors account drawdown and daily loss

### Order Execution (`packages/trading_sdk/execution/`)
- **OrderManager** - Order lifecycle management
- **SnowflakeIDGenerator** - Generates unique client order IDs
- **Reconciler** - Syncs with exchange to detect discrepancies

### Monitoring (`packages/trading_sdk/monitoring/`)
- **PnLCalculator** - Accurate PnL calculation including fees
- **TradingMetrics** - Win rate, profit factor, Sharpe ratio

### State Management (`packages/trading_sdk/state/`)
- **TradingState** - Trading state data structure
- **StatePersistence** - Dual storage (Redis + PostgreSQL)

### Exchange Adapters (`packages/trading_sdk/adapters/`)
- **ExchangeAdapter** - Abstract base class
- **OKXAdapter** - OKX exchange implementation

## Common Use Cases

### 1. Initialize SDK with Risk Control
```python
from trading_sdk import RiskValidator, RiskConfig, TrailingStopConfig

config = RiskConfig(
    max_position_pct=50.0,
    stop_loss_pct=0.02,
    trailing_stop=TrailingStopConfig(enabled=True)
)

validator = RiskValidator(config)
```

### 2. Validate an Order Before Placement
```python
result = validator.validate_order(order_spec, positions, balance)
if result.approved:
    exchange.place_order(order_spec)
else:
    logger.warning(f"Order rejected: {result.violations}")
```

### 3. Calculate Dynamic TP/SL
```python
from trading_sdk import PositionManager, DynamicTPSLConfig

manager = PositionManager(DynamicTPSLConfig(enabled=True))
tp, sl = manager.calculate_tpsl(entry_price, side, sr, atr)
```

### 4. Track Trailing Stop
```python
from trading_sdk import StopLossManager

stop_manager = StopLossManager()
stop_manager.register_position(position_id, position, config, atr)
stop_manager.update(position_id, position, current_price)

if stop_manager.should_trigger(position_id, position, current_price):
    close_position(position)
```

### 5. Perform Reconciliation
```python
from trading_sdk import Reconciler

reconciler = Reconciler(exchange_adapter, order_manager)
result = reconciler.reconcile_orders(local_orders, symbol)

if result["discrepancies"]:
    logger.warning(f"Discrepancies found: {result['discrepancies']}")
```

## Integration Points

The SDK has been integrated into the following files:

### Backend Integration
- **services/api/app/trading_engine/enhanced_executor.py** - Integrates risk control into order placement
- **services/api/app/trading_engine/enhanced_monitor.py** - Integrates trailing stop and PnL tracking
- **services/api/app/trading_engine/enhanced_manager.py** - Integrates reconciliation mechanism
- **services/api/app/trading_engine/sdk_config.py** - Converts DB config to SDK config

### Database Integration
- **services/api/migrations/add_trading_sdk_fields.sql** - Database schema updates

### API Integration
- **services/api/app/routers/trading.py** - Exposes SDK configuration fields

### Frontend Integration
- **apps/web/src/components/console/LiveTradingView.tsx** - UI for SDK configuration

## Configuration Fields (Database & API)

### Risk Control
- `leverage` - Leverage multiplier (1-125x)
- `max_leverage` - Maximum allowed leverage
- `max_daily_loss_pct` - Maximum daily loss percentage
- `max_drawdown_pct` - Maximum drawdown percentage
- `require_stop_loss` - Whether stop loss is mandatory

### Trailing Stop
- `trailing_stop_enabled` - Enable trailing stop loss
- `trailing_activation_pct` - Profit % to activate trailing stop
- `trailing_distance_pct` - Trailing stop distance %

### Dynamic TP/SL
- `dynamic_tpsl_enabled` - Enable dynamic TP/SL based on S/R
- `use_support_resistance` - Use support/resistance for TP/SL
- `min_risk_reward` - Minimum risk/reward ratio
- `fallback_sl_pct` - Fallback SL percentage
- `fallback_tp_pct` - Fallback TP percentage

## When to Read Full Documentation

- **TRADING_SDK_API.md** - When you need exact method signatures, parameters, or return values
- **INTEGRATION_GUIDE.md** - When integrating SDK into new components or services
- **DESIGN.md** - When making architectural decisions or understanding design trade-offs
- **README.md** - When getting started or showing examples to users

## Key Design Principles

1. **Invasive Risk Control** - Orders can't bypass risk checks
2. **Fail-Safe Defaults** - Conservative defaults, explicit opt-out required
3. **Exchange Agnostic** - Adapter pattern for multi-exchange support
4. **State Persistence** - Dual storage for reliability and performance
5. **Idempotent Operations** - Safe to retry, no duplicate orders

## Performance Considerations

- **Redis Caching** - Hot data in Redis, cold data in PostgreSQL
- **Batch Operations** - Bulk order/position updates
- **Async Execution** - Reconciliation runs in background
- **Rate Limiting** - State saves are rate-limited to avoid DB pressure

## Getting Started for LLMs

**To help a user with Trading SDK**:

1. Read this quick reference first to understand capabilities
2. Read TRADING_SDK_API.md for specific API details
3. Check integration files to see how it's currently used
4. Refer to INTEGRATION_GUIDE.md for integration patterns

**To modify/extend the SDK**:

1. Read DESIGN.md to understand architecture
2. Read TRADING_SDK_API.md to understand existing APIs
3. Follow existing patterns in the codebase
4. Update documentation after making changes

---

**Last Updated**: 2025-01-19
**SDK Version**: v0.1.0
**Status**: Fully implemented and integrated
