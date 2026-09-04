from __future__ import annotations

import logging
from typing import Optional, Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.models import (
    TradingSession,
    TradingConfig,
    StrategyExchangeAccount,
    Position,
)
from control_plane.enums import TradingSessionStatus, PositionStatus
from app.deps import get_db
from app.settings import settings
from app.crypto import decrypt_credential
from app.trading_engine.executor import OrderExecutor
from app.trading_engine.live_broker import LiveBroker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/trading", tags=["internal_trading"])


class TradingIntentRequest(BaseModel):
    action: str = Field(..., description="'set_target_allocation' or 'market_order'")
    target: Optional[float] = None
    side: Optional[str] = None
    size: Optional[float] = None
    symbol: str
    reason: Optional[str] = ""


class HeartbeatRequest(BaseModel):
    timestamp: Optional[int] = None


def create_exchange_client(config: TradingConfig, account: Optional[StrategyExchangeAccount]):
    exchange_name = (getattr(account, "exchange", "") or (config.exchange if config else "okx") or "okx").lower()
    if exchange_name == "paper" or account is None or not getattr(account, "api_secret_encrypted", None):
        from app.trading_engine.paper_client import PaperExchangeClient
        return PaperExchangeClient()

    api_key = (account.api_key_encrypted or "").strip()
    secret = decrypt_credential(account.api_secret_encrypted).strip()

    if exchange_name == "binance":
        from risk_engine import BinanceAdapter, BinanceClient
        testnet = getattr(settings, "binance_testnet", False)
        binance_client = BinanceClient(
            api_key=api_key,
            secret_key=secret,
            testnet=testnet,
        )
        return BinanceAdapter(binance_client)

    from okx_sdk import OKXClient
    passphrase = decrypt_credential(account.api_passphrase_encrypted or "").strip()
    return OKXClient(
        api_key=api_key,
        secret_key=secret,
        passphrase=passphrase,
        simulated=settings.okx_simulated_trading,
    )


@router.get("/{session_id}/state")
def get_session_state(
    session_id: str,
    symbol: Optional[str] = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Provide current position and status for the container broker."""
    session = db.get(TradingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")

    sym = symbol or (session.config.symbol if session.config else "")
    pos = db.execute(
        select(Position)
        .where(Position.session_id == session_id)
        .where(Position.symbol == sym)
        .where(Position.status == PositionStatus.OPEN)
    ).scalar_one_or_none()

    position_size = float(pos.size) if pos and pos.size is not None else 0.0

    return {
        "session_id": session.id,
        "status": str(session.status),
        "symbol": sym,
        "position_size": position_size,
    }


@router.post("/{session_id}/intent")
def submit_trading_intent(
    session_id: str,
    intent: TradingIntentRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Receive trading intent from container sandbox, apply 9 risk checks, and execute order."""
    session = db.get(TradingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")

    if session.status not in (TradingSessionStatus.RUNNING, TradingSessionStatus.STARTING):
        raise HTTPException(status_code=400, detail=f"session_not_running:{session.status}")

    config = session.config
    if config is None:
        raise HTTPException(status_code=400, detail="session_missing_config")

    account = session.exchange_account
    okx_client = create_exchange_client(config, account)

    broker = LiveBroker(
        strategy_id=config.strategy_id,
        session_id=session.id,
        config=config,
        okx_client=okx_client,
    )

    executor = OrderExecutor(config, session.id, db, account)
    broker.attach(executor, db)
    try:
        if intent.action == "set_target_allocation":
            if intent.target is None:
                raise HTTPException(status_code=400, detail="missing_target_allocation")
            broker.set_target_allocation(
                target=intent.target,
                reason=intent.reason or "container_target_allocation",
                symbol=intent.symbol,
            )
            return {"status": "ok", "action": "set_target_allocation", "target": intent.target}
        elif intent.action == "market_order":
            if not intent.side or intent.size is None:
                raise HTTPException(status_code=400, detail="missing_side_or_size")
            broker.market_order(
                side=intent.side,
                size=intent.size,
                reason=intent.reason or "container_market_order",
                symbol=intent.symbol,
            )
            return {"status": "ok", "action": "market_order", "side": intent.side, "size": intent.size}
        else:
            raise HTTPException(status_code=400, detail=f"unsupported_action:{intent.action}")
    finally:
        broker.detach()


@router.post("/{session_id}/heartbeat")
def record_heartbeat(
    session_id: str,
    heartbeat: HeartbeatRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record heartbeat from running strategy container."""
    session = db.get(TradingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")

    now = datetime.now(timezone.utc)
    session.last_heartbeat_at = now
    db.flush()
    return {"status": "ok", "last_heartbeat_at": now.isoformat()}
