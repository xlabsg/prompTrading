from enum import Enum


class JobType(str, Enum):
    GENERATE_STRATEGY = "generate_strategy"
    GENERATE_AND_BACKTEST = "generate_and_backtest"
    REFINE_STRATEGY = "refine_strategy"
    BACKTEST = "backtest"
    REPO_IMPORT = "repo_import"
    REPO_SYNC = "repo_sync"
    TRENDING_SCRAPE = "trending_scrape"
    TRENDING_BACKTEST = "trending_backtest"
    TEMPLATE_PERFORMANCE_UPDATE = "template_performance_update"
    TEMPLATE_BACKTEST = "template_backtest"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BacktestStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ChatStatus(str, Enum):
    CHATTING = "chatting"
    READY = "ready"
    GENERATING = "generating"
    DONE = "done"


class TradingSessionMode(str, Enum):
    LIVE = "live"
    PAPER = "paper"


class TradingSessionStatus(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class StrategyRole(str, Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class SignalStatus(str, Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TradeStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    PARTIAL = "partial"


class TrendingSourceType(str, Enum):
    IDEA = "idea"
    SCRIPT = "script"


class TrendingBacktestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StrategyTemplateType(str, Enum):
    """Type of strategy template source."""
    BUILTIN = "builtin"           # Platform built-in strategy
    TRADINGVIEW = "tradingview"   # Imported from TradingView
    COMMUNITY = "community"       # Community shared strategy


class SubscriptionStatus(str, Enum):
    """Status of a strategy subscription/copy."""
    ACTIVE = "active"
    PAUSED = "paused"
    SYNC_ERROR = "sync_error"
    OUTDATED = "outdated"  # Source has updates not yet synced
