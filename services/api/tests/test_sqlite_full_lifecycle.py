import os
import tempfile
import threading
import time
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, text

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import (
    Base,
    User,
    UserSession,
    OAuthAccount,
    Strategy,
    StrategyVersion,
    Job,
    BacktestRun,
    TradingConfig,
    TradingSession,
    StrategyMember,
    StrategyExchangeAccount,
    StrategySignal,
    Order,
    StrategyTemplate,
    Repository,
)
from control_plane.enums import (
    ChatStatus,
    JobType,
    JobStatus,
    BacktestStatus,
    TradingSessionStatus,
    OrderSide,
    OrderType,
    OrderStatus,
    StrategyRole,
    LogLevel,
)


def test_full_sqlite_domain_lifecycle():
    """Verify all domain models, foreign keys, and JSON columns against SQLite."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "lifecycle.db")
        db_url = f"sqlite:///{db_path}"
        engine = create_db_engine(db_url)
        session_factory = create_session_factory(engine)

        # 1. Verify schema creation
        Base.metadata.create_all(engine)

        with session_scope(session_factory) as db:
            # 2. User & Session
            user = User(id="usr_test_1", email="trader@test.com", name="Trader Bob")
            db.add(user)
            db.flush()

            session = UserSession(
                user_id=user.id,
                token="token_abc_123",
                expires_at=datetime.now(timezone.utc) + timedelta(days=14),
            )
            oauth = OAuthAccount(user_id=user.id, provider="github", provider_user_id="gh_123")
            db.add_all([session, oauth])

            # 3. Strategy with complex JSON
            strategy = Strategy(
                name="BTC Momentum Alpha",
                chat_status=ChatStatus.DONE,
                chat_history=[
                    {"role": "user", "content": "Make a momentum bot for BTC"},
                    {"role": "assistant", "content": "Here is the strategy."},
                ],
                chat_config={
                    "exchange": "okx",
                    "symbol": "BTC-USDT-SWAP",
                    "leverage": 5,
                    "risk_limit_pct": 2.5,
                },
            )
            db.add(strategy)
            db.flush()

            # 4. Strategy Version & Member
            version = StrategyVersion(
                strategy_id=strategy.id,
                version=1,
                workspace_path="versions/v1/",
                prompt="Initial prompt",
                llm_meta={"model": "gpt-4", "tokens": 1250},
            )
            member = StrategyMember(
                strategy_id=strategy.id,
                user_id=user.id,
                role=StrategyRole.ADMIN,
            )
            db.add_all([version, member])

            # 5. Job & Backtest Run
            job = Job(
                type="backtest",
                status="succeeded",
                payload={"strategy_id": strategy.id, "version_id": version.id, "days": 30},
            )
            db.add(job)
            db.flush()

            backtest = BacktestRun(
                strategy_id=strategy.id,
                strategy_version_id=version.id,
                status=BacktestStatus.SUCCEEDED,
                run_path="runs/test_run_1/",
                params={"interval": "1h", "stop_loss": 0.02},
                metrics={
                    "total_return": 18.5,
                    "sharpe_ratio": 2.1,
                    "max_drawdown": 4.2,
                },
                result_summary={"trades_count": 45, "win_rate": 0.62},
            )
            db.add(backtest)

            # 6. Trading Config & Live Session
            trading_cfg = TradingConfig(
                strategy_id=strategy.id,
                exchange="okx",
                symbol="BTC-USDT-SWAP",
                symbols=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
                intervals=["1h", "4h"],
                max_position_pct=10.0,
                stop_loss_pct=1.5,
            )
            db.add(trading_cfg)
            db.flush()

            trading_sess = TradingSession(
                config_id=trading_cfg.id,
                status=TradingSessionStatus.RUNNING,
            )
            db.add(trading_sess)
            db.flush()

            # 7. Signal & Trade Order
            signal = StrategySignal(
                strategy_id=strategy.id,
                session_id=trading_sess.id,
                symbol="BTC-USDT-SWAP",
                side="buy",
                price=50000.0,
                indicators={"rsi": 28.5, "macd": -12.4},
                position={"size": 0.5, "entry_price": 49800.0},
            )
            order = Order(
                session_id=trading_sess.id,
                client_order_id="ord_12345",
                symbol="BTC-USDT-SWAP",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                status=OrderStatus.FILLED,
                price=50000.0,
                size=0.5,
                filled_size=0.5,
                avg_fill_price=50000.0,
            )
            db.add_all([signal, order])

        # Verify all committed objects can be retrieved and navigated cleanly
        with session_scope(session_factory) as db:
            s = db.execute(select(Strategy).where(Strategy.name == "BTC Momentum Alpha")).scalar_one()
            assert len(s.versions) == 1
            assert s.versions[0].llm_meta["tokens"] == 1250
            assert len(s.backtests) == 1
            assert s.backtests[0].metrics["sharpe_ratio"] == 2.1
            assert s.trading_config.symbols == ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
            assert len(s.members) == 1
            assert s.members[0].user.email == "trader@test.com"


def test_sqlite_concurrent_read_write():
    """Verify concurrent reads and writes don't lock under SQLite WAL mode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "concurrent.db")
        db_url = f"sqlite:///{db_path}"
        engine = create_db_engine(db_url)
        session_factory = create_session_factory(engine)
        Base.metadata.create_all(engine)

        errors = []

        def writer_task(thread_id: int):
            try:
                for i in range(20):
                    with session_scope(session_factory) as db:
                        strat = Strategy(
                            name=f"Thread-{thread_id}-Strat-{i}",
                            chat_status=ChatStatus.DONE,
                            chat_history=[{"step": i}],
                            chat_config={"risk": i * 0.1},
                        )
                        db.add(strat)
                    time.sleep(0.005)
            except Exception as e:
                errors.append(e)

        def reader_task():
            try:
                for _ in range(30):
                    with session_scope(session_factory) as db:
                        db.execute(select(Strategy)).scalars().all()
                    time.sleep(0.003)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer_task, args=(1,)),
            threading.Thread(target=writer_task, args=(2,)),
            threading.Thread(target=writer_task, args=(3,)),
            threading.Thread(target=reader_task),
            threading.Thread(target=reader_task),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent errors occurred: {errors}"

        with session_scope(session_factory) as db:
            total = db.query(Strategy).count()
            assert total == 60  # 3 writers * 20 items
