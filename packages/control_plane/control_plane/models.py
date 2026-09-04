import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from control_plane.enums import (
    BacktestStatus,
    ChatStatus,
    LogLevel,
    TradingSessionStatus,
    OrderSide,
    OrderType,
    OrderStatus,
    PositionSide,
    PositionStatus,
    StrategyRole,
    SignalStatus,
    TradeStatus,
)


class Base(DeclarativeBase):
    pass


def _uuid_str() -> str:
    return str(uuid.uuid4())

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Link to imported repository (optional)
    repo_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Chat-based strategy creation
    chat_status: Mapped[ChatStatus] = mapped_column(
        SAEnum(ChatStatus, native_enum=False), default=ChatStatus.CHATTING, nullable=False
    )
    chat_history: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True, default=list)
    chat_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)  # Final config after confirmation

    versions: Mapped[list["StrategyVersion"]] = relationship(back_populates="strategy", cascade="all, delete-orphan")
    backtests: Mapped[list["BacktestRun"]] = relationship(back_populates="strategy", cascade="all, delete-orphan")
    trading_config: Mapped[Optional["TradingConfig"]] = relationship(back_populates="strategy", cascade="all, delete-orphan", uselist=False)
    members: Mapped[list["StrategyMember"]] = relationship(back_populates="strategy", cascade="all, delete-orphan")
    exchange_accounts: Mapped[list["StrategyExchangeAccount"]] = relationship(back_populates="strategy", cascade="all, delete-orphan")
    signals: Mapped[list["StrategySignal"]] = relationship(back_populates="strategy", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    email: Mapped[Optional[str]] = mapped_column(String(320), unique=True, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    subscription_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    subscription_plan_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    subscription_current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    strategy_memberships: Mapped[list["StrategyMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    provider: Mapped[str] = mapped_column(String(50), index=True)
    provider_user_id: Mapped[str] = mapped_column(String(200), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="oauth_accounts")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="sessions")


class PendingOAuth(Base):
    __tablename__ = "pending_oauth"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    provider: Mapped[str] = mapped_column(String(50), index=True)
    state: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    redirect_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StrategyMember(Base):
    __tablename__ = "strategy_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[StrategyRole] = mapped_column(
        SAEnum(StrategyRole, native_enum=False), default=StrategyRole.VIEWER, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    strategy: Mapped["Strategy"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="strategy_memberships")


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relative path under the strategy workspace, e.g. "versions/<id>/"
    workspace_path: Mapped[str] = mapped_column(String(500))

    # Optional provenance
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    strategy: Mapped["Strategy"] = relationship(back_populates="versions")


class StrategyExchangeAccount(Base):
    __tablename__ = "strategy_exchange_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    exchange: Mapped[str] = mapped_column(String(50))
    api_key_encrypted: Mapped[str] = mapped_column(Text)
    api_secret_encrypted: Mapped[str] = mapped_column(Text)
    api_passphrase_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    strategy: Mapped["Strategy"] = relationship(back_populates="exchange_accounts")
    sessions: Mapped[list["TradingSession"]] = relationship(back_populates="exchange_account", cascade="all, delete-orphan")


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    exchange: Mapped[str] = mapped_column(String(50))
    symbol: Mapped[str] = mapped_column(String(50))
    interval: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Optional range, interpreted by the backtest runner
    start_ms: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    end_ms: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="queued", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"), index=True)
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id", ondelete="SET NULL"), nullable=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)

    status: Mapped[BacktestStatus] = mapped_column(
        SAEnum(BacktestStatus, native_enum=False), default=BacktestStatus.QUEUED, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    run_path: Mapped[str] = mapped_column(String(500))  # relative, e.g. "runs/<id>/"
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    result_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    strategy: Mapped["Strategy"] = relationship(back_populates="backtests")


class TradingConfig(Base):
    """Configuration for live trading on a strategy."""
    __tablename__ = "trading_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"), index=True, unique=True)
    account_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("strategy_exchange_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    exchange: Mapped[str] = mapped_column(String(50))  # okx, binance
    symbol: Mapped[str] = mapped_column(String(50))  # Primary symbol for compatibility
    symbols: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    intervals: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    
    # Encrypted credentials
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_secret_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_passphrase_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # OKX only
    
    # Risk management
    max_position_pct: Mapped[float] = mapped_column(default=10.0)  # Max position as % of balance
    stop_loss_pct: Mapped[float] = mapped_column(default=5.0)  # Stop loss %

    # Risk control
    leverage: Mapped[int] = mapped_column(Integer, default=1)
    max_leverage: Mapped[int] = mapped_column(Integer, default=10)
    max_daily_loss_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    max_drawdown_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    require_stop_loss: Mapped[bool] = mapped_column(default=True)

    # Trailing stop
    trailing_stop_enabled: Mapped[bool] = mapped_column(default=False)
    trailing_activation_pct: Mapped[float] = mapped_column(default=0.005)
    trailing_distance_pct: Mapped[float] = mapped_column(default=0.008)

    # Dynamic TP/SL
    dynamic_tpsl_enabled: Mapped[bool] = mapped_column(default=False)
    use_support_resistance: Mapped[bool] = mapped_column(default=True)
    min_risk_reward: Mapped[float] = mapped_column(default=1.0)
    fallback_sl_pct: Mapped[float] = mapped_column(default=0.01)
    fallback_tp_pct: Mapped[float] = mapped_column(default=0.02)
    
    is_active: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    strategy: Mapped["Strategy"] = relationship(back_populates="trading_config")
    exchange_account: Mapped[Optional["StrategyExchangeAccount"]] = relationship()
    sessions: Mapped[list["TradingSession"]] = relationship(back_populates="config", cascade="all, delete-orphan")


class TradingSession(Base):
    """A live trading session."""
    __tablename__ = "trading_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    config_id: Mapped[str] = mapped_column(ForeignKey("trading_configs.id", ondelete="CASCADE"), index=True)
    exchange_account_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("strategy_exchange_accounts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    
    status: Mapped["TradingSessionStatus"] = mapped_column(
        SAEnum(TradingSessionStatus, native_enum=False), default=TradingSessionStatus.STARTING, nullable=False
    )
    
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Runtime info
    container_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Summary stats (updated periodically)
    total_pnl: Mapped[float] = mapped_column(default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)

    config: Mapped["TradingConfig"] = relationship(back_populates="sessions")
    exchange_account: Mapped[Optional["StrategyExchangeAccount"]] = relationship(back_populates="sessions")
    orders: Mapped[list["Order"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    positions: Mapped[list["Position"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    logs: Mapped[list["TradingLog"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    trades: Mapped[list["TradingTrade"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Order(Base):
    """An order placed during a trading session."""
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    session_id: Mapped[str] = mapped_column(ForeignKey("trading_sessions.id", ondelete="CASCADE"), index=True)
    
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    client_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    symbol: Mapped[str] = mapped_column(String(50))
    side: Mapped["OrderSide"] = mapped_column(SAEnum(OrderSide, native_enum=False), nullable=False)
    order_type: Mapped["OrderType"] = mapped_column(SAEnum(OrderType, native_enum=False), nullable=False)
    
    price: Mapped[Optional[float]] = mapped_column(nullable=True)  # None for market orders
    size: Mapped[float] = mapped_column()
    filled_size: Mapped[float] = mapped_column(default=0.0)
    avg_fill_price: Mapped[Optional[float]] = mapped_column(nullable=True)
    
    status: Mapped["OrderStatus"] = mapped_column(
        SAEnum(OrderStatus, native_enum=False), default=OrderStatus.PENDING, nullable=False
    )
    
    take_profit: Mapped[Optional[float]] = mapped_column(nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(nullable=True)
    reduce_only: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    
    session: Mapped["TradingSession"] = relationship(back_populates="orders")


class Position(Base):
    """A position held during a trading session."""
    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    session_id: Mapped[str] = mapped_column(ForeignKey("trading_sessions.id", ondelete="CASCADE"), index=True)
    
    symbol: Mapped[str] = mapped_column(String(50))
    side: Mapped["PositionSide"] = mapped_column(SAEnum(PositionSide, native_enum=False), nullable=False)
    
    size: Mapped[float] = mapped_column()
    entry_price: Mapped[float] = mapped_column()
    current_price: Mapped[float] = mapped_column()
    
    unrealized_pnl: Mapped[float] = mapped_column(default=0.0)
    realized_pnl: Mapped[float] = mapped_column(default=0.0)
    
    status: Mapped["PositionStatus"] = mapped_column(
        SAEnum(PositionStatus, native_enum=False), default=PositionStatus.OPEN, nullable=False
    )
    
    leverage: Mapped[int] = mapped_column(Integer, default=1)
    margin: Mapped[float] = mapped_column(default=0.0)
    liquidation_price: Mapped[Optional[float]] = mapped_column(nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(nullable=True)
    stop_loss_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    trailing_stop_activated: Mapped[bool] = mapped_column(default=False)
    trailing_stop_price: Mapped[Optional[float]] = mapped_column(nullable=True)
    highest_price: Mapped[Optional[float]] = mapped_column(nullable=True)
    lowest_price: Mapped[Optional[float]] = mapped_column(nullable=True)

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    session: Mapped["TradingSession"] = relationship(back_populates="positions")


class TradingLog(Base):
    """Log entry for a trading session."""
    __tablename__ = "trading_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    session_id: Mapped[str] = mapped_column(ForeignKey("trading_sessions.id", ondelete="CASCADE"), index=True)
    
    level: Mapped["LogLevel"] = mapped_column(SAEnum(LogLevel, native_enum=False), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    log_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    
    session: Mapped["TradingSession"] = relationship(back_populates="logs")


class StrategySignal(Base):
    __tablename__ = "strategy_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("trading_sessions.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(50))
    interval: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    side: Mapped[str] = mapped_column(String(10))
    price: Mapped[float] = mapped_column(default=0.0)
    confidence: Mapped[float] = mapped_column(default=0.0)
    target: Mapped[Optional[float]] = mapped_column(nullable=True)
    status: Mapped[SignalStatus] = mapped_column(
        SAEnum(SignalStatus, native_enum=False), default=SignalStatus.PENDING, nullable=False
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    params_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    indicators: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    position: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    price_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    strategy: Mapped["Strategy"] = relationship(back_populates="signals")
    session: Mapped["TradingSession"] = relationship()


class TradingTrade(Base):
    __tablename__ = "trading_trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    session_id: Mapped[str] = mapped_column(ForeignKey("trading_sessions.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(50))
    side: Mapped[str] = mapped_column(String(10))
    entry_price: Mapped[float] = mapped_column(default=0.0)
    exit_price: Mapped[Optional[float]] = mapped_column(nullable=True)
    quantity: Mapped[float] = mapped_column(default=0.0)
    pnl: Mapped[Optional[float]] = mapped_column(nullable=True)
    fee: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[TradeStatus] = mapped_column(
        SAEnum(TradeStatus, native_enum=False), default=TradeStatus.OPEN, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["TradingSession"] = relationship(back_populates="trades")


# --- Code repositories & search ---

class Installation(Base):
    __tablename__ = "installations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    provider: Mapped[str] = mapped_column(String(32), default="github")
    installation_id: Mapped[str] = mapped_column(String(64), index=True)
    account_login: Mapped[str] = mapped_column(String(200))
    target_type: Mapped[str] = mapped_column(String(20), default="Organization")  # or User
    permissions: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    provider: Mapped[str] = mapped_column(String(32), default="github", index=True)
    provider_repo_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    owner: Mapped[str] = mapped_column(String(200), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    visibility: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    default_branch: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    installation_id: Mapped[Optional[str]] = mapped_column(ForeignKey("installations.id", ondelete="SET NULL"), nullable=True)
    github_installation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)  # GitHub's raw installation ID for API calls
    sync_mode: Mapped[str] = mapped_column(String(20), default="both")  # webhook/schedule/both
    tracked_branches: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/archived/removed
    quota_state: Mapped[str] = mapped_column(String(20), default="ok")  # ok/over_quota
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class RepoSync(Base):
    __tablename__ = "repo_syncs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    branch: Mapped[str] = mapped_column(String(200), index=True)
    last_remote_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_local_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bytes_transferred: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)



class TradingViewTrendingStrategy(Base):
    """TradingView trending strategies scraped from scripts and ideas."""
    __tablename__ = "tradingview_trending_strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    tradingview_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    author_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    likes: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)

    content_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    script_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    url: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)

    detected_symbols: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)  # ["BTCUSDT", "ETHUSDT"]
    detected_markets: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)  # ["crypto"]

    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    trending_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trending_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    backtest_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    backtest_results: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    backtest_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class TrendingSchedule(Base):
    """Scheduled configuration for trending strategy scraping."""
    __tablename__ = "trending_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False, default="0 */6 * * *")
    source_types: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    max_count: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    auto_backtest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_backtest_top_n: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class StrategyTemplate(Base):
    """
    Strategy template source - a static strategy configuration that can be copied/subscribed.

    Templates don't have trading sessions or exchange accounts - they are pure configurations.
    When a user subscribes, a Strategy record is created with its own copy.
    """
    __tablename__ = "strategy_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)

    # Template identity
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    template_type: Mapped[str] = mapped_column(String(50))  # builtin, tradingview, community

    # Source reference (for TradingView imports)
    source_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)  # FK to TradingViewTrendingStrategy

    # Template content (the actual strategy code/prompt)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)  # Trading config template
    code_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)  # Version snapshot

    # Metadata
    version: Mapped[int] = mapped_column(Integer, default=1)
    author: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    tags: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)

    # Strategy classification (for SaaS marketplace)
    risk_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # low, medium, high
    trading_frequency: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # low_frequency, intraday, high_frequency
    complexity_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5 scale
    min_capital_usdt: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True, default=100.0)
    supported_exchanges: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    supported_symbols: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)

    # Performance summary (aggregated from backtests)
    backtest_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    # Example backtest_summary:
    # {
    #   "total_return": 25.5,
    #   "sharpe_ratio": 1.8,
    #   "max_drawdown": -8.2,
    #   "win_rate": 0.65,
    #   "profit_factor": 2.1,
    #   "avg_trade_pnl_pct": 0.8,
    #   "backtest_period": "2024-01-01 to 2024-12-31",
    # }

    # Visibility and sharing
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)

    # Subscription stats
    subscriber_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    subscriptions: Mapped[list["StrategySubscription"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )
    performance_runs: Mapped[list["TemplatePerformanceRun"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )
    signals: Mapped[list["TemplateSignal"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class StrategySubscription(Base):
    """
    A user's subscription/copy of a strategy template.

    When a user subscribes to a template, a Strategy record is created.
    The subscription maintains the link to the source template for sync purposes.
    """
    __tablename__ = "strategy_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)

    # Links
    template_id: Mapped[str] = mapped_column(
        ForeignKey("strategy_templates.id", ondelete="CASCADE"), index=True
    )
    strategy_id: Mapped[str] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Subscription status
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
    )

    # Sync tracking
    subscribed_version: Mapped[int] = mapped_column(Integer, default=1)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # User configuration (trading params, overrides)
    user_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    # Example user_config:
    # {
    #   "exchange": "okx",
    #   "symbol": "BTCUSDT",
    #   "max_position_pct": 20.0,
    #   "stop_loss_pct": 5.0,
    #   "custom_params": {...}
    # }

    # Telegram notification configuration
    telegram_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    # Example telegram_config:
    # {
    #   "bot_token": "encrypted_token",
    #   "chat_id": "-1001234567890",
    #   "enabled": true,
    #   "notify_on_signal": true,
    #   "notify_on_execution": true,
    #   "notify_on_error": true
    # }

    # Telegram notification status
    telegram_last_notification_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_notification_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    template: Mapped["StrategyTemplate"] = relationship(back_populates="subscriptions")
    strategy: Mapped["Strategy"] = relationship()
    user: Mapped["User"] = relationship()


class TemplatePerformanceRun(Base):
    """Historical backtest run for a strategy template."""
    __tablename__ = "template_performance_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("strategy_templates.id", ondelete="CASCADE"), index=True
    )

    # Run metadata
    run_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exchange: Mapped[str] = mapped_column(String(50))
    symbol: Mapped[str] = mapped_column(String(50))
    interval: Mapped[str] = mapped_column(String(20))
    start_ms: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    end_ms: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Metrics (JSON matching BacktestRun.metrics structure)
    # Example: {
    #   "total_return": 45.2,
    #   "sharpe_ratio": 2.3,
    #   "max_drawdown": -12.5,
    #   "win_rate": 62.5,
    #   "total_trades": 156,
    #   "profit_factor": 1.8,
    #   "avg_trade_pnl": 120.5,
    #   "equity_curve": [[1698792000000, 10000], [1698878400000, 10230], ...]
    # }
    metrics: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="succeeded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    template: Mapped["StrategyTemplate"] = relationship(back_populates="performance_runs")


class TemplateSignal(Base):
    """Historical signal generated by a template."""
    __tablename__ = "template_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("strategy_templates.id", ondelete="CASCADE"), index=True
    )

    # Signal data
    symbol: Mapped[str] = mapped_column(String(50))
    side: Mapped[str] = mapped_column(String(10))
    price: Mapped[float] = mapped_column()
    confidence: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="executed")

    # Outcome tracking
    entry_price: Mapped[Optional[float]] = mapped_column(nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(nullable=True)
    pnl: Mapped[Optional[float]] = mapped_column(nullable=True)
    hold_duration_hours: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Metadata
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    indicators: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    template: Mapped["StrategyTemplate"] = relationship(back_populates="signals")


class TemplatePerformanceSchedule(Base):
    """Schedule configuration for template performance updates."""
    __tablename__ = "template_performance_schedule"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), default="0 2 * * *")

    # Generation config
    templates_per_batch: Mapped[int] = mapped_column(Integer, default=5)
    backtest_days_history: Mapped[int] = mapped_column(Integer, default=90)
    signals_per_day: Mapped[int] = mapped_column(Integer, default=3)

    # Data quality
    max_signals_per_template: Mapped[int] = mapped_column(Integer, default=100)

    # Tracking
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
