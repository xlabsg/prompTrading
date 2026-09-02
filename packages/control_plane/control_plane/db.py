import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def create_db_engine(db_url: str) -> Engine:
    if db_url.startswith("sqlite"):
        url = make_url(db_url)
        if url.database and url.database != ":memory:":
            db_dir = os.path.dirname(os.path.abspath(url.database))
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

        is_memory = not url.database or url.database == ":memory:" or "mode=memory" in db_url
        engine_kwargs = {
            "connect_args": {"check_same_thread": False, "timeout": 30.0},
            "pool_pre_ping": True,
        }
        if is_memory:
            engine_kwargs["poolclass"] = StaticPool

        engine = create_engine(db_url, **engine_kwargs)

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA synchronous=NORMAL")
            finally:
                cursor.close()

        return engine

    return create_engine(db_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


