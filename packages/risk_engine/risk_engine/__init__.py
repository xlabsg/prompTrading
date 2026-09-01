"""
Trading SDK

通用交易 SDK，提供风险控制、订单管理、仓位监控等核心功能
"""
__version__ = "0.1.0"

# Core
from .core import (
    # Enums
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
    # Types
    Bar,
    Position,
    OrderSpec,
    Order,
    Trade,
    Balance,
    SupportResistance,
    RiskCheckResult,
    # Config
    ActivationConfig,
    DistanceConfig,
    TrailingStopConfig,
    DynamicTPSLConfig,
    RiskConfig,
    TradingConfig,
    MonitoringConfig,
    StateConfig,
)

# Risk
from .risk import (
    RiskValidator,
    StopLossStrategy,
    FixedStopLoss,
    TrailingStopLoss,
    StopLossManager,
    PositionManager,
    DrawdownTracker,
)

# Execution
from .execution import (
    SnowflakeIDGenerator,
    get_global_generator,
    generate_client_order_id,
    normalize_prefix,
    is_our_order,
    OrderManager,
    Reconciler,
)

# Monitoring
from .monitoring import (
    PnLCalculator,
    TradingMetrics,
)

# State
from .state import (
    TradingState,
    StateStore,
    RedisStateStore,
    PostgreSQLStateStore,
    DualStateStore,
)

# Adapters
from .adapters import (
    ExchangeAdapter,
    OKXAdapter,
)

__all__ = [
    # Version
    "__version__",
    # Core - Enums
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
    # Core - Types
    "Bar",
    "Position",
    "OrderSpec",
    "Order",
    "Trade",
    "Balance",
    "SupportResistance",
    "RiskCheckResult",
    # Core - Config
    "ActivationConfig",
    "DistanceConfig",
    "TrailingStopConfig",
    "DynamicTPSLConfig",
    "RiskConfig",
    "TradingConfig",
    "MonitoringConfig",
    "StateConfig",
    # Risk
    "RiskValidator",
    "StopLossStrategy",
    "FixedStopLoss",
    "TrailingStopLoss",
    "StopLossManager",
    "PositionManager",
    "DrawdownTracker",
    # Execution
    "SnowflakeIDGenerator",
    "get_global_generator",
    "generate_client_order_id",
    "normalize_prefix",
    "is_our_order",
    "OrderManager",
    "Reconciler",
    # Monitoring
    "PnLCalculator",
    "TradingMetrics",
    # State
    "TradingState",
    "StateStore",
    "RedisStateStore",
    "PostgreSQLStateStore",
    "DualStateStore",
    # Adapters
    "ExchangeAdapter",
    "OKXAdapter",
]
