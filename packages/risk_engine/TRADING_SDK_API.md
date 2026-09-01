# Trading SDK API 文档

> 本文档为 LLM 设计，提供 Trading SDK 的完整 API 参考

## 目录

1. [核心概念](#核心概念)
2. [风险控制 API](#风险控制-api)
3. [订单管理 API](#订单管理-api)
4. [仓位监控 API](#仓位监控-api)
5. [状态管理 API](#状态管理-api)
6. [交易所适配器 API](#交易所适配器-api)
7. [使用示例](#使用示例)

---

## 核心概念

### 数据类型

#### OrderSpec
订单规格（下单请求）

```python
OrderSpec(
    symbol: str,              # 交易对，如 "BTC-USDT-SWAP"
    side: OrderSide,          # BUY 或 SELL
    order_type: OrderType,    # MARKET, LIMIT, STOP_MARKET 等
    size: Decimal,            # 订单大小
    position_side: PositionSide,  # LONG, SHORT, NET
    price: Decimal = None,    # 限价单价格（可选）
    stop_loss: Decimal = None,    # 止损价格（可选）
    take_profit: Decimal = None,  # 止盈价格（可选）
    reduce_only: bool = False,    # 只减仓
    client_order_id: str = None   # 客户端订单 ID
)
```

#### Position
仓位信息

```python
Position(
    symbol: str,
    side: PositionSide,
    size: Decimal,
    entry_price: Decimal,
    current_price: Decimal,
    unrealized_pnl: Decimal,
    realized_pnl: Decimal,
    leverage: int,
    margin: Decimal,
    stop_loss: Decimal = None,
    take_profit: Decimal = None,
    stop_loss_type: StopLossType = None,  # "fixed", "trailing"
    status: PositionStatus = PositionStatus.OPEN
)
```

#### Balance
账户余额

```python
Balance(
    total_equity: Decimal,      # 总权益
    available_balance: Decimal, # 可用余额
    margin_used: Decimal,       # 已用保证金
    unrealized_pnl: Decimal     # 未实现盈亏
)
```

### 配置类型

#### RiskConfig
风险控制配置

```python
RiskConfig(
    max_position_pct: float = 100.0,    # 最大仓位百分比
    max_leverage: int = 10,              # 最大杠杆
    stop_loss_pct: float = None,         # 强制止损百分比
    max_daily_loss_pct: float = None,    # 最大每日亏损百分比
    max_drawdown_pct: float = None,      # 最大回撤百分比
    require_stop_loss: bool = True,      # 是否强制要求止损
    trailing_stop: TrailingStopConfig,   # 移动止损配置
    dynamic_tpsl: DynamicTPSLConfig      # 动态 TP/SL 配置
)
```

#### TrailingStopConfig
移动止损配置

```python
TrailingStopConfig(
    enabled: bool,
    activation: ActivationConfig(
        type: ActivationType,  # PROFIT_PCT, PROFIT_DOLLAR, IMMEDIATE
        threshold: float       # 激活阈值，如 0.005 表示 0.5%
    ),
    distance: DistanceConfig(
        type: DistanceType,    # PERCENTAGE, ATR, FIXED_DOLLAR
        value: float,          # 距离值，如 0.008 表示 0.8%
        atr_multiplier: float  # ATR 倍数（可选）
    )
)
```

---

## 风险控制 API

### RiskValidator

**用途**: 侵入式风险控制，下单前自动验证风险规则

#### `__init__(config: RiskConfig)`

初始化风险验证器

**参数**:
- `config`: RiskConfig - 风险配置

**示例**:
```python
risk_validator = RiskValidator(RiskConfig(
    max_position_pct=50.0,
    stop_loss_pct=0.02,
    max_daily_loss_pct=5.0,
    require_stop_loss=True
))
```

#### `validate_order(order_spec, current_positions, balance) -> RiskCheckResult`

验证订单是否符合风险规则

**参数**:
- `order_spec`: OrderSpec - 订单规格
- `current_positions`: List[Position] - 当前持仓列表
- `balance`: Balance - 账户余额

**返回**:
```python
RiskCheckResult(
    approved: bool,             # 是否通过
    violations: List[str],      # 违规列表
    warnings: List[str],        # 警告列表
    metadata: Dict[str, Any]    # 元数据
)
```

**示例**:
```python
result = risk_validator.validate_order(
    order_spec=order_spec,
    current_positions=positions,
    balance=balance
)

if not result.approved:
    print(f"Order rejected: {result.reason}")
```

#### `reset_daily_stats()`

重置每日统计（应在每日开始时调用）

**示例**:
```python
risk_validator.reset_daily_stats()
```

---

### PositionManager

**用途**: 仓位和 TP/SL 管理，支持动态计算和手动设置

#### `__init__(config: DynamicTPSLConfig)`

初始化仓位管理器

**参数**:
- `config`: DynamicTPSLConfig - 动态 TP/SL 配置

#### `calculate_tpsl(entry_price, side, sr=None, atr=None) -> Tuple[Decimal, Decimal]`

计算 TP/SL

**参数**:
- `entry_price`: Decimal - 入场价格
- `side`: PositionSide - 方向（LONG 或 SHORT）
- `sr`: SupportResistance - 支撑阻力位（可选）
- `atr`: float - ATR 值（可选）

**返回**: `(take_profit, stop_loss)`

**示例**:
```python
tp, sl = position_manager.calculate_tpsl(
    entry_price=Decimal("50000"),
    side=PositionSide.LONG,
    sr=None,  # 可选
    atr=None  # 可选
)
print(f"TP: {tp}, SL: {sl}")
```

#### `set_manual_tpsl(take_profit, stop_loss)`

设置手动 TP/SL（混合模式）

**参数**:
- `take_profit`: Decimal - 止盈价格
- `stop_loss`: Decimal - 止损价格

**示例**:
```python
position_manager.set_manual_tpsl(
    take_profit=Decimal("52000"),
    stop_loss=Decimal("49000")
)
```

#### `enable_dynamic_tpsl()`

启用动态 TP/SL 计算

**示例**:
```python
position_manager.enable_dynamic_tpsl()
```

#### `extract_support_resistance(bars, lookback=10) -> SupportResistance`

从 K 线数据提取支撑阻力位

**参数**:
- `bars`: List[Bar] - K 线数据
- `lookback`: int - 回看周期（默认 10）

**返回**: SupportResistance 对象

**示例**:
```python
sr = position_manager.extract_support_resistance(bars, lookback=10)
```

#### `calculate_atr(bars, period=14) -> float`

计算 ATR (Average True Range)

**参数**:
- `bars`: List[Bar] - K 线数据
- `period`: int - ATR 周期（默认 14）

**返回**: ATR 值

**示例**:
```python
atr = position_manager.calculate_atr(bars, period=14)
```

---

### StopLossManager

**用途**: 管理多种止损策略（固定止损、移动止损）

#### `__init__()`

初始化止损管理器

#### `register_position(position_id, position, config, atr=None)`

为仓位注册止损策略

**参数**:
- `position_id`: str - 仓位 ID
- `position`: Position - 仓位对象
- `config`: TrailingStopConfig - 移动止损配置
- `atr`: float - ATR 值（可选）

**示例**:
```python
stop_loss_manager.register_position(
    position_id="BTC_LONG_1",
    position=position,
    config=TrailingStopConfig(enabled=True),
    atr=500.0
)
```

#### `update(position_id, position, current_price)`

更新止损状态

**参数**:
- `position_id`: str - 仓位 ID
- `position`: Position - 仓位对象
- `current_price`: Decimal - 当前价格

**示例**:
```python
stop_loss_manager.update("BTC_LONG_1", position, Decimal("51000"))
```

#### `should_trigger(position_id, position, current_price) -> bool`

检查是否应该触发止损

**参数**:
- `position_id`: str - 仓位 ID
- `position`: Position - 仓位对象
- `current_price`: Decimal - 当前价格

**返回**: bool - 是否触发

**示例**:
```python
if stop_loss_manager.should_trigger("BTC_LONG_1", position, current_price):
    # 执行止损平仓
    close_position(position)
```

#### `get_stop_price(position_id, position) -> Decimal`

获取当前止损价格

**参数**:
- `position_id`: str - 仓位 ID
- `position`: Position - 仓位对象

**返回**: Decimal - 止损价格

**示例**:
```python
stop_price = stop_loss_manager.get_stop_price("BTC_LONG_1", position)
```

---

### DrawdownTracker

**用途**: 监控最大回撤和每日亏损

#### `__init__()`

初始化回撤追踪器

#### `update(current_equity, timestamp=None)`

更新回撤统计

**参数**:
- `current_equity`: Decimal - 当前账户权益
- `timestamp`: datetime - 时间戳（可选）

**示例**:
```python
drawdown_tracker.update(Decimal("10500"))
```

#### `is_max_drawdown_exceeded(max_drawdown_pct) -> bool`

检查是否超过最大回撤限制

**参数**:
- `max_drawdown_pct`: float - 最大回撤百分比

**返回**: bool - 是否超过

**示例**:
```python
if drawdown_tracker.is_max_drawdown_exceeded(10.0):
    # 停止交易
    stop_trading()
```

#### `is_daily_loss_exceeded(max_daily_loss_pct=None, max_daily_loss_dollar=None) -> bool`

检查是否超过每日亏损限制

**参数**:
- `max_daily_loss_pct`: float - 最大每日亏损百分比（可选）
- `max_daily_loss_dollar`: Decimal - 最大每日亏损金额（可选）

**返回**: bool - 是否超过

**示例**:
```python
if drawdown_tracker.is_daily_loss_exceeded(max_daily_loss_pct=5.0):
    # 停止交易
    stop_trading()
```

#### `get_stats() -> Dict[str, Any]`

获取回撤统计信息

**返回**: 统计字典

**示例**:
```python
stats = drawdown_tracker.get_stats()
print(f"Peak equity: {stats['peak_equity']}")
print(f"Current drawdown: {stats['current_drawdown_pct']}%")
print(f"Max drawdown: {stats['max_drawdown_pct']}%")
```

---

## 订单管理 API

### OrderManager

**用途**: 订单生命周期管理

#### `__init__(order_timeout_seconds=900, cancel_stale_orders=True)`

初始化订单管理器

**参数**:
- `order_timeout_seconds`: int - 订单超时时间（秒）
- `cancel_stale_orders`: bool - 是否自动取消陈旧订单

#### `add_order(order: Order)`

添加订单到追踪列表

**参数**:
- `order`: Order - 订单对象

**示例**:
```python
order_manager.add_order(order)
```

#### `get_order(order_id) -> Order`

根据订单 ID 获取订单

**参数**:
- `order_id`: str - 订单 ID

**返回**: Order 对象或 None

**示例**:
```python
order = order_manager.get_order("order_123")
```

#### `get_order_by_client_id(client_order_id) -> Order`

根据客户端订单 ID 获取订单

**参数**:
- `client_order_id`: str - 客户端订单 ID

**返回**: Order 对象或 None

**示例**:
```python
order = order_manager.get_order_by_client_id("mystrategyL5f3k2x")
```

#### `get_open_orders() -> List[Order]`

获取所有未完成的订单

**返回**: 订单列表

**示例**:
```python
open_orders = order_manager.get_open_orders()
for order in open_orders:
    print(f"Order {order.order_id}: {order.status}")
```

#### `get_stale_orders() -> List[Order]`

获取陈旧订单（超过超时时间的未完成订单）

**返回**: 订单列表

**示例**:
```python
stale_orders = order_manager.get_stale_orders()
for order in stale_orders:
    cancel_order(order)
```

#### `update_order(order_id, status=None, filled_size=None, avg_fill_price=None, ...)`

更新订单状态

**参数**:
- `order_id`: str - 订单 ID
- `status`: OrderStatus - 新状态（可选）
- `filled_size`: Decimal - 成交数量（可选）
- `avg_fill_price`: Decimal - 平均成交价格（可选）
- 其他参数...

**示例**:
```python
order_manager.update_order(
    order_id="order_123",
    status=OrderStatus.FILLED,
    filled_size=Decimal("0.1"),
    avg_fill_price=Decimal("50100")
)
```

---

### Snowflake ID Generator

**用途**: 生成唯一的客户端订单 ID

#### `generate_client_order_id(prefix="", direction="", max_length=32) -> str`

生成客户端订单 ID

**参数**:
- `prefix`: str - 前缀（如策略名）
- `direction`: str - 方向标识（"L" 或 "S"）
- `max_length`: int - 最大长度（默认 32）

**返回**: str - 客户端订单 ID

**示例**:
```python
from trading_sdk import generate_client_order_id

cl_ord_id = generate_client_order_id(
    prefix="my_strategy",
    direction="L"
)
# 输出: "mystrategyL5f3k2x"
```

---

### Reconciler

**用途**: 与交易所定期对账

#### `__init__(exchange_adapter, reconcile_interval_seconds=60)`

初始化对账器

**参数**:
- `exchange_adapter`: ExchangeAdapter - 交易所适配器
- `reconcile_interval_seconds`: int - 对账间隔（秒）

#### `should_reconcile() -> bool`

判断是否应该执行对账

**返回**: bool

**示例**:
```python
if reconciler.should_reconcile():
    reconciler.reconcile_orders(local_orders, symbol)
```

#### `reconcile_orders(local_orders, symbol) -> Dict[str, Any]`

对账订单

**参数**:
- `local_orders`: List[Order] - 本地订单列表
- `symbol`: str - 交易对

**返回**: 对账结果
```python
{
    "discrepancies": [...],    # 差异列表
    "updated_orders": [...],   # 需要更新的订单
    "missing_orders": [...]    # 缺失的订单
}
```

**示例**:
```python
result = reconciler.reconcile_orders(open_orders, "BTC-USDT-SWAP")

for discrepancy in result["discrepancies"]:
    logger.warning(f"Order discrepancy: {discrepancy}")
```

#### `reconcile_positions(local_positions, symbol=None) -> Dict[str, Any]`

对账仓位

**参数**:
- `local_positions`: List[Position] - 本地仓位列表
- `symbol`: str - 交易对（可选）

**返回**: 对账结果

**示例**:
```python
result = reconciler.reconcile_positions(positions)
```

---

## 仓位监控 API

### PnLCalculator

**用途**: 准确的 PnL 计算（包含费用）

#### `__init__(include_fees=True, use_mark_price=True)`

初始化 PnL 计算器

**参数**:
- `include_fees`: bool - 是否包含费用
- `use_mark_price`: bool - 是否使用标记价格

#### `calculate_unrealized_pnl(position, current_price=None) -> Decimal`

计算未实现盈亏

**参数**:
- `position`: Position - 仓位对象
- `current_price`: Decimal - 当前价格（可选）

**返回**: Decimal - 未实现盈亏

**示例**:
```python
pnl_calculator = PnLCalculator(include_fees=True)
unrealized_pnl = pnl_calculator.calculate_unrealized_pnl(
    position=position,
    current_price=Decimal("51000")
)
print(f"Unrealized PnL: {unrealized_pnl}")
```

#### `calculate_roi(position, current_price=None) -> float`

计算投资回报率 (ROI)

**参数**:
- `position`: Position - 仓位对象
- `current_price`: Decimal - 当前价格（可选）

**返回**: float - ROI 百分比

**示例**:
```python
roi = pnl_calculator.calculate_roi(position)
print(f"ROI: {roi:.2f}%")
```

---

### TradingMetrics

**用途**: 交易统计指标计算

#### `calculate_session_metrics(trades, positions, initial_balance, current_balance) -> Dict`

计算会话交易指标

**参数**:
- `trades`: List[Trade] - 成交记录列表
- `positions`: List[Position] - 仓位列表
- `initial_balance`: Decimal - 初始余额
- `current_balance`: Decimal - 当前余额

**返回**: 指标字典
```python
{
    "total_trades": int,
    "winning_trades": int,
    "losing_trades": int,
    "win_rate": float,
    "profit_factor": float,
    "avg_win": float,
    "avg_loss": float,
    "largest_win": float,
    "largest_loss": float,
    "total_pnl": float,
    "total_return_pct": float
}
```

**示例**:
```python
metrics_calculator = TradingMetrics()
metrics = metrics_calculator.calculate_session_metrics(
    trades=trades,
    positions=positions,
    initial_balance=Decimal("10000"),
    current_balance=Decimal("10500")
)
print(f"Win Rate: {metrics['win_rate']}%")
print(f"Profit Factor: {metrics['profit_factor']}")
```

---

## 交易所适配器 API

### ExchangeAdapter (抽象基类)

所有交易所适配器的基类

### OKXAdapter

**用途**: OKX 交易所适配器

#### `__init__(okx_client)`

初始化 OKX 适配器

**参数**:
- `okx_client`: OKXClient - OKX SDK 客户端实例

**示例**:
```python
from okx_sdk import OKXClient
from trading_sdk import OKXAdapter

okx_client = OKXClient(
    api_key="your_key",
    secret_key="your_secret",
    passphrase="your_passphrase"
)

adapter = OKXAdapter(okx_client)
```

#### `place_order(order_spec: OrderSpec) -> Dict`

下单

**参数**:
- `order_spec`: OrderSpec - 订单规格

**返回**: 交易所返回的订单信息

**示例**:
```python
response = adapter.place_order(order_spec)
exchange_order_id = response.get("ordId")
```

#### `cancel_order(symbol, order_id) -> bool`

取消订单

**参数**:
- `symbol`: str - 交易对
- `order_id`: str - 订单 ID

**返回**: bool - 是否成功

**示例**:
```python
success = adapter.cancel_order("BTC-USDT-SWAP", "order_id")
```

#### `get_positions(symbol=None) -> List[Dict]`

获取仓位信息

**参数**:
- `symbol`: str - 交易对（可选，None 表示所有）

**返回**: 仓位列表

**示例**:
```python
positions = adapter.get_positions("BTC-USDT-SWAP")
```

#### `get_balance() -> Dict`

获取账户余额

**返回**: 余额信息

**示例**:
```python
balance = adapter.get_balance()
```

#### `set_leverage(symbol, leverage, margin_mode) -> bool`

设置杠杆

**参数**:
- `symbol`: str - 交易对
- `leverage`: int - 杠杆倍数
- `margin_mode`: TradingMode - 保证金模式

**返回**: bool - 是否成功

**示例**:
```python
adapter.set_leverage("BTC-USDT-SWAP", 5, TradingMode.ISOLATED)
```

---

## 使用示例

### 完整的下单流程（带风险控制）

```python
from decimal import Decimal
from trading_sdk import (
    RiskValidator, PositionManager, StopLossManager,
    OrderManager, OKXAdapter, generate_client_order_id,
    OrderSpec, OrderSide, OrderType, PositionSide,
    RiskConfig, TrailingStopConfig
)
from okx_sdk import OKXClient

# 1. 初始化组件
okx_client = OKXClient(api_key="...", secret_key="...", passphrase="...")
adapter = OKXAdapter(okx_client)

risk_config = RiskConfig(
    max_position_pct=50.0,
    stop_loss_pct=0.02,
    require_stop_loss=True,
    trailing_stop=TrailingStopConfig(enabled=True)
)

risk_validator = RiskValidator(risk_config)
position_manager = PositionManager(risk_config.dynamic_tpsl)
order_manager = OrderManager()

# 2. 创建订单规格
order_spec = OrderSpec(
    symbol="BTC-USDT-SWAP",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    size=Decimal("0.1"),
    price=Decimal("50000"),
    position_side=PositionSide.LONG,
    client_order_id=generate_client_order_id("my_strategy", "L")
)

# 3. 计算 TP/SL
tp, sl = position_manager.calculate_tpsl(
    entry_price=order_spec.price,
    side=PositionSide.LONG
)
order_spec.take_profit = tp
order_spec.stop_loss = sl

# 4. 风险验证
current_positions = adapter.get_positions()
balance = adapter.get_balance()

risk_result = risk_validator.validate_order(
    order_spec=order_spec,
    current_positions=current_positions,
    balance=balance
)

if not risk_result.approved:
    print(f"Order rejected: {risk_result.reason}")
    exit()

# 5. 下单
response = adapter.place_order(order_spec)
print(f"Order placed: {response}")
```

### 监控循环（带移动止损）

```python
import time

stop_loss_manager = StopLossManager()

# 为每个仓位注册止损策略
for position in positions:
    stop_loss_manager.register_position(
        position_id=f"{position.symbol}_{position.side}",
        position=position,
        config=trailing_stop_config
    )

# 监控循环
while True:
    # 更新价格
    ticker = adapter.get_ticker(symbol)
    current_price = Decimal(str(ticker.get("last")))

    # 更新止损
    for position in positions:
        position_id = f"{position.symbol}_{position.side}"

        # 更新移动止损
        stop_loss_manager.update(position_id, position, current_price)

        # 检查是否触发
        if stop_loss_manager.should_trigger(position_id, position, current_price):
            print(f"Stop loss triggered for {position_id}")
            # 执行平仓
            close_position(position)

    time.sleep(5)
```

---

## 最佳实践

### 1. 始终进行风险验证

```python
# ✅ 正确
risk_result = risk_validator.validate_order(order_spec, positions, balance)
if risk_result.approved:
    adapter.place_order(order_spec)

# ❌ 错误 - 绕过风险验证
adapter.place_order(order_spec)  # 危险！
```

### 2. 使用客户端订单 ID 追踪

```python
# ✅ 正确 - 使用 Snowflake ID
cl_ord_id = generate_client_order_id("my_strategy", "L")
order_spec.client_order_id = cl_ord_id

# 后续可以通过 client_order_id 查询
order = order_manager.get_order_by_client_id(cl_ord_id)
```

### 3. 定期对账

```python
# 每 60 秒对账一次
if reconciler.should_reconcile():
    result = reconciler.reconcile_orders(open_orders, symbol)

    # 处理差异
    for discrepancy in result["discrepancies"]:
        logger.warning(f"Discrepancy: {discrepancy}")
```

### 4. 监控回撤

```python
# 每次更新余额时检查回撤
drawdown_tracker.update(current_equity)

if drawdown_tracker.is_max_drawdown_exceeded(10.0):
    logger.error("Max drawdown exceeded, stopping trading")
    stop_all_trading()
```

### 5. 清理陈旧订单

```python
# 定期清理
stale_orders = order_manager.get_stale_orders()
for order in stale_orders:
    adapter.cancel_order(order.symbol, order.exchange_order_id)
    order_manager.mark_order_stale(order.order_id)
```

---

## 错误处理

### RiskViolationError

当风险验证失败时抛出

```python
from trading_sdk.risk import RiskViolationError

try:
    result = risk_validator.validate_order(...)
    if not result.approved:
        raise RiskViolationError(result.reason)
except RiskViolationError as e:
    logger.error(f"Risk violation: {e}")
```

### 常见错误代码

- `INSUFFICIENT_BALANCE`: 余额不足
- `MAX_POSITION_EXCEEDED`: 超过最大仓位
- `MAX_LEVERAGE_EXCEEDED`: 超过最大杠杆
- `DAILY_LOSS_LIMIT`: 达到每日亏损限制
- `MAX_DRAWDOWN_EXCEEDED`: 超过最大回撤
- `INVALID_STOP_LOSS`: 无效的止损价格

---

## 附录

### 完整的枚举类型

```python
# OrderType
OrderType.MARKET
OrderType.LIMIT
OrderType.STOP_MARKET
OrderType.STOP_LIMIT
OrderType.TRAILING_STOP

# OrderSide
OrderSide.BUY
OrderSide.SELL

# PositionSide
PositionSide.LONG
PositionSide.SHORT
PositionSide.NET

# OrderStatus
OrderStatus.PENDING
OrderStatus.SUBMITTED
OrderStatus.OPEN
OrderStatus.PARTIALLY_FILLED
OrderStatus.FILLED
OrderStatus.CANCELLED
OrderStatus.REJECTED
OrderStatus.EXPIRED
OrderStatus.FAILED

# PositionStatus
PositionStatus.OPEN
PositionStatus.CLOSED

# ActivationType
ActivationType.PROFIT_PCT
ActivationType.PROFIT_DOLLAR
ActivationType.IMMEDIATE

# DistanceType
DistanceType.PERCENTAGE
DistanceType.ATR
DistanceType.FIXED_DOLLAR

# StopLossType
StopLossType.FIXED
StopLossType.TRAILING
StopLossType.DYNAMIC
```

---

**文档版本**: 0.1.0
**最后更新**: 2025-01-19
**适用于**: LLM 辅助编程、AI 策略开发
