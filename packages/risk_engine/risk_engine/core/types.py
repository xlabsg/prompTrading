"""
Trading SDK Core Types

定义所有核心数据类型
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from .enums import (
    OrderType, OrderSide, PositionSide, OrderStatus, PositionStatus,
    TradingMode, PositionMode, StopLossType
)


@dataclass
class Bar:
    """K线数据"""
    timestamp: int  # 毫秒时间戳
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str
    interval: str  # 1m, 5m, 15m, 1h, 4h, 1d 等


@dataclass
class Position:
    """仓位信息"""
    symbol: str
    side: PositionSide
    size: Decimal  # 仓位大小
    entry_price: Decimal  # 平均入场价格
    current_price: Decimal  # 当前市场价格
    unrealized_pnl: Decimal  # 未实现盈亏
    realized_pnl: Decimal  # 已实现盈亏
    leverage: int
    margin: Decimal  # 保证金
    liquidation_price: Optional[Decimal] = None  # 强平价格
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    status: PositionStatus = PositionStatus.OPEN

    # TP/SL 信息
    take_profit: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    stop_loss_type: Optional[StopLossType] = None

    # 移动止损信息
    trailing_stop_activated: bool = False
    trailing_stop_price: Optional[Decimal] = None
    highest_price: Optional[Decimal] = None  # Long 用
    lowest_price: Optional[Decimal] = None  # Short 用

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderSpec:
    """订单规格（下单请求）"""
    symbol: str
    side: OrderSide
    order_type: OrderType
    size: Decimal
    position_side: PositionSide

    # 价格信息
    price: Optional[Decimal] = None  # 限价单价格
    trigger_price: Optional[Decimal] = None  # 触发价格（止损单）

    # 风控参数
    take_profit: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None

    # 其他参数
    reduce_only: bool = False  # 只减仓
    post_only: bool = False  # 只做 maker
    time_in_force: str = "GTC"  # GTC, IOC, FOK
    client_order_id: Optional[str] = None

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Order:
    """订单信息"""
    order_id: str  # 本地订单 ID
    exchange_order_id: Optional[str]  # 交易所订单 ID
    client_order_id: str  # 客户端订单 ID
    symbol: str
    side: OrderSide
    order_type: OrderType
    position_side: PositionSide
    status: OrderStatus

    # 数量和价格
    size: Decimal
    filled_size: Decimal = Decimal("0")
    remaining_size: Decimal = Decimal("0")
    price: Optional[Decimal] = None
    avg_fill_price: Optional[Decimal] = None
    trigger_price: Optional[Decimal] = None

    # 时间信息
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None

    # 费用
    fee: Decimal = Decimal("0")
    fee_currency: str = "USDT"

    # 风控信息
    reduce_only: bool = False
    take_profit: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update_filled(self, filled_size: Decimal, avg_fill_price: Decimal):
        """更新成交信息"""
        self.filled_size = filled_size
        self.remaining_size = self.size - filled_size
        self.avg_fill_price = avg_fill_price
        self.updated_at = datetime.utcnow()

        if self.filled_size >= self.size:
            self.status = OrderStatus.FILLED
            self.filled_at = datetime.utcnow()
        elif self.filled_size > 0:
            self.status = OrderStatus.PARTIALLY_FILLED


@dataclass
class Trade:
    """成交记录"""
    trade_id: str
    order_id: str
    symbol: str
    side: OrderSide
    size: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Balance:
    """账户余额"""
    total_equity: Decimal  # 总权益
    available_balance: Decimal  # 可用余额
    margin_used: Decimal = Decimal("0")  # 已用保证金
    unrealized_pnl: Decimal = Decimal("0")  # 未实现盈亏
    currency: str = "USDT"
    timestamp: Optional[datetime] = None


@dataclass
class SupportResistance:
    """支撑阻力位"""
    supports: list[Decimal] = field(default_factory=list)
    resistances: list[Decimal] = field(default_factory=list)

    def get_nearest_support(self, price: Decimal) -> Optional[Decimal]:
        """获取最近的支撑位（价格下方）"""
        valid_supports = [s for s in self.supports if s < price]
        return max(valid_supports) if valid_supports else None

    def get_nearest_resistance(self, price: Decimal) -> Optional[Decimal]:
        """获取最近的阻力位（价格上方）"""
        valid_resistances = [r for r in self.resistances if r > price]
        return min(valid_resistances) if valid_resistances else None


@dataclass
class RiskCheckResult:
    """风险检查结果"""
    approved: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def reason(self) -> str:
        """获取拒绝原因"""
        if self.approved:
            return ""
        return "; ".join(self.violations)
