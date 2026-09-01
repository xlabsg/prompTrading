"""
Trading SDK Core Enums

定义所有核心枚举类型
"""
from enum import Enum


class OrderType(str, Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderSide(str, Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class PositionSide(str, Enum):
    """仓位方向"""
    LONG = "long"
    SHORT = "short"
    NET = "net"  # 单向持仓模式


class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "pending"  # 等待提交
    SUBMITTED = "submitted"  # 已提交到交易所
    OPEN = "open"  # 已接受，等待成交
    PARTIALLY_FILLED = "partially_filled"  # 部分成交
    FILLED = "filled"  # 完全成交
    CANCELLED = "cancelled"  # 已取消
    REJECTED = "rejected"  # 被拒绝
    EXPIRED = "expired"  # 已过期
    FAILED = "failed"  # 失败


class PositionStatus(str, Enum):
    """仓位状态"""
    OPEN = "open"
    CLOSED = "closed"


class TradingMode(str, Enum):
    """交易模式"""
    CROSS = "cross"  # 全仓
    ISOLATED = "isolated"  # 逐仓


class PositionMode(str, Enum):
    """持仓模式"""
    NET = "net_mode"  # 单向持仓
    LONG_SHORT = "long_short_mode"  # 双向持仓


class ActivationType(str, Enum):
    """移动止损激活类型"""
    PROFIT_PCT = "profit_pct"  # 利润百分比
    PROFIT_DOLLAR = "profit_dollar"  # 利润金额
    IMMEDIATE = "immediate"  # 立即激活


class DistanceType(str, Enum):
    """移动止损距离类型"""
    PERCENTAGE = "percentage"  # 百分比
    ATR = "atr"  # ATR 倍数
    FIXED_DOLLAR = "fixed_dollar"  # 固定金额


class StopLossType(str, Enum):
    """止损类型"""
    FIXED = "fixed"  # 固定止损
    TRAILING = "trailing"  # 移动止损
    DYNAMIC = "dynamic"  # 动态止损（基于支撑阻力）


class RiskViolationType(str, Enum):
    """风险违规类型"""
    MAX_POSITION_EXCEEDED = "max_position_exceeded"  # 超过最大仓位
    MAX_LEVERAGE_EXCEEDED = "max_leverage_exceeded"  # 超过最大杠杆
    INSUFFICIENT_BALANCE = "insufficient_balance"  # 余额不足
    DAILY_LOSS_LIMIT = "daily_loss_limit"  # 达到每日亏损限制
    MAX_DRAWDOWN_EXCEEDED = "max_drawdown_exceeded"  # 超过最大回撤
    MIN_RISK_REWARD = "min_risk_reward"  # 不满足最小风险回报比
    INVALID_STOP_LOSS = "invalid_stop_loss"  # 无效的止损价格
