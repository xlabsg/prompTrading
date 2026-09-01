"""Test data helpers and fixtures."""

import secrets
from datetime import datetime, timedelta, timezone

from control_plane.enums import StrategyRole
from control_plane.models import Strategy, StrategyMember, User, UserSession


def create_test_user(db, email: str | None = None, name: str | None = None) -> User:
    """Create a test user in the database.

    Args:
        db: Database session
        email: User email (random if not provided)
        name: User name (random if not provided)

    Returns:
        Created User instance
    """
    random_suffix = secrets.token_hex(4)
    user = User(
        email=email or f"test_{random_suffix}@example.com",
        name=name or f"Test User {random_suffix}",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def create_test_session(db, user: User, expires_days: int = 14) -> UserSession:
    """Create a test session for a user.

    Args:
        db: Database session
        user: User to create session for
        expires_days: Days until session expires

    Returns:
        Created UserSession instance with token
    """
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
    session = UserSession(
        user_id=user.id,
        token=token,
        expires_at=expires_at,
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.flush()
    return session


def create_test_strategy(db, user: User, name: str | None = None) -> Strategy:
    """Create a test strategy owned by the user.

    Args:
        db: Database session
        user: User who will own the strategy
        name: Strategy name (random if not provided)

    Returns:
        Created Strategy instance
    """
    random_suffix = secrets.token_hex(4)
    strategy = Strategy(
        name=name or f"Test Strategy {random_suffix}",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(strategy)
    db.flush()

    # Add user as ADMIN
    member = StrategyMember(
        strategy_id=strategy.id,
        user_id=user.id,
        role=StrategyRole.ADMIN,
        created_at=datetime.now(timezone.utc),
    )
    db.add(member)
    db.flush()

    return strategy


def build_auth_cookies(session: UserSession) -> dict:
    """Build a cookies dict for making authenticated requests.

    Args:
        session: UserSession instance

    Returns:
        Dict with session cookie for TestClient
    """
    return {"asp_session": session.token}
