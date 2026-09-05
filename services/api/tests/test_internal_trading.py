from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from control_plane.models import (
    Base,
    Strategy,
    TradingConfig,
    TradingSession,
    Position,
)
from control_plane.enums import TradingSessionStatus, PositionStatus
from app.main import app
from app.deps import get_db
from live_trading_sdk.live_container_runner import ContainerBroker


def test_internal_trading_flow():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    with TestingSessionLocal() as db:
        strat = Strategy(id="strat-test-1", name="Test Strat")
        db.add(strat)

        config = TradingConfig(
            id="cfg-test-1",
            strategy_id=strat.id,
            exchange="paper",
            symbol="BTC-USDT",
            symbols=["BTC-USDT"],
            intervals=["1m"],
            max_position_pct=25.0,
            stop_loss_pct=5.0,
            is_active=True,
        )
        db.add(config)

        session = TradingSession(
            id="sess-test-1",
            config_id=config.id,
            status=TradingSessionStatus.RUNNING,
        )
        db.add(session)

        pos = Position(
            session_id=session.id,
            symbol="BTC-USDT",
            status=PositionStatus.OPEN,
            size=0.05,
            side="long",
            entry_price=65000.0,
            current_price=65000.0,
        )
        db.add(pos)
        db.commit()

    try:
        # 1. Test get_session_state
        resp = client.get("/api/internal/trading/sess-test-1/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess-test-1"
        assert data["position_size"] == 0.05
        assert "RUNNING" in data["status"]

        # 2. Test heartbeat
        resp = client.post("/api/internal/trading/sess-test-1/heartbeat", json={"timestamp": 1234567890})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # 3. Test submit_trading_intent - market_order
        resp = client.post(
            "/api/internal/trading/sess-test-1/intent",
            json={
                "action": "market_order",
                "side": "buy",
                "size": 0.01,
                "symbol": "BTC-USDT",
                "reason": "unit test market order",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["action"] == "market_order"

        # 4. Test submit_trading_intent - set_target_allocation
        resp = client.post(
            "/api/internal/trading/sess-test-1/intent",
            json={
                "action": "set_target_allocation",
                "target": 0.2,
                "symbol": "BTC-USDT",
                "reason": "unit test allocation",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["action"] == "set_target_allocation"

        # 5. Test rejection when session is STOPPED
        with TestingSessionLocal() as db:
            s = db.get(TradingSession, "sess-test-1")
            s.status = TradingSessionStatus.STOPPED
            db.commit()

        resp = client.post(
            "/api/internal/trading/sess-test-1/intent",
            json={
                "action": "market_order",
                "side": "buy",
                "size": 0.01,
                "symbol": "BTC-USDT",
            },
        )
        assert resp.status_code == 400
        assert "session_not_running" in resp.json()["detail"]

    finally:
        app.dependency_overrides.clear()


def test_container_broker_dispatch():
    """Verify ContainerBroker properly submits intents to mock endpoint."""
    from unittest.mock import patch, MagicMock

    broker = ContainerBroker(
        api_base_url="http://mock-api:8000",
        session_id="sess-broker-1",
        default_symbol="ETH-USDT",
    )

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_post.return_value = mock_resp

        # Test set_target_allocation
        broker.set_target_allocation(0.5, reason="test signal")
        mock_post.assert_called_once()
        called_args = mock_post.call_args
        called_url = called_args[0][0]
        called_kwargs = called_args[1]
        assert "http://mock-api:8000/api/internal/trading/sess-broker-1/intent" in called_url
        assert called_kwargs["json"]["action"] == "set_target_allocation"
        assert called_kwargs["json"]["target"] == 0.5
        assert called_kwargs["json"]["symbol"] == "ETH-USDT"

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_post.return_value = mock_resp

        # Test market_order
        broker.market_order("buy", 0.1, reason="test buy")
        mock_post.assert_called_once()
        called_args = mock_post.call_args
        called_kwargs = called_args[1]
        assert called_kwargs["json"]["action"] == "market_order"
        assert called_kwargs["json"]["side"] == "buy"
        assert called_kwargs["json"]["size"] == 0.1
