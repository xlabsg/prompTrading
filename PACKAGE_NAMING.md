# Package Naming Conventions

## Packages Architecture Overview

| Package Name | Purpose | Target Audience |
|--------------|---------|-----------------|
| `risk_engine` | 交易引擎内部风控、移动止损、仓位对账与交易所适配 | 交易系统内部实现 |
| `live_trading_sdk` | 策略编写接口协议（Broker / LiveStrategy / PaperBroker） | 策略开发者 |

### 包的定位与职责

#### `risk_engine` (内部引擎核心)
- **抽象层级**: 引擎底层实现
- **功能**:
  - 风险控制 (`RiskValidator` - 9项前置合规与风控校验)
  - 订单管理 (`OrderManager` - Snowflake ID, 状态生命周期)
  - 仓位监控 (`StopLossManager` - 移动止损)
  - 对账与同步 (`Reconciler` - 定时与交易所真实仓位/订单同步)
  - 交易所适配器 (`OKXAdapter`, `BinanceAdapter`)
- **使用场景**: `services/api/app/trading_engine/` 下的 `executor.py`, `monitor.py`, `manager.py` 等

#### `live_trading_sdk` (策略开发 SDK)
- **抽象层级**: 策略层高层抽象
- **功能**:
  - `Broker` Protocol - 策略表达交易意图 (`set_target_allocation`, `market_order`)
  - `LiveStrategy` Protocol - 策略生命周期钩子 (`initialize`, `on_bar`, `on_error`)
  - `PaperBroker` - 纸盘模拟交易 Broker 实现
  - `Bar`, `StrategyContext` - 基础数据结构
- **使用场景**: 实盘/模拟盘运行的用户策略代码 (`strategy.py`)

### 数据流

```
策略代码 (用户编写)
    ↓ 导入并实现
live_trading_sdk.LiveStrategy
    ↓ 调用
live_trading_sdk.Broker (LiveBroker / PaperBroker)
    ↓ 实现方
TradingEngine (services/api/app/trading_engine/executor.py)
    ↓ 使用
risk_engine (RiskValidator, OrderManager, StopLossManager)
    ↓ 调用
Exchange (OKX / Binance)
```

