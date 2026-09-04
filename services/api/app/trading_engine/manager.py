"""
Trading Session Manager with Risk Engine Integration

交易会话管理器（集成 Risk Engine）
"""
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.enums import LogLevel, OrderStatus, TradingSessionStatus
from control_plane.models import Order, StrategyExchangeAccount, TradingConfig, TradingSession
from app.trading_engine.executor import OrderExecutor
from app.trading_engine.monitor import PositionMonitor
from app.trading_engine.strategy_runner import StrategyRunner
from app.trading_engine.logging_utils import log_trading_event
from app.trading_engine.sdk_config import build_trading_config

# Risk Engine imports
from risk_engine import Reconciler, OrderManager

logger = logging.getLogger(__name__)


class TradingSessionManager:
    """
    交易会话管理器（集成 Risk Engine）

    功能：
    - 定期对账机制（60 秒）
    - 风险控制（9项验证）
    - 移动止损
    - 订单生命周期管理
    """

    # Global registry of active sessions
    _active_sessions: dict[str, "TradingSessionManager"] = {}
    _lock = threading.Lock()

    def __init__(
        self,
        session: TradingSession,
        config: TradingConfig,
        account: StrategyExchangeAccount,
        db: Session
    ):
        """
        初始化增强交易会话管理器

        Args:
            session: 交易会话记录
            config: 交易配置
            account: 交易账户
            db: 数据库会话
        """
        self.session = session
        self.config = config
        self.account = account
        self.db = db
        self.session_id = session.id

        # Build SDK configuration
        self.sdk_config = build_trading_config(config)

        # Create executor and monitor
        self.executor = OrderExecutor(config, session.id, db, account)
        self.monitor = PositionMonitor(
            config=config,
            session_id=session.id,
            db=db,
            account=account,
            exchange_adapter=self.executor.exchange_adapter,
            trailing_stop_config=self.sdk_config.risk.trailing_stop
        )

        # SDK components
        self.order_manager = OrderManager()
        self.reconciler = Reconciler(
            exchange_adapter=self.executor.exchange_adapter,
            order_manager=self.order_manager
        )

        # Strategy runner
        self._strategy_runner: StrategyRunner | None = None

        # Monitoring threads
        self._monitor_thread: Optional[threading.Thread] = None
        self._reconcile_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Reconciliation tracking
        self._last_reconcile_time = 0
        self._reconcile_interval = self.sdk_config.reconcile_interval_seconds

        logger.info(
            f"Enhanced TradingSessionManager initialized for session {session.id} "
            f"(reconcile_interval: {self._reconcile_interval}s)"
        )

    def log_event(self, level: LogLevel, message: str, metadata: Optional[dict] = None) -> None:
        """写入日志到数据库"""
        log_trading_event(
            self.db,
            strategy_id=self.config.strategy_id,
            session_id=self.session_id,
            level=level,
            message=message,
            metadata=metadata,
        )

    @classmethod
    def start_session(cls, session_id: str, db: Session) -> "TradingSessionManager":
        """
        启动新的交易会话

        Args:
            session_id: 交易会话 ID
            db: 数据库会话

        Returns:
            交易会话管理器

        Raises:
            ValueError: 如果会话已经在运行或未找到
        """
        with cls._lock:
            if session_id in cls._active_sessions:
                raise ValueError(f"Session {session_id} is already running")

            # Load session and config from DB
            session = db.get(TradingSession, session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            config = db.get(TradingConfig, session.config_id)
            if not config:
                raise ValueError(f"Trading config not found for session {session_id}")

            account = None
            if session.exchange_account_id:
                account = db.get(StrategyExchangeAccount, session.exchange_account_id)
            if account is None:
                raise ValueError("exchange_account_not_found")

            # Create enhanced manager
            manager = cls(session, config, account, db)

            # Update session status
            session.status = TradingSessionStatus.RUNNING
            db.commit()

            # Log session start
            manager.log_event(
                LogLevel.INFO,
                f"Enhanced trading session started for {config.exchange}:{config.symbol}",
                {
                    "exchange": config.exchange,
                    "symbol": config.symbol,
                    "leverage": getattr(config, 'leverage', 1),
                    "trailing_stop_enabled": getattr(config, 'trailing_stop_enabled', False),
                }
            )

            # Perform initial reconciliation if configured
            if manager.sdk_config.reconcile_on_startup:
                try:
                    manager._perform_reconciliation(db)
                except Exception as e:
                    logger.error(f"Failed to reconcile on startup: {e}", exc_info=True)

            # Start monitoring
            manager._start_monitoring()

            # Register in active sessions
            cls._active_sessions[session_id] = manager

            logger.info(f"Enhanced trading session started: {session_id}")
            return manager

    @classmethod
    def stop_session(cls, session_id: str, db: Session) -> None:
        """
        停止交易会话

        Args:
            session_id: 交易会话 ID
            db: 数据库会话
        """
        with cls._lock:
            manager = cls._active_sessions.pop(session_id, None)
            if not manager:
                logger.warning(f"Session {session_id} is not running")
                return

            # Stop monitoring
            manager._stop_monitoring()

            # Perform final reconciliation
            try:
                manager._perform_reconciliation(db)
            except Exception as e:
                logger.error(f"Failed to reconcile on stop: {e}", exc_info=True)

            # Log session stop
            manager.log_event(
                LogLevel.INFO,
                "Enhanced trading session stopped",
                {"total_pnl": manager.monitor.get_total_pnl()}
            )

            # Update session status
            session = db.get(TradingSession, session_id)
            if session:
                session.status = TradingSessionStatus.STOPPED
                session.stopped_at = datetime.now(timezone.utc)
                session.total_pnl = manager.monitor.get_total_pnl()
                db.commit()

            logger.info(f"Enhanced trading session stopped: {session_id}")

    @classmethod
    def get_session(cls, session_id: str) -> Optional["TradingSessionManager"]:
        """
        获取活跃的交易会话管理器

        Args:
            session_id: 交易会话 ID

        Returns:
            交易会话管理器或 None
        """
        return cls._active_sessions.get(session_id)

    def _start_monitoring(self) -> None:
        """启动仓位监控和对账线程"""
        self._stop_event.clear()

        # Start position monitoring thread
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

        self.log_event(LogLevel.INFO, "Position monitoring started")
        logger.info(f"Position monitoring started for session {self.session_id}")

        # Start live strategy runner
        if not self._strategy_runner:
            self._strategy_runner = StrategyRunner(self.session_id, self.config, self.account)
            self._strategy_runner.start()
            self.log_event(LogLevel.INFO, "Live strategy runner started")

    def _stop_monitoring(self) -> None:
        """停止监控线程"""
        self._stop_event.set()

        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)

        logger.info(f"Position monitoring stopped for session {self.session_id}")

        if self._strategy_runner:
            self._strategy_runner.stop()
            self.log_event(LogLevel.INFO, "Live strategy runner stopped")
            self._strategy_runner = None

    def _monitor_loop(self) -> None:
        """
        监控循环（后台线程）

        更新：
        - 从交易所获取仓位数据
        - 更新订单状态
        - 更新会话 PnL
        - 定期对账
        """
        from app.main import app

        session_factory = app.state.session_factory
        reconcile_counter = 0

        while not self._stop_event.is_set():
            with session_factory() as thread_db:
                try:
                    # Reload config for this thread
                    config = thread_db.get(TradingConfig, self.config.id)
                    if not config:
                        logger.error(f"Config not found for session {self.session_id}")
                        break

                    # Load session
                    session = thread_db.get(TradingSession, self.session_id)
                    if not session:
                        logger.error(f"Session not found: {self.session_id}")
                        break

                    # Load account
                    account = None
                    if session.exchange_account_id:
                        account = thread_db.get(StrategyExchangeAccount, session.exchange_account_id)
                    if not account:
                        logger.error(f"Account not found for session {self.session_id}")
                        break

                    # Create thread-local components
                    executor = OrderExecutor(config, session.id, thread_db, account)
                    monitor = PositionMonitor(
                        config=config,
                        session_id=session.id,
                        db=thread_db,
                        account=account,
                        exchange_adapter=executor.exchange_adapter,
                        trailing_stop_config=self.sdk_config.risk.trailing_stop
                    )

                    # Update positions (includes trailing stop checks)
                    monitor.update_positions()

                    # Update open orders
                    self._update_open_orders_thread(executor, thread_db)

                    # Update session stats
                    self._update_session_stats_thread(monitor, thread_db)

                    # Perform reconciliation every N intervals
                    reconcile_counter += 1
                    if reconcile_counter >= (self._reconcile_interval // 5):  # 5 seconds per loop
                        try:
                            self._perform_reconciliation(thread_db)
                            reconcile_counter = 0
                        except Exception as e:
                            logger.error(f"Reconciliation failed: {e}", exc_info=True)
                            if self.sdk_config.reconcile_on_error:
                                # Try again next iteration
                                reconcile_counter = (self._reconcile_interval // 5) - 1

                except Exception as e:
                    logger.error(f"Error in monitoring loop for session {self.session_id}: {e}", exc_info=True)

            # Sleep for 5 seconds between updates
            self._stop_event.wait(5.0)

    def _perform_reconciliation(self, db: Session) -> None:
        """
        执行对账

        Args:
            db: 数据库会话
        """
        try:
            # Get local orders from DB
            local_orders = db.execute(
                select(Order)
                .where(Order.session_id == self.session_id)
                .where(Order.status.in_([OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]))
            ).scalars().all()

            # Convert to SDK Order objects for reconciliation
            from risk_engine import Order as SDKOrder, OrderStatus as SDKOrderStatus, OrderSide, OrderType, PositionSide as SDKPositionSide
            from decimal import Decimal

            sdk_orders = []
            for db_order in local_orders:
                side_str = db_order.side.value if hasattr(db_order.side, "value") else str(db_order.side)
                order_type_str = db_order.order_type.value if hasattr(db_order.order_type, "value") else str(db_order.order_type)
                status_str = db_order.status.value if hasattr(db_order.status, "value") else str(db_order.status)
                sdk_order = SDKOrder(
                    order_id=db_order.id,
                    client_order_id=db_order.client_order_id or db_order.id,
                    exchange_order_id=db_order.exchange_order_id,
                    symbol=db_order.symbol,
                    side=OrderSide(side_str),
                    order_type=OrderType.MARKET if order_type_str == "market" else OrderType.LIMIT,
                    position_side=SDKPositionSide.LONG if side_str == "buy" else SDKPositionSide.SHORT,
                    status=SDKOrderStatus(status_str),
                    size=Decimal(str(db_order.size)),
                    filled_size=Decimal(str(db_order.filled_size or "0")),
                    price=Decimal(str(db_order.price)) if db_order.price else None,
                )
                # Register with order manager
                self.order_manager.add_order(sdk_order)
                sdk_orders.append(sdk_order)

            # Reconcile orders
            order_result = self.reconciler.reconcile_orders(sdk_orders, self.config.symbol)

            # Log discrepancies
            if order_result["discrepancies"]:
                self.log_event(
                    LogLevel.WARNING,
                    f"Order discrepancies detected: {len(order_result['discrepancies'])} issues",
                    {"discrepancies": order_result["discrepancies"]}
                )
                logger.warning(f"Order discrepancies: {order_result['discrepancies']}")

            # Update orders in DB based on reconciliation
            for updated_order in order_result.get("updated_orders", []):
                db_order = db.execute(
                    select(Order)
                    .where(Order.client_order_id == updated_order.client_order_id)
                ).scalar_one_or_none()

                if db_order:
                    db_order.status = OrderStatus(updated_order.status.value)
                    db_order.filled_size = float(updated_order.filled_size) if updated_order.filled_size else 0.0
                    db_order.updated_at = datetime.now(timezone.utc)

            # Reconcile positions
            position_result = self.reconciler.reconcile_positions([], self.config.symbol)

            if position_result["discrepancies"]:
                self.log_event(
                    LogLevel.WARNING,
                    f"Position discrepancies detected: {len(position_result['discrepancies'])} issues",
                    {"discrepancies": position_result["discrepancies"]}
                )
                logger.warning(f"Position discrepancies: {position_result['discrepancies']}")

            db.commit()

            logger.info(f"Reconciliation completed for session {self.session_id}")
            self._last_reconcile_time = time.time()

        except Exception as e:
            logger.error(f"Failed to perform reconciliation: {e}", exc_info=True)
            db.rollback()
            raise

    def _update_open_orders_thread(self, executor: OrderExecutor, db: Session) -> None:
        """更新未完成订单状态（线程安全）"""
        open_orders = db.execute(
            select(Order)
            .where(Order.session_id == self.session_id)
            .where(Order.status.in_([OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]))
        ).scalars().all()

        for order in open_orders:
            try:
                executor.update_order_status(order)
            except Exception as e:
                logger.error(f"Failed to update order {order.id}: {e}", exc_info=True)

    def _update_session_stats_thread(self, monitor: PositionMonitor, db: Session) -> None:
        """更新会话统计（线程安全）"""
        session = db.get(TradingSession, self.session_id)
        if not session:
            return

        # Update total PnL
        session.total_pnl = monitor.get_total_pnl()

        # Count filled orders
        filled_count = db.execute(
            select(Order)
            .where(Order.session_id == self.session_id)
            .where(Order.status == OrderStatus.FILLED)
        ).scalars().all()
        session.total_trades = len(filled_count)

        db.commit()
