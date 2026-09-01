"""
Trading SDK Configuration Classes

定义所有配置类
"""
from dataclasses import dataclass, field
from typing import Optional
from .enums import ActivationType, DistanceType, TradingMode, PositionMode


@dataclass
class ActivationConfig:
    """移动止损激活配置"""
    type: ActivationType = ActivationType.PROFIT_PCT
    threshold: float = 0.005  # 0.5% 利润激活


@dataclass
class DistanceConfig:
    """移动止损距离配置"""
    type: DistanceType = DistanceType.PERCENTAGE
    value: float = 0.008  # 0.8% 距离
    atr_multiplier: float = 1.5  # ATR 倍数（如果使用 ATR）


@dataclass
class TrailingStopConfig:
    """移动止损配置"""
    enabled: bool = False
    activation: ActivationConfig = field(default_factory=ActivationConfig)
    distance: DistanceConfig = field(default_factory=DistanceConfig)


@dataclass
class DynamicTPSLConfig:
    """动态 TP/SL 配置"""
    enabled: bool = False
    use_support_resistance: bool = True  # 使用支撑阻力
    use_atr_buffer: bool = True  # 使用 ATR 缓冲
    sr_buffer_pct: float = 0.003  # 支撑阻力缓冲 0.3%
    min_sl_pct: float = 0.005  # 最小止损距离 0.5%
    atr_sl_multiplier: float = 1.5  # ATR 止损倍数
    min_risk_reward: float = 1.0  # 最小风险回报比
    fallback_sl_pct: float = 0.01  # 兜底止损 1%
    fallback_tp_pct: float = 0.02  # 兜底止盈 2%


@dataclass
class RiskConfig:
    """风险控制配置"""
    # 仓位限制
    max_position_pct: float = 100.0  # 最大仓位百分比（相对于账户权益）
    max_leverage: int = 10  # 最大杠杆

    # 止损配置
    stop_loss_pct: Optional[float] = None  # 强制止损百分比
    trailing_stop: TrailingStopConfig = field(default_factory=TrailingStopConfig)
    dynamic_tpsl: DynamicTPSLConfig = field(default_factory=DynamicTPSLConfig)

    # 亏损限制
    max_daily_loss_pct: Optional[float] = None  # 最大每日亏损百分比
    max_daily_loss_dollar: Optional[float] = None  # 最大每日亏损金额
    max_drawdown_pct: Optional[float] = None  # 最大回撤百分比

    # 订单限制
    min_order_size: float = 0.0  # 最小订单大小
    max_order_size: Optional[float] = None  # 最大订单大小
    max_slippage_pct: float = 0.01  # 最大滑点 1%

    # 其他
    require_stop_loss: bool = True  # 是否强制要求止损
    allow_hedging: bool = False  # 是否允许对冲（同时持有多空）


@dataclass
class TradingConfig:
    """交易配置"""
    # 基本信息
    exchange: str
    symbol: str
    trading_mode: TradingMode = TradingMode.ISOLATED
    position_mode: PositionMode = PositionMode.LONG_SHORT

    # 杠杆
    leverage: int = 1

    # 风险配置
    risk: RiskConfig = field(default_factory=RiskConfig)

    # 对账配置
    reconcile_interval_seconds: int = 60  # 对账间隔
    reconcile_on_startup: bool = True  # 启动时对账
    reconcile_on_error: bool = True  # 错误时对账

    # 订单超时
    order_timeout_seconds: int = 900  # 15 分钟
    cancel_stale_orders: bool = True  # 自动取消陈旧订单


@dataclass
class MonitoringConfig:
    """监控配置"""
    # 更新频率
    position_update_interval_seconds: int = 5
    balance_update_interval_seconds: int = 10
    metrics_update_interval_seconds: int = 60

    # PnL 计算
    include_fees: bool = True  # PnL 计算包含费用
    use_mark_price: bool = True  # 使用标记价格而非最新价

    # 通知
    notify_on_fill: bool = True
    notify_on_stop_loss: bool = True
    notify_on_take_profit: bool = True
    notify_on_error: bool = True


@dataclass
class StateConfig:
    """状态管理配置"""
    # 持久化
    enable_redis: bool = True
    enable_postgres: bool = True
    save_interval_seconds: float = 1.0  # 保存间隔（限流）

    # Redis 配置
    redis_key_prefix: str = "trading:"
    redis_ttl_seconds: int = 86400  # 24 小时

    # 文件备份（可选）
    enable_file_backup: bool = False
    backup_directory: Optional[str] = None
