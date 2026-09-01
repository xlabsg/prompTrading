"""
Trading SDK Core Module

导出核心类型、枚举和配置
"""
from .enums import (
    OrderType,
    OrderSide,
    PositionSide,
    OrderStatus,
    PositionStatus,
    TradingMode,
    PositionMode,
    ActivationType,
    DistanceType,
    StopLossType,
    RiskViolationType,
)

from .types import (
    Bar,
    Position,
    OrderSpec,
    Order,
    Trade,
    Balance,
    SupportResistance,
    RiskCheckResult,
)

from .config import (
    ActivationConfig,
    DistanceConfig,
    TrailingStopConfig,
    DynamicTPSLConfig,
    RiskConfig,
    TradingConfig,
    MonitoringConfig,
    StateConfig,
)

__all__ = [
    # Enums
    "OrderType",
    "OrderSide",
    "PositionSide",
    "OrderStatus",
    "PositionStatus",
    "TradingMode",
    "PositionMode",
    "ActivationType",
    "DistanceType",
    "StopLossType",
    "RiskViolationType",
    # Types
    "Bar",
    "Position",
    "OrderSpec",
    "Order",
    "Trade",
    "Balance",
    "SupportResistance",
    "RiskCheckResult",
    # Config
    "ActivationConfig",
    "DistanceConfig",
    "TrailingStopConfig",
    "DynamicTPSLConfig",
    "RiskConfig",
    "TradingConfig",
    "MonitoringConfig",
    "StateConfig",
]
