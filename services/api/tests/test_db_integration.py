import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import Base, User, Strategy, StrategyTemplate
from control_plane.enums import ChatStatus
from app.settings import settings


def test_api_sqlite_session_and_models():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "api_test.db")
        db_url = f"sqlite:///{db_path}"
        engine = create_db_engine(db_url)
        Base.metadata.create_all(engine)
        session_factory = create_session_factory(engine)

        # 1. Test user operations
        with session_scope(session_factory) as db:
            user = User(email="test@example.com", name="Test User")
            db.add(user)

        with session_scope(session_factory) as db:
            loaded = db.execute(select(User).where(User.email == "test@example.com")).scalar_one()
            assert loaded.email == "test@example.com"
            assert loaded.name == "Test User"

        # 2. Test strategy creation with JSON fields
        with session_scope(session_factory) as db:
            strategy = Strategy(
                name="SQLite Test Strategy",
                chat_status=ChatStatus.READY,
                chat_history=[
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "hi there"},
                ],
                chat_config={"symbol": "BTC-USDT-SWAP", "interval": "1h"},
            )
            db.add(strategy)
            db.flush()
            strategy_id = strategy.id

        with session_scope(session_factory) as db:
            saved_strat = db.get(Strategy, strategy_id)
            assert saved_strat is not None
            assert saved_strat.name == "SQLite Test Strategy"
            assert saved_strat.chat_history[1]["content"] == "hi there"
            assert saved_strat.chat_config["symbol"] == "BTC-USDT-SWAP"
