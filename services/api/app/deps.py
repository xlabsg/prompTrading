from __future__ import annotations

from collections.abc import Generator

import redis
from fastapi import Request
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def get_engine(request: Request) -> Engine:
    return request.app.state.db_engine


def get_session_factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.session_factory


def get_db(request: Request) -> Generator[Session, None, None]:
    session_factory = get_session_factory(request)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def get_redis(request: Request) -> redis.Redis:
    return request.app.state.redis

