# Trading SDK 集成指南

本指南说明如何将 Trading SDK 集成到现有的 `services/api/app/trading_engine` 中。

## 集成概览

Trading SDK 将替换和增强以下现有功能：
- 订单执行（`executor.py`）
- 仓位监控（`monitor.py`）
- 会话管理（`manager.py`）

同时新增：
- 风险控制（`RiskValidator`）
- 移动止损（`StopLossManager`）
- 对账机制（`Reconciler`）

## 集成步骤

### 1. 更新数据库模型

在 `packages/control_plane/control_plane/models.py` 中添加新字段：

```python
# TradingConfig 表新增字段
class TradingConfig(Base):
    # ... 现有字段 ...

    # 风险控制配置
    max_leverage = Column(Integer, default=10)
    max_daily_loss_pct = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)
    require_stop_loss = Column(Boolean, default=True)

    # 移动止损配置
    trailing_stop_enabled = Column(Boolean, default=False)
    trailing_activation_pct = Column(Float, default=0.005)
    trailing_distance_pct = Column(Float, default=0.008)

    # 动态 TP/SL 配置
    dynamic_tpsl_enabled = Column(Boolean, default=False)
    use_support_resistance = Column(Boolean, default=True)
    min_risk_reward = Column(Float, default=1.0)

# Position 表新增字段
class Position(Base):
    # ... 现有字段 ...

    # TP/SL 信息
    take_profit = Column(Numeric(20, 8), nullable=True)
    stop_loss = Column(Numeric(20, 8), nullable=True)
    stop_loss_type = Column(String(20), nullable=True)  # "fixed", "trailing"

    # 移动止损状态
    trailing_stop_activated = Column(Boolean, default=False)
    trailing_stop_price = Column(Numeric(20, 8), nullable=True)
    highest_price = Column(Numeric(20, 8), nullable=True)
    lowest_price = Column(Numeric(20, 8), nullable=True)

# Order 表新增字段
class Order(Base):
    # ... 现有字段 ...

    # 客户端订单 ID (Snowflake)
    client_order_id = Column(String(32), unique=True, index=True)

    # TP/SL 信息
    take_profit = Column(Numeric(20, 8), nullable=True)
    stop_loss = Column(Numeric(20, 8), nullable=True)
```

生成迁移：
```bash
cd services/api
alembic revision --autogenerate -m "Add trading SDK fields"
alembic upgrade head
```

### 2. 创建 SDK 配置构建器

创建 `services/api/app/trading_engine/sdk_config.py`：

```python
"""
Trading SDK Configuration Builder

从 TradingConfig 构建 SDK 配置
"""
from trading_sdk import (
    RiskConfig, TradingConfig as SDKTradingConfig,
    TrailingStopConfig, DynamicTPSLConfig,
    ActivationConfig, DistanceConfig,
    ActivationType, DistanceType, TradingMode, PositionMode
)
from control_plane.models import TradingConfig as DBTradingConfig


def build_risk_config(db_config: DBTradingConfig) -> RiskConfig:
    """从数据库配置构建风险配置"""
    return RiskConfig(
        max_position_pct=db_config.max_position_pct,
        max_leverage=db_config.max_leverage,
        stop_loss_pct=db_config.stop_loss_pct,
        max_daily_loss_pct=db_config.max_daily_loss_pct,
        max_drawdown_pct=db_config.max_drawdown_pct,
        require_stop_loss=db_config.require_stop_loss,

        trailing_stop=TrailingStopConfig(
            enabled=db_config.trailing_stop_enabled,
            activation=ActivationConfig(
                type=ActivationType.PROFIT_PCT,
                threshold=db_config.trailing_activation_pct
            ),
            distance=DistanceConfig(
                type=DistanceType.PERCENTAGE,
                value=db_config.trailing_distance_pct
            )
        ),

        dynamic_tpsl=DynamicTPSLConfig(
            enabled=db_config.dynamic_tpsl_enabled,
            use_support_resistance=db_config.use_support_resistance,
            min_risk_reward=db_config.min_risk_reward
        )
    )


def build_trading_config(db_config: DBTradingConfig) -> SDKTradingConfig:
    """从数据库配置构建交易配置"""
    return SDKTradingConfig(
        exchange=db_config.exchange,
        symbol=db_config.symbol,
        trading_mode=TradingMode.ISOLATED if db_config.exchange == "okx" else TradingMode.CROSS,
        position_mode=PositionMode.LONG_SHORT,
        leverage=db_config.leverage or 1,
        risk=build_risk_config(db_config),
        reconcile_interval_seconds=60,
        order_timeout_seconds=900
    )
```

### 3. 更新 OrderExecutor

修改 `services/api/app/trading_engine/executor.py`：

```python
"""
Enhanced Order Executor with Trading SDK
"""
import logging
from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session

from trading_sdk import (
    RiskValidator, PositionManager, StopLossManager,
    OrderManager, OKXAdapter,
    OrderSpec, OrderSide, OrderType, PositionSide,
    generate_client_order_id
)
from okx_sdk import OKXClient
from control_plane.models import Order, TradingConfig
from .sdk_config import build_trading_config

logger = logging.getLogger(__name__)


class EnhancedOrderExecutor:
    """增强的订单执行器（集成 Trading SDK）"""

    def __init__(self, config: TradingConfig, okx_client: OKXClient, db: Session):
        self.config = config
        self.db = db

        # SDK 配置
        self.sdk_config = build_trading_config(config)

        # 交易所适配器
        self.exchange_adapter = OKXAdapter(okx_client)

        # SDK 组件
        self.risk_validator = RiskValidator(self.sdk_config.risk)
        self.position_manager = PositionManager(self.sdk_config.risk.dynamic_tpsl)
        self.stop_loss_manager = StopLossManager()
        self.order_manager = OrderManager(
            order_timeout_seconds=self.sdk_config.order_timeout_seconds,
            cancel_stale_orders=self.sdk_config.cancel_stale_orders
        )

    def place_market_order(
        self,
        side: str,
        size: float,
        reduce_only: bool = False
    ) -> Optional[Order]:
        """下市价单（带风险控制）"""
        # 获取当前市场价格
        ticker = self.exchange_adapter.get_ticker(self.config.symbol)
        current_price = Decimal(str(ticker.get("last", 0)))

        # 创建订单规格
        order_spec = OrderSpec(
            symbol=self.config.symbol,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            size=Decimal(str(size)),
            price=current_price,
            position_side=PositionSide.LONG if side == "buy" else PositionSide.SHORT,
            reduce_only=reduce_only,
            client_order_id=generate_client_order_id(
                prefix=f"strategy_{self.config.strategy_id}",
                direction="L" if side == "buy" else "S"
            )
        )

        # 如果不是减仓，计算 TP/SL
        if not reduce_only:
            take_profit, stop_loss = self.position_manager.calculate_tpsl(
                entry_price=current_price,
                side=order_spec.position_side,
                sr=None,  # TODO: 从 K 线数据计算支撑阻力
                atr=None  # TODO: 从 K 线数据计算 ATR
            )
            order_spec.take_profit = take_profit
            order_spec.stop_loss = stop_loss

        # 风险验证
        current_positions = self.exchange_adapter.get_positions(self.config.symbol)
        balance = self.exchange_adapter.get_balance()

        risk_result = self.risk_validator.validate_order(
            order_spec=order_spec,
            current_positions=current_positions,
            balance=balance
        )

        if not risk_result.approved:
            logger.error(f"Order rejected by risk validator: {risk_result.reason}")
            raise ValueError(f"Risk check failed: {risk_result.reason}")

        # 下单
        try:
            response = self.exchange_adapter.place_order(order_spec)

            # 创建数据库订单记录
            order = Order(
                session_id=self.config.id,
                exchange_order_id=response.get("ordId"),
                client_order_id=order_spec.client_order_id,
                symbol=self.config.symbol,
                side=side,
                order_type="market",
                size=float(size),
                status="open",
                take_profit=float(order_spec.take_profit) if order_spec.take_profit else None,
                stop_loss=float(order_spec.stop_loss) if order_spec.stop_loss else None,
                created_at=datetime.utcnow()
            )
            self.db.add(order)
            self.db.commit()

            # 添加到订单管理器
            # self.order_manager.add_order(...)

            logger.info(f"Order placed successfully: {order.id}")
            return order

        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            self.db.rollback()
            raise
```

### 4. 更新 PositionMonitor

修改 `services/api/app/trading_engine/monitor.py`：

```python
"""
Enhanced Position Monitor with Trading SDK
"""
import logging
from decimal import Decimal
from sqlalchemy.orm import Session

from trading_sdk import (
    StopLossManager, PnLCalculator, DrawdownTracker,
    Position as SDKPosition, PositionSide
)
from control_plane.models import Position, TradingSession

logger = logging.getLogger(__name__)


class EnhancedPositionMonitor:
    """增强的仓位监控器（集成 Trading SDK）"""

    def __init__(
        self,
        session: TradingSession,
        exchange_adapter,
        db: Session
    ):
        self.session = session
        self.exchange_adapter = exchange_adapter
        self.db = db

        # SDK 组件
        self.stop_loss_manager = StopLossManager()
        self.pnl_calculator = PnLCalculator(include_fees=True, use_mark_price=True)
        self.drawdown_tracker = DrawdownTracker()

    def update_positions(self):
        """更新仓位（检查移动止损）"""
        # 从交易所获取仓位
        exchange_positions = self.exchange_adapter.get_positions(self.session.config.symbol)

        for ex_pos in exchange_positions:
            # 转换为 SDK Position
            sdk_position = self._convert_to_sdk_position(ex_pos)

            # 检查止损
            current_price = Decimal(str(ex_pos.get("markPx", ex_pos.get("last"))))

            # 更新移动止损
            self.stop_loss_manager.update(
                position_id=f"{sdk_position.symbol}_{sdk_position.side}",
                position=sdk_position,
                current_price=current_price
            )

            # 检查是否触发止损
            should_stop = self.stop_loss_manager.should_trigger(
                position_id=f"{sdk_position.symbol}_{sdk_position.side}",
                position=sdk_position,
                current_price=current_price
            )

            if should_stop:
                logger.warning(f"Stop loss triggered for {sdk_position.symbol}")
                # 执行平仓...
                self._close_position(sdk_position)

            # 更新数据库中的仓位...

    def _convert_to_sdk_position(self, ex_pos: dict) -> SDKPosition:
        """将交易所仓位转换为 SDK Position"""
        # 实现转换逻辑...
        pass

    def _close_position(self, position: SDKPosition):
        """平仓"""
        # 实现平仓逻辑...
        pass
```

### 5. 更新会话管理器

修改 `services/api/app/trading_engine/manager.py`，集成对账机制：

```python
from trading_sdk import Reconciler

class TradingSessionManager:
    def __init__(self, ...):
        # ... 现有代码 ...

        # 对账器
        self.reconciler = Reconciler(
            exchange_adapter=self.exchange_adapter,
            reconcile_interval_seconds=60
        )

    def _monitor_loop(self):
        """监控循环（增加对账）"""
        while self._should_continue_monitoring():
            try:
                # 对账检查
                if self.reconciler.should_reconcile():
                    self._run_reconciliation()

                # ... 现有监控逻辑 ...

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

    def _run_reconciliation(self):
        """运行对账"""
        # 订单对账
        local_orders = self.order_executor.order_manager.get_open_orders()
        order_result = self.reconciler.reconcile_orders(
            local_orders=local_orders,
            symbol=self.config.symbol
        )

        # 处理差异
        for discrepancy in order_result["discrepancies"]:
            logger.warning(f"Order discrepancy: {discrepancy}")
            # 更新本地订单状态...

        # 仓位对账
        # ...
```

### 6. 更新 API 路由

修改 `services/api/app/routers/trading.py`，暴露新的风控配置：

```python
from pydantic import BaseModel

class TradingConfigCreate(BaseModel):
    # ... 现有字段 ...

    # 新增风控字段
    max_leverage: int = 10
    max_daily_loss_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    require_stop_loss: bool = True

    # 移动止损
    trailing_stop_enabled: bool = False
    trailing_activation_pct: float = 0.005
    trailing_distance_pct: float = 0.008

    # 动态 TP/SL
    dynamic_tpsl_enabled: bool = False
    use_support_resistance: bool = True
    min_risk_reward: float = 1.0

@router.post("/strategies/{strategy_id}/trading/config")
async def create_trading_config(
    strategy_id: str,
    config: TradingConfigCreate,
    db: Session = Depends(get_db)
):
    # 创建配置（包含新字段）
    # ...
```

### 7. 前端更新

在 `apps/web/src/components/trading/TradingConfigForm.tsx` 中添加新的配置项：

```tsx
// 风险控制配置
<FormSection title="Risk Control">
  <NumberInput label="Max Leverage" name="max_leverage" defaultValue={10} />
  <NumberInput label="Max Daily Loss (%)" name="max_daily_loss_pct" />
  <NumberInput label="Max Drawdown (%)" name="max_drawdown_pct" />
  <Checkbox label="Require Stop Loss" name="require_stop_loss" />
</FormSection>

// 移动止损配置
<FormSection title="Trailing Stop">
  <Checkbox label="Enable" name="trailing_stop_enabled" />
  <NumberInput label="Activation (%)" name="trailing_activation_pct" defaultValue={0.5} />
  <NumberInput label="Distance (%)" name="trailing_distance_pct" defaultValue={0.8} />
</FormSection>

// 动态 TP/SL 配置
<FormSection title="Dynamic TP/SL">
  <Checkbox label="Enable" name="dynamic_tpsl_enabled" />
  <Checkbox label="Use Support/Resistance" name="use_support_resistance" />
  <NumberInput label="Min Risk/Reward" name="min_risk_reward" defaultValue={1.5} />
</FormSection>
```

## 测试

### 单元测试

```bash
cd packages/trading_sdk
pytest tests/
```

### 集成测试

1. 启动开发环境：
```bash
cd infra/compose
./update.sh
```

2. 创建测试配置：
```bash
curl -X POST http://localhost:8000/api/strategies/{id}/trading/config \
  -H "Content-Type: application/json" \
  -d '{
    "exchange": "okx",
    "symbol": "BTC-USDT-SWAP",
    "max_position_pct": 50,
    "stop_loss_pct": 2,
    "trailing_stop_enabled": true,
    "dynamic_tpsl_enabled": true
  }'
```

3. 启动交易会话并监控日志。

## 注意事项

1. **渐进式集成**：建议先在测试环境验证，然后逐步迁移到生产
2. **数据库迁移**：确保在生产环境运行迁移前备份数据
3. **配置兼容性**：旧配置应该能够正常工作（使用默认值）
4. **监控日志**：密切关注风控拒绝、对账差异等日志

## 常见问题

### Q: SDK 是否会影响现有交易性能？
A: 风险验证的开销很小（< 1ms），不会显著影响性能。对账机制在后台运行，不阻塞交易。

### Q: 如何禁用某些风控规则？
A: 在配置中将相关字段设为 `None` 或 `False`，例如 `max_daily_loss_pct=None`。

### Q: 移动止损会自动执行平仓吗？
A: 是的，当触发移动止损时，`PositionMonitor` 会自动下平仓单。

### Q: 如何查看对账差异？
A: 查看日志文件中的 `Order discrepancy` 和 `Position discrepancy` 记录。

## 后续优化

1. 添加更多风控规则（资金费率过滤）
2. 支持 WebSocket 实时更新（减少轮询）
3. 优化对账性能（批量查询）
4. 添加风控告警通知
