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
from control_plane.models import Base, InviteCode
from app.routers import backtests, internal, jobs, markets, portfolio, sandbox, strategies, strategies_import, trading, trending, ws, templates, template_performance, template_backtests, templates_admin, admin_ops
from app.routers import strategy_accounts, strategy_members, strategy_workspace
from app.routers import auth as auth_router
from app.routers import billing as billing_router
from app.routers import repos as repos_router
from app.routers import github as github_router
from app.routers import search as search_router
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


def _dev_invite_seeding_enabled() -> bool:
    """本地开发种子数据开关，默认关闭。"""
    return os.getenv("SEED_DEV_INVITE_CODES", "").strip().lower() in {"1", "true", "yes"}


def _ensure_permanent_invite_codes(session_factory) -> list[str]:
    """确保固定的永久 invite codes 存在（无过期，可多次使用，仅供本地开发）

    这些是硬编码在公开源码里的已知码，任何人都能用它们在部署实例上注册，
    因此默认不创建。仅当显式设置 SEED_DEV_INVITE_CODES=true 时启用。
    """
    if not _dev_invite_seeding_enabled():
        return []
    permanent_codes = [
        "dev-unlimited",  # 开发环境无限使用
        "test-unlimited",  # 测试环境无限使用
        "demo-user",  # 演示用户
    ]
    created = []
    with session_factory() as db:
        for code in permanent_codes:
            existing = db.execute(
                select(InviteCode.id).where(InviteCode.code == code)
            ).scalar_one_or_none()
            if not existing:
                db.add(InviteCode(
                    code=code,
                    max_uses=999999,  # 接近无限次使用
                    expires_at=None,  # 永不过期
                ))
                created.append(code)
        if created:
            db.commit()
    return created


def _ensure_invite_codes(
    session_factory,
    target_count: int,
    expires_in_days: int = 30,
) -> list[str]:
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        valid_invites = db.execute(
            select(InviteCode).where(
                (InviteCode.expires_at.is_(None)) | (InviteCode.expires_at > now),
                InviteCode.used_count < InviteCode.max_uses,
            )
        ).scalars().all()
        needed = max(0, target_count - len(valid_invites))
        if needed == 0:
            return []
        expires_at = now + timedelta(days=expires_in_days)
        created_codes: list[str] = []
        for _ in range(needed):
            code = secrets.token_urlsafe(6)
            while db.execute(select(InviteCode.id).where(InviteCode.code == code)).scalar_one_or_none():
                code = secrets.token_urlsafe(6)
            db.add(InviteCode(code=code, max_uses=1, expires_at=expires_at))
            created_codes.append(code)
        db.commit()
        return created_codes


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.workspaces_dir, exist_ok=True)

    await _wait_for_db(settings.db_url, timeout_s=90.0)
    engine = create_db_engine(settings.db_url)
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)

    rds = await _wait_for_redis(settings.redis_url, timeout_s=60.0)

    # Save main event loop reference for thread-safe WebSocket broadcasting
    loop = asyncio.get_running_loop()
    app.state.event_loop = loop

    # Set the event loop for WebSocket manager
    from app.routers.ws import set_main_event_loop
    set_main_event_loop(loop)

    app.state.db_engine = engine
    app.state.session_factory = session_factory
    app.state.redis = rds

    # Ensure permanent invite codes (dev/test)
    permanent_created = _ensure_permanent_invite_codes(session_factory)
    if permanent_created:
        logger.warning(f"Created permanent invite codes: {', '.join(permanent_created)}")

    # Ensure regular invite codes
    created_invites = _ensure_invite_codes(session_factory, target_count=10, expires_in_days=30)
    if created_invites:
        logger.warning(f"Created {len(created_invites)} new regular invite codes")

    # 仅在本地开发时把邀请码打印到日志；生产环境只记录数量，
    # 避免有效邀请码泄露到日志聚合系统里。
    with session_factory() as db:
        now = datetime.now(timezone.utc)

        # Get permanent codes (no expiration)
        permanent_codes = db.execute(
            select(InviteCode.code).where(
                InviteCode.expires_at.is_(None),
                InviteCode.used_count < InviteCode.max_uses,
            )
        ).scalars().all()

        # Get regular codes (with expiration)
        regular_codes = db.execute(
            select(InviteCode.code).where(
                InviteCode.expires_at.is_not(None),
                InviteCode.expires_at > now,
                InviteCode.used_count < InviteCode.max_uses,
            )
        ).scalars().all()

        logger.info(
            "invite codes available: %d permanent, %d regular",
            len(permanent_codes),
            len(regular_codes),
        )

        if (permanent_codes or regular_codes) and _dev_invite_seeding_enabled():
            logger.warning("=" * 80)
            logger.warning("AVAILABLE INVITE CODES:")
            if permanent_codes:
                logger.warning("")
                logger.warning("  Permanent (unlimited use):")
                for code in permanent_codes:
                    logger.warning(f"    • {code}")
            if regular_codes:
                logger.warning("")
                logger.warning("  Regular (single use, expires in 30 days):")
                for code in regular_codes:
                    logger.warning(f"    • {code}")
            logger.warning("=" * 80)
    try:
        yield
    finally:
        rds.close()
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
app.include_router(sandbox.router, prefix="/api", tags=["sandbox"])
app.include_router(ws.router, prefix="/ws", tags=["ws"])
app.include_router(internal.router, prefix="/internal", tags=["internal"])
app.include_router(auth_router.router, prefix="/api", tags=["auth"])
app.include_router(billing_router.router, prefix="/api", tags=["billing"])
app.include_router(repos_router.router, prefix="/api", tags=["repos"])
app.include_router(search_router.router, prefix="/api", tags=["search"])
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
def healthz() -> dict:
    return {"ok": True}
