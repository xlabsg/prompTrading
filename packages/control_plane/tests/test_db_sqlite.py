import os
import tempfile
import pytest
from sqlalchemy import text, select

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import Base, Strategy, StrategyVersion, Job, StrategyTemplate, User
from control_plane.enums import JobType, JobStatus, ChatStatus


def test_sqlite_engine_wal_and_pragmas():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "subdir", "test.db")
        db_url = f"sqlite:///{db_path}"
        engine = create_db_engine(db_url)

        # Directory was auto-created
        assert os.path.exists(os.path.dirname(db_path))

        with engine.connect() as conn:
            journal_mode = conn.execute(text("PRAGMA journal_mode")).scalar()
            assert journal_mode.lower() == "wal"

            foreign_keys = conn.execute(text("PRAGMA foreign_keys")).scalar()
            assert foreign_keys == 1

            busy_timeout = conn.execute(text("PRAGMA busy_timeout")).scalar()
            assert busy_timeout >= 30000


def test_sqlite_schema_creation_and_json_fields():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db_url = f"sqlite:///{db_path}"
        engine = create_db_engine(db_url)
        session_factory = create_session_factory(engine)

        # Create all tables
        Base.metadata.create_all(engine)

        with session_scope(session_factory) as session:
            strat = Strategy(
                name="Test Strategy",
                chat_status=ChatStatus.DONE,
                chat_history=[
                    {"role": "user", "content": "Create a momentum strategy"},
                    {"role": "assistant", "content": "Sure, here it is"},
                ],
                chat_config={"symbol": "BTC-USDT-SWAP", "risk": 0.02},
            )
            session.add(strat)
            session.flush()
            strat_id = strat.id

        # Query back
        with session_scope(session_factory) as session:
            loaded = session.execute(select(Strategy).where(Strategy.id == strat_id)).scalar_one()
            assert loaded.name == "Test Strategy"
            assert isinstance(loaded.chat_history, list)
            assert len(loaded.chat_history) == 2
            assert loaded.chat_history[0]["role"] == "user"
            assert loaded.chat_config["symbol"] == "BTC-USDT-SWAP"


def test_sqlite_template_model_and_json_fields():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db_url = f"sqlite:///{db_path}"
        engine = create_db_engine(db_url)
        session_factory = create_session_factory(engine)

        Base.metadata.create_all(engine)

        with session_scope(session_factory) as session:
            tmpl = StrategyTemplate(
                id="tmpl-test",
                name="test_template",
                description="test description",
                template_type="builtin",
                prompt="test prompt",
                config_snapshot={"live_bar_interval": "1h", "pivot_period": 10},
                code_snapshot={"module": "test.module", "entrypoint": "main"},
                tags=["divergence", "rsi"],
                supported_exchanges=["okx", "binance"],
                supported_symbols=["BTC-USDT-SWAP"],
            )
            session.add(tmpl)

        with session_scope(session_factory) as session:
            loaded = session.execute(select(StrategyTemplate).where(StrategyTemplate.id == "tmpl-test")).scalar_one()
            assert loaded.name == "test_template"
            assert loaded.config_snapshot["live_bar_interval"] == "1h"
            assert loaded.tags == ["divergence", "rsi"]
            assert loaded.supported_exchanges == ["okx", "binance"]
