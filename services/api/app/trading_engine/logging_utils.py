"""Utilities for recording trading logs and broadcasting updates."""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from control_plane.enums import LogLevel
from control_plane.models import TradingLog
from app.routers.ws import manager as ws_manager

logger = logging.getLogger(__name__)


def log_trading_event(
    db: Session,
    *,
    strategy_id: str,
    session_id: str,
    level: LogLevel,
    message: str,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[TradingLog]:
    """Persist and broadcast a trading log entry.

    Returns the created `TradingLog` or ``None`` if writing fails.
    """

    try:
        log_entry = TradingLog(
            session_id=session_id,
            level=level,
            message=message,
            log_metadata=metadata or {},
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)

        log_level = getattr(logging, level.value.upper(), logging.INFO)
        logger.log(log_level, f"[Session {session_id[:8]}] {message}", extra={"metadata": metadata})

        try:
            ws_manager.broadcast_from_thread(
                strategy_id,
                {
                    "type": "log_new",
                    "data": {
                        "id": log_entry.id,
                        "session_id": session_id,
                        "level": level.value,
                        "message": message,
                        "log_metadata": metadata,
                        "created_at": log_entry.created_at.isoformat() if log_entry.created_at else None,
                    },
                },
            )
        except Exception as exc:  # pragma: no cover - best effort broadcast
            logger.debug("Failed to broadcast trading log: %s", exc)

        return log_entry

    except Exception as exc:
        logger.error("Failed to persist trading log: %s", exc, exc_info=True)
        db.rollback()
        return None
