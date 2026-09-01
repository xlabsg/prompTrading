from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.enums import LogLevel, TradingSessionStatus, StrategyRole
from control_plane.models import Order, Position, Strategy, StrategyExchangeAccount, TradingConfig, TradingLog, TradingSession
from app.auth import get_current_user, require_strategy_member, user_has_active_subscription
from app.deps import get_db
from app.settings import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _clean(value: Optional[str]) -> str:
    return value.strip() if value else ""


def _cred_debug(name: str, value: str) -> dict[str, object]:
    return {
        "field": name,
        "length": len(value or ""),
        "preview": (value[:4] + "***") if value else "",
    }


def _normalize_list(values: Optional[list[str]]) -> list[str]:
    return [v.strip() for v in (values or []) if v and v.strip()]


def _require_session_access(
    request: Request,
    db: Session,
    session_id: str,
    allowed_roles: list[StrategyRole] | None = None,
) -> TradingSession:
    session = db.get(TradingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    config = db.get(TradingConfig, session.config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="config_not_found")
    require_strategy_member(request, db, config.strategy_id, allowed_roles)
    return session


# ============== Schemas ==============

class TradingConfigCreate(BaseModel):
    exchange: str = Field(..., description="Exchange name: okx, binance")
    symbol: Optional[str] = Field(default=None, description="Trading pair: BTC-USDT")
    symbols: Optional[list[str]] = Field(default=None, description="Trading pairs")
    intervals: Optional[list[str]] = Field(default=None, description="Candle intervals")
    account_id: str = Field(..., description="Strategy exchange account id")
    max_position_pct: float = Field(default=10.0, ge=1, le=100)
    stop_loss_pct: float = Field(default=5.0, ge=0.5, le=50)

    # Risk control
    leverage: int = Field(default=1, ge=1, le=125, description="Leverage multiplier")
    max_leverage: int = Field(default=10, ge=1, le=125, description="Maximum allowed leverage")
    max_daily_loss_pct: Optional[float] = Field(default=None, ge=0, le=50, description="Maximum daily loss percentage")
    max_drawdown_pct: Optional[float] = Field(default=None, ge=0, le=50, description="Maximum drawdown percentage")
    require_stop_loss: bool = Field(default=True, description="Require stop loss for all orders")

    # Trailing stop
    trailing_stop_enabled: bool = Field(default=False, description="Enable trailing stop loss")
    trailing_activation_pct: float = Field(default=0.005, ge=0, le=1, description="Profit % to activate trailing stop")
    trailing_distance_pct: float = Field(default=0.008, ge=0, le=1, description="Trailing stop distance %")

    # Dynamic TP/SL
    dynamic_tpsl_enabled: bool = Field(default=False, description="Enable dynamic TP/SL based on S/R")
    use_support_resistance: bool = Field(default=True, description="Use support/resistance for TP/SL")
    min_risk_reward: float = Field(default=1.0, ge=0.1, le=10, description="Minimum risk/reward ratio")
    fallback_sl_pct: float = Field(default=0.01, ge=0.001, le=0.5, description="Fallback SL percentage")
    fallback_tp_pct: float = Field(default=0.02, ge=0.001, le=1, description="Fallback TP percentage")


class TradingConfigResponse(BaseModel):
    id: str
    strategy_id: str
    exchange: str
    symbol: str
    symbols: Optional[list[str]] = None
    intervals: Optional[list[str]] = None
    account_id: Optional[str]
    max_position_pct: float
    stop_loss_pct: float
    is_active: bool

    # Risk control
    leverage: Optional[int] = 1
    max_leverage: Optional[int] = 10
    max_daily_loss_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    require_stop_loss: Optional[bool] = True

    # Trailing stop
    trailing_stop_enabled: Optional[bool] = False
    trailing_activation_pct: Optional[float] = 0.005
    trailing_distance_pct: Optional[float] = 0.008

    # Dynamic TP/SL
    dynamic_tpsl_enabled: Optional[bool] = False
    use_support_resistance: Optional[bool] = True
    min_risk_reward: Optional[float] = 1.0
    fallback_sl_pct: Optional[float] = 0.01
    fallback_tp_pct: Optional[float] = 0.02

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TradingSessionResponse(BaseModel):
    id: str
    config_id: str
    exchange_account_id: Optional[str]
    status: TradingSessionStatus
    started_at: datetime
    stopped_at: Optional[datetime]
    total_pnl: float
    total_trades: int
    error_message: Optional[str]
    
    class Config:
        from_attributes = True


class TradingStartRequest(BaseModel):
    account_id: str


class OrderResponse(BaseModel):
    id: str
    session_id: str
    client_order_id: Optional[str] = None
    exchange_order_id: Optional[str]
    symbol: str
    side: str
    order_type: str
    price: Optional[float]
    size: float
    filled_size: float
    avg_fill_price: Optional[float]
    status: str

    # SDK fields
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    reduce_only: Optional[bool] = False
    fee: Optional[float] = 0.0
    fee_currency: Optional[str] = "USDT"

    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PositionResponse(BaseModel):
    id: str
    session_id: str
    symbol: str
    side: str
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    status: str

    # SDK fields
    leverage: Optional[int] = 1
    margin: Optional[float] = 0.0
    liquidation_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    stop_loss_type: Optional[str] = None
    trailing_stop_activated: Optional[bool] = False
    trailing_stop_price: Optional[float] = None
    highest_price: Optional[float] = None
    lowest_price: Optional[float] = None

    opened_at: datetime
    closed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TradingStatusResponse(BaseModel):
    config: Optional[TradingConfigResponse]
    active_session: Optional[TradingSessionResponse]
    is_trading: bool


class TradingLogResponse(BaseModel):
    id: str
    session_id: str
    level: LogLevel
    message: str
    log_metadata: Optional[dict]
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============== Encryption Helpers ==============

from app.crypto import decrypt_credential


# ============== Config Endpoints ==============

@router.post("/strategies/{strategy_id}/trading/config", response_model=TradingConfigResponse)
def create_or_update_trading_config(
    strategy_id: str,
    req: TradingConfigCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> TradingConfigResponse:
    """Create or update trading configuration for a strategy."""
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN])
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    
    exchange = _clean(req.exchange).lower()
    if exchange not in ("okx", "binance"):
        raise HTTPException(status_code=400, detail="unsupported_exchange")

    symbols = _normalize_list(req.symbols)
    if not symbols and req.symbol:
        symbols = [_clean(req.symbol)]
    if not symbols:
        raise HTTPException(status_code=400, detail="missing_symbols")

    intervals = _normalize_list(req.intervals)
    if not intervals:
        intervals = ["1m"]

    account = db.get(StrategyExchangeAccount, req.account_id)
    if account is None or account.strategy_id != strategy_id:
        raise HTTPException(status_code=404, detail="exchange_account_not_found")
    if account.exchange != exchange:
        raise HTTPException(status_code=400, detail="exchange_account_mismatch")

    config = db.execute(
        select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
    ).scalar_one_or_none()

    logger.warning({
        "event": "trading_config_account",
        "strategy_id": strategy_id,
        "exchange": exchange,
        "account_id": account.id,
    })
    
    if config:
        config.exchange = exchange
        config.symbol = symbols[0]
        config.symbols = symbols
        config.intervals = intervals
        config.max_position_pct = req.max_position_pct
        config.stop_loss_pct = req.stop_loss_pct

        # Risk control
        config.leverage = req.leverage
        config.max_leverage = req.max_leverage
        config.max_daily_loss_pct = req.max_daily_loss_pct
        config.max_drawdown_pct = req.max_drawdown_pct
        config.require_stop_loss = req.require_stop_loss

        # Trailing stop
        config.trailing_stop_enabled = req.trailing_stop_enabled
        config.trailing_activation_pct = req.trailing_activation_pct
        config.trailing_distance_pct = req.trailing_distance_pct

        # Dynamic TP/SL
        config.dynamic_tpsl_enabled = req.dynamic_tpsl_enabled
        config.use_support_resistance = req.use_support_resistance
        config.min_risk_reward = req.min_risk_reward
        config.fallback_sl_pct = req.fallback_sl_pct
        config.fallback_tp_pct = req.fallback_tp_pct

        config.updated_at = datetime.now(timezone.utc)
    else:
        config = TradingConfig(
            strategy_id=strategy_id,
            exchange=exchange,
            symbol=symbols[0],
            symbols=symbols,
            intervals=intervals,
            api_key_encrypted=None,
            api_secret_encrypted=None,
            api_passphrase_encrypted=None,
            max_position_pct=req.max_position_pct,
            stop_loss_pct=req.stop_loss_pct,

            # Risk control
            leverage=req.leverage,
            max_leverage=req.max_leverage,
            max_daily_loss_pct=req.max_daily_loss_pct,
            max_drawdown_pct=req.max_drawdown_pct,
            require_stop_loss=req.require_stop_loss,

            # Trailing stop
            trailing_stop_enabled=req.trailing_stop_enabled,
            trailing_activation_pct=req.trailing_activation_pct,
            trailing_distance_pct=req.trailing_distance_pct,

            # Dynamic TP/SL
            dynamic_tpsl_enabled=req.dynamic_tpsl_enabled,
            use_support_resistance=req.use_support_resistance,
            min_risk_reward=req.min_risk_reward,
            fallback_sl_pct=req.fallback_sl_pct,
            fallback_tp_pct=req.fallback_tp_pct,
        )
        db.add(config)

    config.account_id = account.id
    
    db.commit()
    db.refresh(config)
    return config


@router.get("/strategies/{strategy_id}/trading/config", response_model=Optional[TradingConfigResponse])
def get_trading_config(
    strategy_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[TradingConfigResponse]:
    """Get trading configuration for a strategy."""
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    
    config = db.execute(
        select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
    ).scalar_one_or_none()
    
    return config


@router.delete("/strategies/{strategy_id}/trading/config")
def delete_trading_config(
    strategy_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Delete trading configuration for a strategy."""
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN])
    config = db.execute(
        select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
    ).scalar_one_or_none()
    
    if config is None:
        raise HTTPException(status_code=404, detail="config_not_found")
    
    # Check if there's an active session
    active_session = db.execute(
        select(TradingSession)
        .where(TradingSession.config_id == config.id)
        .where(TradingSession.status.in_([TradingSessionStatus.STARTING, TradingSessionStatus.RUNNING]))
    ).scalar_one_or_none()
    
    if active_session:
        raise HTTPException(status_code=409, detail="cannot_delete_config_with_active_session")
    
    db.delete(config)
    db.commit()
    return {"deleted": True}


# ============== Session Endpoints ==============

@router.post("/strategies/{strategy_id}/trading/start", response_model=TradingSessionResponse)
def start_trading(
    strategy_id: str,
    req: TradingStartRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TradingSessionResponse:
    """Start a live trading session."""
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])
    user = get_current_user(request, db)
    if not user_has_active_subscription(user):
        raise HTTPException(status_code=403, detail="subscription_required")
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    
    config = db.execute(
        select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
    ).scalar_one_or_none()
    
    if config is None:
        raise HTTPException(status_code=400, detail="no_trading_config")

    account = db.get(StrategyExchangeAccount, req.account_id)
    if account is None or account.strategy_id != strategy_id:
        raise HTTPException(status_code=404, detail="exchange_account_not_found")
    if account.exchange != config.exchange:
        raise HTTPException(status_code=400, detail="exchange_account_mismatch")
    
    # Check for existing active session
    active_session = db.execute(
        select(TradingSession)
        .where(TradingSession.config_id == config.id)
        .where(TradingSession.status.in_([TradingSessionStatus.STARTING, TradingSessionStatus.RUNNING]))
    ).scalar_one_or_none()
    
    if active_session:
        from app.trading_engine import TradingSessionManager

        manager = TradingSessionManager.get_session(active_session.id)
        if manager is not None:
            raise HTTPException(status_code=409, detail="session_already_active")

        # Stale session record (e.g., API restart). Mark it stopped so a new
        # session can be created.
        active_session.status = TradingSessionStatus.STOPPED
        active_session.stopped_at = datetime.now(timezone.utc)
        config.is_active = False
        db.commit()

    # Re-validate stored credentials before starting the engine (handles
    # configs created before validation logic, or credentials rotated on OKX).
    exchange = (config.exchange or "").lower()
    if exchange == "okx":
        if not account.api_key_encrypted or not account.api_secret_encrypted or not account.api_passphrase_encrypted:
            raise HTTPException(status_code=400, detail="missing_credentials")
        from okx_sdk import OKXClient
        try:
            key = _clean(account.api_key_encrypted)
            secret = _clean(decrypt_credential(account.api_secret_encrypted))
            passphrase = _clean(decrypt_credential(account.api_passphrase_encrypted or ""))
            logger.warning({
                "event": "start_trading_credentials",
                "strategy_id": strategy_id,
                "api_key": _cred_debug("api_key", key),
                "api_secret": _cred_debug("api_secret", secret),
                "api_passphrase": _cred_debug("api_passphrase", passphrase),
            })
            client = OKXClient(
                api_key=key,
                secret_key=secret,
                passphrase=passphrase,
                simulated=settings.okx_simulated_trading,
            )
            client.test_credentials()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid_credentials: {exc}")

    # Create new session
    session = TradingSession(
        config_id=config.id,
        exchange_account_id=account.id,
        status=TradingSessionStatus.STARTING,
    )
    db.add(session)
    
    # Mark config as active
    config.is_active = True
    
    db.commit()
    db.refresh(session)
    
    # Start trading session via manager
    try:
        from app.trading_engine import TradingSessionManager
        TradingSessionManager.start_session(session.id, db)
        
        # Refresh to get updated status
        db.refresh(session)
    except Exception as e:
        session.status = TradingSessionStatus.ERROR
        session.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=f"failed_to_start_session: {str(e)}")
    
    return session


@router.post("/strategies/{strategy_id}/trading/stop", response_model=TradingSessionResponse)
def stop_trading(
    strategy_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> TradingSessionResponse:
    """Stop the active trading session."""
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])
    config = db.execute(
        select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
    ).scalar_one_or_none()
    
    if config is None:
        raise HTTPException(status_code=400, detail="no_trading_config")
    
    active_session = db.execute(
        select(TradingSession)
        .where(TradingSession.config_id == config.id)
        .where(TradingSession.status.in_([TradingSessionStatus.STARTING, TradingSessionStatus.RUNNING]))
    ).scalar_one_or_none()
    
    if active_session is None:
        raise HTTPException(status_code=400, detail="no_active_session")
    
    # Stop trading session via manager
    try:
        from app.trading_engine import TradingSessionManager
        TradingSessionManager.stop_session(active_session.id, db)
        
        # Mark config as inactive
        config.is_active = False
        db.commit()
        
        # Refresh to get updated status
        db.refresh(active_session)
    except ValueError as e:
        # Session not in memory (e.g., after container restart)
        # Just update the database state directly
        if "is not running" in str(e):
            active_session.status = TradingSessionStatus.STOPPED
            active_session.stopped_at = datetime.now(timezone.utc)
            config.is_active = False
            db.commit()  # Commit before refresh!
            db.refresh(active_session)
        else:
            raise HTTPException(status_code=500, detail=f"failed_to_stop_session: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed_to_stop_session: {str(e)}")
    
    return active_session


@router.get("/strategies/{strategy_id}/trading/status", response_model=TradingStatusResponse)
def get_trading_status(
    strategy_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> TradingStatusResponse:
    """Get current trading status for a strategy."""
    require_strategy_member(request, db, strategy_id)
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    
    config = db.execute(
        select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
    ).scalar_one_or_none()
    
    active_session = None
    if config:
        active_session = db.execute(
            select(TradingSession)
            .where(TradingSession.config_id == config.id)
            .where(TradingSession.status.in_([TradingSessionStatus.STARTING, TradingSessionStatus.RUNNING]))
        ).scalar_one_or_none()
    
    return TradingStatusResponse(
        config=config,
        active_session=active_session,
        is_trading=active_session is not None and active_session.status == TradingSessionStatus.RUNNING,
    )


# ============== Monitoring Endpoints ==============

@router.get("/trading/sessions/{session_id}/orders", response_model=list[OrderResponse])
def list_session_orders(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> list[OrderResponse]:
    """List orders for a trading session."""
    session = _require_session_access(request, db, session_id)
    
    orders = db.execute(
        select(Order)
        .where(Order.session_id == session_id)
        .order_by(Order.created_at.desc())
    ).scalars().all()
    
    return orders


@router.get("/trading/sessions/{session_id}/positions", response_model=list[PositionResponse])
def list_session_positions(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> list[PositionResponse]:
    """List positions for a trading session."""
    session = _require_session_access(request, db, session_id)
    
    positions = db.execute(
        select(Position)
        .where(Position.session_id == session_id)
        .order_by(Position.opened_at.desc())
    ).scalars().all()
    
    return positions


@router.get("/strategies/{strategy_id}/trading/sessions", response_model=list[TradingSessionResponse])
def list_trading_sessions(
    strategy_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> list[TradingSessionResponse]:
    """List all trading sessions for a strategy."""
    require_strategy_member(request, db, strategy_id)
    config = db.execute(
        select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
    ).scalar_one_or_none()
    
    if config is None:
        return []
    
    sessions = db.execute(
        select(TradingSession)
        .where(TradingSession.config_id == config.id)
        .order_by(TradingSession.started_at.desc())
    ).scalars().all()
    
    return sessions


@router.get("/strategies/{strategy_id}/trading/logs", response_model=list[TradingLogResponse])
def get_trading_logs(
    strategy_id: str,
    request: Request,
    level: Optional[LogLevel] = None,
    levels: Optional[list[LogLevel]] = Query(None, description="Filter logs by multiple levels"),
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[TradingLogResponse]:
    """Get trading logs for a strategy's active or most recent session."""
    require_strategy_member(request, db, strategy_id)
    # Get trading config for this strategy
    config = db.execute(
        select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
    ).scalar_one_or_none()
    
    if config is None:
        return []
    
    # Try to get active session first, otherwise get most recent
    session = db.execute(
        select(TradingSession)
        .where(TradingSession.config_id == config.id)
        .where(TradingSession.status.in_([TradingSessionStatus.STARTING, TradingSessionStatus.RUNNING]))
    ).scalar_one_or_none()
    
    if session is None:
        # Get most recent session
        session = db.execute(
            select(TradingSession)
            .where(TradingSession.config_id == config.id)
            .order_by(TradingSession.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    
    if session is None:
        return []
    
    # Build query
    query = select(TradingLog).where(TradingLog.session_id == session.id)

    selected_levels: list[LogLevel] | None = None
    if levels:
        selected_levels = levels
    elif level:
        selected_levels = [level]

    if selected_levels:
        query = query.where(TradingLog.level.in_(selected_levels))
    
    # Order by newest first and limit
    query = query.order_by(TradingLog.created_at.desc()).limit(limit)
    
    logs = db.execute(query).scalars().all()

    return logs


# ============== Trading Symbols Endpoints ==============


class SymbolInfo(BaseModel):
    """Trading symbol information."""
    symbol: str = Field(..., description="Symbol identifier (e.g., BTC-USDT-SWAP)")
    base_coin: str = Field(..., description="Base coin (e.g., BTC)")
    quote_coin: str = Field(..., description="Quote coin (e.g., USDT)")
    contract_type: str = Field(..., description="Contract type (e.g., SWAP)")


class SymbolsListResponse(BaseModel):
    """Response for listing trading symbols."""
    symbols: list[SymbolInfo]
    total: int


@router.get("/symbols", response_model=SymbolsListResponse)
async def list_trading_symbols(
    exchange: str = Query("okx", description="Exchange name (okx, binance)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of symbols to return"),
    db: Session = Depends(get_db),
) -> SymbolsListResponse:
    """
    Get available trading symbols from exchange.

    Fetches the list of trading pairs directly from the exchange,
    sorted by 24h trading volume.

    - **exchange**: Exchange to fetch symbols from (currently only OKX supported)
    - **limit**: Maximum number of symbols to return (default: 50, max: 200)
    """
    if exchange.lower() != "okx":
        raise HTTPException(
            status_code=400,
            detail=f"Exchange '{exchange}' not yet supported. Currently only OKX is available."
        )

    try:
        import httpx

        # Fetch from OKX public API
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get all USDT-SWAP instruments
            response = await client.get(
                "https://www.okx.com/api/v5/public/instruments",
                params={"instType": "SWAP"}
            )
            response.raise_for_status()
            data = response.json()

            if data.get("code") != "0":
                raise HTTPException(
                    status_code=502,
                    detail=f"OKX API error: {data.get('msg', 'Unknown error')}"
                )

            # Filter USDT-margined swaps
            instruments = data.get("data", [])
            usdt_swaps = [
                inst for inst in instruments
                if inst.get("instId", "").endswith("-USDT-SWAP")
            ]

            # Fetch 24h ticker data for volume sorting
            tickers_response = await client.get(
                "https://www.okx.com/api/v5/market/tickers",
                params={"instType": "SWAP"}
            )
            tickers_response.raise_for_status()
            tickers_data = tickers_response.json()

            if tickers_data.get("code") != "0":
                # If ticker API fails, return unsorted list
                logger.warning(f"OKX ticker API error: {tickers_data.get('msg')}")
                tickers = {}
            else:
                # Create a map of instId -> ticker data
                tickers = {
                    t.get("instId"): t
                    for t in tickers_data.get("data", [])
                }

            # Sort by 24h trading volume in USDT (price × volume)
            def get_volume_usdt(inst_id: str) -> float:
                ticker = tickers.get(inst_id, {})
                try:
                    # Get price and volume
                    price_str = ticker.get("last", "0")
                    vol_str = ticker.get("volCcy24h", "0")

                    price = float(price_str) if price_str else 0.0
                    vol = float(vol_str) if vol_str else 0.0

                    # Calculate USDT volume
                    usdt_volume = price * vol
                    return usdt_volume
                except (ValueError, TypeError):
                    return 0.0

            usdt_swaps.sort(key=lambda x: get_volume_usdt(x.get("instId", "")), reverse=True)

            # Limit results
            usdt_swaps = usdt_swaps[:limit]

            # Format response
            symbols = []
            for inst in usdt_swaps:
                inst_id = inst.get("instId", "")
                # Parse instId (e.g., "BTC-USDT-SWAP")
                parts = inst_id.split("-")
                if len(parts) >= 3:
                    base_coin = parts[0]
                    quote_coin = parts[1]
                    contract_type = parts[2]
                else:
                    continue

                symbols.append(SymbolInfo(
                    symbol=inst_id,
                    base_coin=base_coin,
                    quote_coin=quote_coin,
                    contract_type=contract_type,
                ))

            return SymbolsListResponse(
                symbols=symbols,
                total=len(symbols)
            )

    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching symbols from OKX: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to fetch symbols from exchange. Please try again later."
        )
    except Exception as e:
        logger.error(f"Unexpected error fetching symbols: {e}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while fetching symbols."
        )
