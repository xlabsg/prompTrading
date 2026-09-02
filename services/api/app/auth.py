from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.enums import StrategyRole
from control_plane.models import StrategyMember, User, UserSession
from app.settings import settings

SESSION_COOKIE_NAME = "asp_session"


DEV_USER_ID = "usr_local_dev"
DEV_USER_EMAIL = "dev@local.test"


def _get_or_create_dev_user(db: Session) -> User:
    user = db.get(User, DEV_USER_ID)
    if user is None:
        user = db.execute(select(User).where(User.email == DEV_USER_EMAIL)).scalar_one_or_none()
    if user is None:
        user = User(
            id=DEV_USER_ID,
            email=DEV_USER_EMAIL,
            name="Local Dev",
            avatar_url="https://api.dicebear.com/7.x/bottts/svg?seed=localdev",
            is_active=True,
        )
        db.add(user)
        db.flush()
    return user


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.auth_session_days)
    session = UserSession(user_id=user.id, token=token, expires_at=expires_at)
    db.add(session)
    user.last_login_at = datetime.now(timezone.utc)
    return token


def get_current_user_optional(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        if settings.dev_skip_auth:
            return _get_or_create_dev_user(db)
        return None
    session = db.execute(
        select(UserSession)
        .where(UserSession.token == token)
        .where(UserSession.expires_at > datetime.now(timezone.utc))
    ).scalar_one_or_none()
    if session is None:
        if settings.dev_skip_auth:
            return _get_or_create_dev_user(db)
        return None
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        if settings.dev_skip_auth:
            return _get_or_create_dev_user(db)
        return None
    return user


def get_current_user(request: Request, db: Session) -> User:
    user = get_current_user_optional(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return user


def require_strategy_member(
    request: Request,
    db: Session,
    strategy_id: str,
    allowed_roles: list[StrategyRole] | None = None,
) -> StrategyMember:
    user = get_current_user(request, db)
    member = db.execute(
        select(StrategyMember)
        .where(StrategyMember.strategy_id == strategy_id)
        .where(StrategyMember.user_id == user.id)
    ).scalar_one_or_none()
    if member is None:
        if settings.dev_skip_auth:
            member = StrategyMember(
                strategy_id=strategy_id,
                user_id=user.id,
                role=StrategyRole.OWNER,
            )
            db.add(member)
            db.flush()
            return member
        raise HTTPException(status_code=403, detail="not_authorized")
    if allowed_roles and member.role not in allowed_roles:
        if settings.dev_skip_auth:
            return member
        raise HTTPException(status_code=403, detail="not_authorized")
    return member


def user_has_active_subscription(user: User) -> bool:
    # In development, skip subscription check (allow all users)
    if settings.dev_skip_subscription_check:
        return True

    status = (user.subscription_status or "").lower()
    if status in {"active", "trialing"}:
        if user.subscription_current_period_end:
            return user.subscription_current_period_end > datetime.now(timezone.utc)
        return True
    return False
