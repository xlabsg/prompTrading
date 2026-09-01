# Package Naming Conventions

## Package Rename (2026-01-19)

为了减少混淆，对两个核心包进行了重命名：

### 变更说明

| 旧名称 | 新名称 | 用途 | 目标用户 |
|--------|--------|------|----------|
| `trading_sdk` | `risk_engine` | 交易引擎内部风控与订单执行 | 系统实现者 |
| `live_trading_sdk` | `strategy_sdk` | 策略编写接口 | 策略开发者 |

### 重命名原因

1. **命名混淆**: 两个包都叫 "SDK"，但用途完全不同
2. **清晰定位**:
   - `risk_engine` - 更准确反映其作为交易引擎核心风控模块的定位
   - `strategy_sdk` - 更清楚表明是给策略开发者使用的公开 SDK

### 包的定位

#### `risk_engine` (内部使用)
- **抽象层级**: 底层实现
- **功能**:
  - 风险控制 (RiskValidator - 9项检查)
  - 订单管理 (OrderManager - Snowflake ID, 生命周期)
  - 仓位监控 (StopLossManager - 移动止损)
  - 交易所适配器 (OKXAdapter)
- **使用场景**: `enhanced_executor.py`, `enhanced_monitor.py` 等引擎模块

#### `strategy_sdk` (公开接口，未来可能开源)
- **抽象层级**: 高层抽象
- **功能**:
  - `Broker` Protocol - 策略表达交易意图
  - `LiveStrategy` Protocol - 策略生命周期钩子
  - `Bar`, `StrategyContext` - 数据结构
- **使用场景**: 用户编写的策略代码

### 数据流

```
策略代码 (用户编写)
    ↓ 导入并实现
strategy_sdk.LiveStrategy
    ↓ 调用
strategy_sdk.Broker
    ↓ 实现方
TradingEngine (enhanced_executor.py)
    ↓ 使用
risk_engine (RiskValidator, OrderManager)
    ↓ 调用
OKX Exchange
```

### 未来计划

- `strategy_sdk` 可能开源，提供完整文档和示例
- `risk_engine` 保持内部使用，作为交易引擎核心
