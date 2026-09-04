"""Unit tests for trading engine OrderExecutor."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from control_plane.enums import OrderSide, OrderStatus, OrderType, TradeStatus, TradingSessionStatus
from control_plane.models import Base, Order, TradingConfig, TradingSession, TradingTrade
from app.trading_engine.executor import OrderExecutor


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_order_executor_market_and_limit_orders(db_session):
    config = TradingConfig(
        id="test-config-1",
        strategy_id="strat-1",
        exchange="paper",
        symbol="BTC-USDT",
        max_position_pct=25.0,
        stop_loss_pct=5.0,
        require_stop_loss=True,
        dynamic_tpsl_enabled=False,
    )
    db_session.add(config)

    session = TradingSession(
        id="test-session-1",
        config_id=config.id,
        status=TradingSessionStatus.RUNNING,
    )
    db_session.add(session)
    db_session.commit()

    executor = OrderExecutor(config=config, session_id=session.id, db=db_session)

    # 1. Place Market Order
    market_order = executor.place_market_order(side=OrderSide.BUY, size=0.005)
    assert market_order is not None
    assert market_order.status == OrderStatus.OPEN
    assert market_order.stop_loss is not None
    assert market_order.symbol == "BTC-USDT"

    # Verify TradingTrade record created
    trades = db_session.query(TradingTrade).filter(TradingTrade.session_id == session.id).all()
    assert len(trades) == 1
    assert trades[0].symbol == "BTC-USDT"
    assert trades[0].status == TradeStatus.OPEN

    # 2. Place Limit Order
    limit_order = executor.place_limit_order(side=OrderSide.BUY, price=60000.0, size=0.005)
    assert limit_order is not None
    assert limit_order.order_type == OrderType.LIMIT
    assert limit_order.stop_loss == pytest.approx(57000.0)  # 60000 * 0.95


def test_order_executor_risk_rejection(db_session):
    config = TradingConfig(
        id="test-config-risk",
        strategy_id="strat-risk",
        exchange="paper",
        symbol="BTC-USDT",
        max_position_pct=1.0,  # 1% of 10,000 = $100 max position
        stop_loss_pct=5.0,
        require_stop_loss=True,
    )
    db_session.add(config)

    session = TradingSession(
        id="test-session-risk",
        config_id=config.id,
        status=TradingSessionStatus.RUNNING,
    )
    db_session.add(session)
    db_session.commit()

    executor = OrderExecutor(config=config, session_id=session.id, db=db_session)

    # 0.1 BTC at ~$80,000 = ~$8,000, which exceeds $100
    order = executor.place_market_order(side=OrderSide.BUY, size=0.1)
    assert order is None


def test_manager_reconcile_orders_handles_order_type_attribute(db_session):
    """Verify TradingSessionManager._reconcile properly accesses db_order.order_type without AttributeError."""
    from app.trading_engine.manager import TradingSessionManager

    config = TradingConfig(
        id="test-config-reconcile",
        strategy_id="strat-rec",
        exchange="paper",
        symbol="BTC-USDT",
        max_position_pct=25.0,
        stop_loss_pct=5.0,
    )
    db_session.add(config)

    session = TradingSession(
        id="test-session-rec",
        config_id=config.id,
        status=TradingSessionStatus.RUNNING,
    )
    db_session.add(session)

    # Insert an open order with order_type
    open_order = Order(
        id="test-ord-1",
        session_id=session.id,
        symbol="BTC-USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        client_order_id="client_test_rec_1",
        exchange_order_id="ex_test_rec_1",
        price=50000.0,
        size=0.1,
        filled_size=0.0,
        status=OrderStatus.OPEN,
    )
    db_session.add(open_order)
    db_session.commit()

    manager = TradingSessionManager(session=session, config=config, account=None, db=db_session)
    # This must succeed and not raise AttributeError: 'Order' object has no attribute 'type'
    manager._perform_reconciliation(db_session)

    # Check that the order is registered with manager's order manager
    sdk_order = manager.order_manager.get_order_by_client_id("client_test_rec_1")
    assert sdk_order is not None
    assert sdk_order.symbol == "BTC-USDT"
    assert sdk_order.order_id == "test-ord-1"

