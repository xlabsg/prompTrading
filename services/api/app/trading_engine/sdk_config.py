"""
Risk Engine Configuration Builder

从数据库 TradingConfig 构建 Risk Engine 配置
"""
from risk_engine import (
    RiskConfig, TradingConfig as SDKTradingConfig,
    TrailingStopConfig, DynamicTPSLConfig,
    ActivationConfig, DistanceConfig,
    ActivationType, DistanceType, TradingMode, PositionMode
)
from control_plane.models import TradingConfig as DBTradingConfig


def build_risk_config(db_config: DBTradingConfig) -> RiskConfig:
    """从数据库配置构建风险配置"""
    return RiskConfig(
        # 仓位限制
        max_position_pct=db_config.max_position_pct,
        max_leverage=getattr(db_config, 'max_leverage', 10),

        # 止损配置
        stop_loss_pct=db_config.stop_loss_pct / 100.0 if db_config.stop_loss_pct else None,
        require_stop_loss=getattr(db_config, 'require_stop_loss', True),

        # 移动止损
        trailing_stop=TrailingStopConfig(
            enabled=getattr(db_config, 'trailing_stop_enabled', False),
            activation=ActivationConfig(
                type=ActivationType.PROFIT_PCT,
                threshold=getattr(db_config, 'trailing_activation_pct', 0.005)
            ),
            distance=DistanceConfig(
                type=DistanceType.PERCENTAGE,
                value=getattr(db_config, 'trailing_distance_pct', 0.008)
            )
        ),

        # 动态 TP/SL
        dynamic_tpsl=DynamicTPSLConfig(
            enabled=getattr(db_config, 'dynamic_tpsl_enabled', False),
            use_support_resistance=getattr(db_config, 'use_support_resistance', True),
            use_atr_buffer=True,
            min_risk_reward=getattr(db_config, 'min_risk_reward', 1.0),
            fallback_sl_pct=getattr(db_config, 'fallback_sl_pct', 0.01),
            fallback_tp_pct=getattr(db_config, 'fallback_tp_pct', 0.02),
        ),

        # 亏损限制
        max_daily_loss_pct=getattr(db_config, 'max_daily_loss_pct', None),
        max_drawdown_pct=getattr(db_config, 'max_drawdown_pct', None),
    )


def build_trading_config(db_config: DBTradingConfig) -> SDKTradingConfig:
    """从数据库配置构建交易配置"""
    return SDKTradingConfig(
        exchange=db_config.exchange,
        symbol=db_config.symbol,

        # 交易模式（OKX 默认逐仓）
        trading_mode=TradingMode.ISOLATED if db_config.exchange == "okx" else TradingMode.CROSS,
        position_mode=PositionMode.LONG_SHORT,

        # 杠杆
        leverage=getattr(db_config, 'leverage', 1),

        # 风险配置
        risk=build_risk_config(db_config),

        # 对账配置
        reconcile_interval_seconds=60,
        reconcile_on_startup=True,
        reconcile_on_error=True,

        # 订单超时
        order_timeout_seconds=900,  # 15 minutes
        cancel_stale_orders=True,
    )
