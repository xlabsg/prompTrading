# Trading SDK

通用交易 SDK，提供完整的 live trading 基础设施。

## 功能特性

### 1. 风险控制（Risk Control）
- **侵入式风险验证**：下单前自动检查风险规则
- **多种止损策略**：
  - 固定止损
  - 移动止损（支持百分比、ATR、固定金额）
- **动态 TP/SL 计算**：基于支撑阻力位 + ATR 缓冲
- **回撤监控**：实时追踪最大回撤和每日亏损
- **仓位限制**：最大仓位百分比、杠杆限制
- **风险回报比验证**：确保最小 R:R 比率

### 2. 订单管理（Order Management）
- **Snowflake ID 生成**：唯一的客户端订单 ID
- **订单生命周期追踪**：创建、提交、成交、取消
- **陈旧订单清理**：自动取消超时订单
- **订单所有权识别**：前缀匹配，支持多策略

### 3. 对账机制（Reconciliation）
- **定期对账**：与交易所同步订单和仓位状态
- **差异检测**：自动发现并记录状态不一致
- **启动时全量对账**：确保状态一致性

### 4. 仓位监控（Position Monitoring）
- **准确的 PnL 计算**：包含费用
- **实时仓位追踪**：WebSocket + REST 对账
- **交易统计指标**：
  - Win Rate, Profit Factor
  - 最大连续盈利/亏损
  - Sharpe Ratio
  - 平均持仓时间

### 5. 状态管理（State Management）
- **双层存储**：Redis（热存储）+ PostgreSQL（冷存储）
- **持久化与恢复**：支持重启恢复
- **限流保存**：避免频繁写入

### 6. 交易所适配（Exchange Adapters）
- **统一接口**：抽象不同交易所的 API 差异
- **OKX 实现**：完整的 OKX 适配器
- **可扩展**：易于添加 Binance、Bybit 等

## 安装

```bash
cd packages/trading_sdk
pip install -e .
```

## 快速开始

### 基本配置

```python
from trading_sdk import (
    RiskConfig, TradingConfig, TrailingStopConfig,
    ActivationConfig, DistanceConfig,
    ActivationType, DistanceType, TradingMode
)

# 风险配置
risk_config = RiskConfig(
    max_position_pct=100.0,  # 最大仓位 100%
    max_leverage=10,  # 最大杠杆 10x
    stop_loss_pct=0.02,  # 强制止损 2%
    max_daily_loss_pct=5.0,  # 最大每日亏损 5%
    max_drawdown_pct=10.0,  # 最大回撤 10%
    require_stop_loss=True,  # 强制要求止损

    # 移动止损配置
    trailing_stop=TrailingStopConfig(
        enabled=True,
        activation=ActivationConfig(
            type=ActivationType.PROFIT_PCT,
            threshold=0.005  # 0.5% 利润激活
        ),
        distance=DistanceConfig(
            type=DistanceType.PERCENTAGE,
            value=0.008,  # 0.8% 距离
            atr_multiplier=1.5
        )
    ),

    # 动态 TP/SL 配置
    dynamic_tpsl=DynamicTPSLConfig(
        enabled=True,
        use_support_resistance=True,
        use_atr_buffer=True,
        min_risk_reward=1.5  # 最小 1.5:1 风险回报比
    )
)

# 交易配置
trading_config = TradingConfig(
    exchange="okx",
    symbol="BTC-USDT-SWAP",
    trading_mode=TradingMode.ISOLATED,
    leverage=5,
    risk=risk_config,
    reconcile_interval_seconds=60,
    order_timeout_seconds=900
)
```

### 使用示例

```python
from trading_sdk import (
    RiskValidator, PositionManager, StopLossManager,
    OrderManager, Reconciler, OKXAdapter,
    OrderSpec, OrderSide, OrderType, PositionSide,
    generate_client_order_id
)
from okx_sdk import OKXClient
from decimal import Decimal

# 1. 初始化 OKX 客户端和适配器
okx_client = OKXClient(
    api_key="your_api_key",
    secret_key="your_secret_key",
    passphrase="your_passphrase"
)
exchange_adapter = OKXAdapter(okx_client)

# 2. 初始化风险控制组件
risk_validator = RiskValidator(risk_config)
position_manager = PositionManager(risk_config.dynamic_tpsl)
stop_loss_manager = StopLossManager()

# 3. 初始化订单管理
order_manager = OrderManager(
    order_timeout_seconds=trading_config.order_timeout_seconds,
    cancel_stale_orders=trading_config.cancel_stale_orders
)

# 4. 初始化对账器
reconciler = Reconciler(
    exchange_adapter=exchange_adapter,
    reconcile_interval_seconds=trading_config.reconcile_interval_seconds
)

# 5. 下单流程
def place_order_with_risk_control():
    # 获取当前账户信息
    balance_info = exchange_adapter.get_balance()
    current_positions = exchange_adapter.get_positions(trading_config.symbol)

    # 创建订单规格
    order_spec = OrderSpec(
        symbol=trading_config.symbol,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=Decimal("0.1"),
        price=Decimal("50000"),
        position_side=PositionSide.LONG,
        client_order_id=generate_client_order_id(
            prefix="my_strategy",
            direction="L"
        )
    )

    # 计算 TP/SL
    entry_price = order_spec.price
    take_profit, stop_loss = position_manager.calculate_tpsl(
        entry_price=entry_price,
        side=PositionSide.LONG,
        sr=None,  # 可选：提供支撑阻力位
        atr=None  # 可选：提供 ATR 值
    )

    order_spec.take_profit = take_profit
    order_spec.stop_loss = stop_loss

    # 风险验证（侵入式控制）
    risk_result = risk_validator.validate_order(
        order_spec=order_spec,
        current_positions=current_positions,
        balance=balance_info
    )

    if not risk_result.approved:
        print(f"Order rejected: {risk_result.reason}")
        return None

    # 下单
    try:
        response = exchange_adapter.place_order(order_spec)
        print(f"Order placed: {response}")

        # 添加到订单管理器
        # order_manager.add_order(order)

        return response
    except Exception as e:
        print(f"Failed to place order: {e}")
        return None

# 6. 运行对账
def run_reconciliation():
    if reconciler.should_reconcile():
        open_orders = order_manager.get_open_orders()
        order_result = reconciler.reconcile_orders(
            local_orders=open_orders,
            symbol=trading_config.symbol
        )

        print(f"Order reconciliation: {order_result}")

        # 处理差异...
```

## 核心组件

### RiskValidator（风险验证器）
侵入式风险控制，下单前自动检查：
- 余额是否足够
- 是否超过最大仓位
- 杠杆是否超限
- 止损是否有效
- 风险回报比是否满足要求
- 是否超过每日亏损限制
- 是否超过最大回撤

### PositionManager（仓位管理器）
支持三种 TP/SL 模式：
1. **动态计算**：基于支撑阻力 + ATR
2. **手动设置**：策略自定义
3. **混合模式**：策略可选择

### StopLossManager（止损管理器）
管理多种止损策略：
- **FixedStopLoss**：固定止损
- **TrailingStopLoss**：移动止损
  - 支持利润激活（百分比/金额/立即）
  - 支持距离类型（百分比/ATR/固定金额）
  - 只向有利方向移动

### OrderManager（订单管理器）
- Snowflake ID 生成（唯一性保证）
- 订单生命周期追踪
- 陈旧订单检测和清理
- 线程安全操作

### Reconciler（对账器）
- 定期与交易所同步
- 检测订单状态差异
- 检测仓位大小差异
- 自动记录差异日志

## 架构设计

```
packages/trading_sdk/
├── core/               # 核心类型、枚举、配置
├── risk/               # 风险控制
│   ├── risk_validator.py
│   ├── stop_loss.py
│   ├── position_manager.py
│   └── drawdown_tracker.py
├── execution/          # 订单执行
│   ├── order_types.py
│   ├── order_manager.py
│   └── reconciler.py
├── monitoring/         # 监控统计
│   ├── pnl_calculator.py
│   └── metrics.py
├── state/              # 状态管理
│   ├── trading_state.py
│   └── persistence.py
└── adapters/           # 交易所适配器
    ├── base.py
    └── okx.py
```

## 设计原则

1. **安全优先**：风控是硬约束，不可绕过
2. **可观测**：所有状态变化都可追溯
3. **容错性**：支持重启恢复、对账、重试
4. **可扩展**：新交易所、新订单类型易于添加
5. **性能**：异步执行、非阻塞状态保存

## 集成到现有系统

参考 `INTEGRATION_GUIDE.md` 了解如何将 SDK 集成到现有的 TradingEngine。

## 开发计划

- [ ] 完善单元测试
- [ ] 添加 Binance 适配器
- [ ] 支持更多订单类型（Iceberg, TWAP）
- [ ] 添加更多风控规则（资金费率过滤）
- [ ] 性能优化（WebSocket 代替轮询）

## 许可证

MIT
