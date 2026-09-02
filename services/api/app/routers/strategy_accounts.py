"""Exchange accounts, signals, and trades for a strategy."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.enums import StrategyRole
from control_plane.models import (
    StrategyExchangeAccount,
    StrategySignal,
    TradingSession,
    TradingTrade,
)

from app.auth import require_strategy_member
from app.crypto import encrypt_credential
from app.deps import get_db
from app.schemas import (
    ExchangeAccountCreateRequest,
    ExchangeAccountResponse,
    ExchangeAccountUpdateRequest,
    SignalResponse,
    TradeResponse,
)

router = APIRouter()


@router.get("/strategies/{strategy_id}/exchange_accounts", response_model=list[ExchangeAccountResponse])
def list_exchange_accounts(
    strategy_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> list[ExchangeAccountResponse]:
    require_strategy_member(request, db, strategy_id)
    accounts = (
        db.execute(
            select(StrategyExchangeAccount)
            .where(StrategyExchangeAccount.strategy_id == strategy_id)
            .order_by(StrategyExchangeAccount.created_at.desc())
        )
        .scalars()
        .all()
    )
    return accounts


@router.post("/strategies/{strategy_id}/exchange_accounts", response_model=ExchangeAccountResponse)
def create_exchange_account(
    strategy_id: str,
    req: ExchangeAccountCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ExchangeAccountResponse:
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN])
    exchange = (req.exchange or "").strip().lower()
    if exchange not in ("okx", "binance"):
        raise HTTPException(status_code=400, detail="unsupported_exchange")
    account = StrategyExchangeAccount(
        strategy_id=strategy_id,
        name=req.name.strip(),
        exchange=exchange,
        api_key_encrypted=req.api_key.strip(),
        api_secret_encrypted=encrypt_credential(req.api_secret.strip()),
        api_passphrase_encrypted=encrypt_credential(req.api_passphrase.strip()) if req.api_passphrase else None,
        is_connected=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.patch("/strategies/{strategy_id}/exchange_accounts/{account_id}", response_model=ExchangeAccountResponse)
def update_exchange_account(
    strategy_id: str,
    account_id: str,
    req: ExchangeAccountUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ExchangeAccountResponse:
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN])
    account = db.get(StrategyExchangeAccount, account_id)
    if account is None or account.strategy_id != strategy_id:
        raise HTTPException(status_code=404, detail="account_not_found")

    if req.name is not None:
        account.name = req.name.strip()
    if req.api_key is not None:
        account.api_key_encrypted = req.api_key.strip()
    if req.api_secret is not None:
        account.api_secret_encrypted = encrypt_credential(req.api_secret.strip())
    if req.api_passphrase is not None:
        account.api_passphrase_encrypted = encrypt_credential(req.api_passphrase.strip()) if req.api_passphrase else None
    if req.is_connected is not None:
        account.is_connected = req.is_connected

    account.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/strategies/{strategy_id}/exchange_accounts/{account_id}")
def delete_exchange_account(
    strategy_id: str,
    account_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN])
    account = db.get(StrategyExchangeAccount, account_id)
    if account is None or account.strategy_id != strategy_id:
        raise HTTPException(status_code=404, detail="account_not_found")
    db.delete(account)
    db.commit()
    return {"ok": True}


@router.get("/strategies/{strategy_id}/signals", response_model=list[SignalResponse])
def list_signals(
    strategy_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> list[SignalResponse]:
    require_strategy_member(request, db, strategy_id)
    rows = (
        db.execute(
            select(StrategySignal)
            .where(StrategySignal.strategy_id == strategy_id)
            .order_by(StrategySignal.created_at.desc())
        )
        .scalars()
        .all()
    )
    return rows


@router.get("/strategies/{strategy_id}/trades", response_model=list[TradeResponse])
def list_trades(
    strategy_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> list[TradeResponse]:
    require_strategy_member(request, db, strategy_id)
    rows = (
        db.execute(
            select(TradingTrade)
            .join(TradingSession, TradingSession.id == TradingTrade.session_id)
            .where(TradingSession.strategy_id == strategy_id)
            .order_by(TradingTrade.created_at.desc())
        )
        .scalars()
        .all()
    )
    return rows
