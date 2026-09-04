from __future__ import annotations

import asyncio
import logging
import logging.config
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from control_plane.db import create_db_engine, create_session_factory
from control_plane.models import Base
from app.routers import backtests, jobs, markets, portfolio, strategies, strategies_import, trading, trending, ws, templates, template_performance, template_backtests, templates_admin, admin_ops
from app.routers import strategy_accounts, strategy_members, strategy_workspace
from app.routers import auth as auth_router
from app.routers import billing as billing_router
from app.routers import repos as repos_router
from app.routers import github as github_router
from app.routers import github_webhooks as github_webhooks_router
from app.settings import settings

logger = logging.getLogger(__name__)


def _configure_logging(log_dir: str, service_name: str) -> None:
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{service_name}.log")
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            }
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "filename": log_path,
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "root": {"level": "INFO", "handlers": ["stdout", "file"]},
    }
    logging.config.dictConfig(log_config)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True


_configure_logging(settings.log_dir, "api")


async def _wait_for_db(db_url: str, timeout_s: float = 60.0) -> None:
    engine = create_db_engine(db_url)
    deadline = time.monotonic() + timeout_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as e:
            last_err = e
            await asyncio.sleep(1.0)
    raise RuntimeError("db_not_ready") from last_err


async def _wait_for_redis(redis_url: str, timeout_s: float = 30.0) -> redis.Redis:
    rds = redis.Redis.from_url(redis_url, decode_responses=True)
    deadline = time.monotonic() + timeout_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            rds.ping()
            return rds
        except Exception as e:
            last_err = e
            await asyncio.sleep(0.5)
    raise RuntimeError("redis_not_ready") from last_err


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.workspaces_dir, exist_ok=True)

    await _wait_for_db(settings.db_url, timeout_s=90.0)
    engine = create_db_engine(settings.db_url)
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)

    rds = None
    if settings.redis_url:
        try:
            rds = await _wait_for_redis(settings.redis_url, timeout_s=10.0)
        except Exception as e:
            logger.warning(f"Redis not reachable ({e}), proceeding with zero-redis file queue")

    from control_plane.queue import get_file_queue
    app.state.file_queue = get_file_queue(settings.workspaces_dir)

    # Save main event loop reference for thread-safe WebSocket broadcasting
    loop = asyncio.get_running_loop()
    app.state.event_loop = loop

    # Set the event loop for WebSocket manager
    from app.routers.ws import set_main_event_loop
    set_main_event_loop(loop)

    app.state.db_engine = engine
    app.state.session_factory = session_factory
    app.state.redis = rds
    try:
        yield
    finally:
        if rds is not None:
            try:
                rds.close()
            except Exception:
                pass
        engine.dispose()


app = FastAPI(title="PrompTrading API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_base_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(strategies.router, prefix="/api", tags=["strategies"])
app.include_router(strategy_members.router, prefix="/api", tags=["strategies"])
app.include_router(strategy_accounts.router, prefix="/api", tags=["strategies"])
app.include_router(strategy_workspace.router, prefix="/api", tags=["strategies"])
app.include_router(strategies_import.router, prefix="/api", tags=["import"])
app.include_router(backtests.router, prefix="/api", tags=["backtests"])
app.include_router(trading.router, prefix="/api", tags=["trading"])
app.include_router(portfolio.router, tags=["portfolio"])
app.include_router(jobs.router, prefix="/api", tags=["jobs"])
app.include_router(ws.router, prefix="/ws", tags=["ws"])
app.include_router(auth_router.router, prefix="/api", tags=["auth"])
app.include_router(billing_router.router, prefix="/api", tags=["billing"])
app.include_router(repos_router.router, prefix="/api", tags=["repos"])
app.include_router(github_router.router, prefix="/api", tags=["github"])
app.include_router(github_webhooks_router.router, tags=["webhooks"])
app.include_router(markets.router, prefix="/api", tags=["markets"])
app.include_router(trending.router, tags=["trending"])
app.include_router(templates.router, prefix="/api", tags=["templates"])
app.include_router(templates_admin.router, prefix="/api", tags=["templates-admin"])
app.include_router(template_performance.router, prefix="/api", tags=["template-performance"])
app.include_router(template_backtests.router, prefix="/api", tags=["template-backtests"])
app.include_router(admin_ops.router, prefix="/api", tags=["admin-ops"])


@app.get("/healthz")
@app.get("/health")
def healthz() -> dict:
    return {"ok": True, "status": "healthy"}
