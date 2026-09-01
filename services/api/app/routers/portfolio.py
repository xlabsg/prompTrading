"""Portfolio monitoring endpoints for live trading."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.enums import PositionStatus, TradingSessionStatus
from control_plane.models import Order, Position, Strategy, StrategyExchangeAccount, TradingConfig, TradingSession
from app.schemas import ExchangeAccountResponse
from app.crypto import decrypt_credential
from app.deps import get_db
from app.settings import settings
from okx_sdk import OKXClient

router = APIRouter()
logger = logging.getLogger(__name__)


def _create_okx_client(account: StrategyExchangeAccount):
    """Build an OKX client for the given exchange account."""

    return OKXClient(
        api_key=(account.api_key_encrypted or "").strip(),
        secret_key=decrypt_credential(account.api_secret_encrypted).strip(),
        passphrase=decrypt_credential(account.api_passphrase_encrypted or "").strip(),
        simulated=settings.okx_simulated_trading,
    )


def _fetch_live_positions(
    config: Optional[TradingConfig],
    account: StrategyExchangeAccount,
) -> Optional[list["PositionData"]]:
    """Fetch current positions from OKX, returning None on failure."""
    try:
        client = _create_okx_client(account)
        inst_id = config.symbol if config else None
        okx_positions = client.get_positions(inst_id=inst_id)

        result: list[PositionData] = []
        for okx_pos in okx_positions:
            try:
                size = float(okx_pos.pos or 0)
            except (TypeError, ValueError):
                size = 0.0
            if size == 0:
                continue

            try:
                avg_px = float(okx_pos.avg_px or 0)
            except (TypeError, ValueError):
                avg_px = 0.0
            try:
                mark_px = float(okx_pos.mark_px or okx_pos.last or 0)
            except (TypeError, ValueError):
                mark_px = avg_px
            try:
                upl = float(okx_pos.upl or 0)
            except (TypeError, ValueError):
                upl = 0.0
            try:
                upl_ratio = float(okx_pos.upl_ratio or 0)
            except (TypeError, ValueError):
                upl_ratio = 0.0
            try:
                margin = float(okx_pos.margin or 0)
            except (TypeError, ValueError):
                margin = 0.0
            lever_value = 1
            if okx_pos.lever:
                try:
                    lever_value = max(1, int(float(okx_pos.lever)))
                except (TypeError, ValueError):
                    lever_value = 1
            if margin == 0 and avg_px > 0 and lever_value > 0:
                margin = size * avg_px / lever_value

            result.append(PositionData(
                inst_id=okx_pos.inst_id,
                pos_side=okx_pos.pos_side,
                pos=size,
                avg_px=avg_px,
                mark_px=mark_px,
                upl=upl,
                upl_ratio=upl_ratio,
                margin=margin,
                lever=lever_value,
                opened_at=None,
            ))

        return result

    except Exception as exc:  # pragma: no cover - relies on live credentials
        logger.error(f"Failed to fetch live positions from OKX: {exc}")
        return None


# ============== Schemas ==============

class PositionData(BaseModel):
    """Position data for portfolio monitor."""
    inst_id: str
    pos_side: str
    pos: float
    avg_px: float
    mark_px: float
    upl: float
    upl_ratio: float
    margin: float
    lever: int
    opened_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class PendingOrderData(BaseModel):
    """Pending order data."""
    order_id: str
    exchange_order_id: Optional[str]
    inst_id: str
    side: str
    order_type: str
    sz: float
    px: Optional[float]
    filled_size: float
    avg_fill_price: Optional[float]
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class BalanceData(BaseModel):
    """Balance data for portfolio."""
    total_equity: float
    available: float
    frozen: float
    unrealized_pnl: float
    margin_used: float


class PortfolioSummary(BaseModel):
    """Portfolio summary response."""
    has_trading_config: bool
    has_active_session: bool
    balance: Optional[BalanceData]
    positions: list[PositionData]
    total_pnl: float
    total_trades: int


# ============== Endpoints ==============

@router.get("/api/portfolio/{strategy_id}/accounts", response_model=list[ExchangeAccountResponse])
async def list_portfolio_accounts(
    strategy_id: str,
    db: Session = Depends(get_db),
) -> list[ExchangeAccountResponse]:
    """List exchange accounts for a strategy."""
    return (
        db.execute(
            select(StrategyExchangeAccount)
            .where(StrategyExchangeAccount.strategy_id == strategy_id)
            .order_by(StrategyExchangeAccount.created_at.desc())
        )
        .scalars()
        .all()
    )


@router.get("/api/portfolio/{strategy_id}/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    strategy_id: str,
    account_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> PortfolioSummary:
    """Get portfolio summary for a strategy's active trading session."""
    # Get strategy
    strategy = db.get(Strategy, strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="strategy_not_found")

    account: Optional[StrategyExchangeAccount] = None
    config = None
    session = None

    if account_id:
        account = db.get(StrategyExchangeAccount, account_id)
        if account is None or account.strategy_id != strategy_id:
            raise HTTPException(status_code=404, detail="account_not_found")
    else:
        # Get trading config
        config = db.execute(
            select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
        ).scalar_one_or_none()
    
    if not account:
        if not config:
            return PortfolioSummary(
                has_trading_config=False,
                has_active_session=False,
                balance=None,
                positions=[],
                total_pnl=0.0,
                total_trades=0,
            )
    
        # Get active session
        session = db.execute(
            select(TradingSession)
            .where(TradingSession.config_id == config.id)
            .where(TradingSession.status.in_([TradingSessionStatus.STARTING, TradingSessionStatus.RUNNING]))
        ).scalar_one_or_none()
        
        if not session:
            return PortfolioSummary(
                has_trading_config=True,
                has_active_session=False,
                balance=None,
                positions=[],
                total_pnl=0.0,
                total_trades=0,
            )

    # Load cached positions from DB (used as fallback)
    positions = []
    if session:
        positions = db.execute(
            select(Position)
            .where(Position.session_id == session.id)
            .where(Position.status == PositionStatus.OPEN)
        ).scalars().all()

    if not account:
        account_id = session.exchange_account_id or config.account_id
        account = db.get(StrategyExchangeAccount, account_id) if account_id else None

    live_positions = None
    exchange = account.exchange if account else (config.exchange if config else None)
    if account and exchange == "okx":
        if account.api_key_encrypted and account.api_secret_encrypted and account.api_passphrase_encrypted:
            live_positions = _fetch_live_positions(config, account)
    if live_positions is not None:
        position_data = live_positions
    else:
        position_data = [
            PositionData(
                inst_id=pos.symbol,
                pos_side=pos.side.value,
                pos=pos.size,
                avg_px=pos.entry_price,
                mark_px=pos.current_price,
                upl=pos.unrealized_pnl,
                upl_ratio=(pos.unrealized_pnl / (pos.entry_price * pos.size) * 100) if pos.size > 0 else 0.0,
                margin=pos.size * pos.entry_price / 10,
                lever=10,
                opened_at=pos.opened_at,
            )
            for pos in positions
        ]

    # Fetch real balance from OKX
    balance_data = None  # Default to None if we can't fetch real data
    
    if account and exchange == "okx":
        try:
            client = _create_okx_client(account)
            
            # Get account balance (returns list of Balance objects per currency)
            balances = client.get_balance()
            
            if balances:
                # Find USDT balance or use first balance
                usdt_balance = next((b for b in balances if b.ccy == "USDT"), balances[0] if balances else None)
                
                if usdt_balance:
                    total_eq = float(usdt_balance.eq or 0)  # Equity (total balance)
                    avail_bal = float(usdt_balance.availBal or 0)  # OKX uses camelCase
                    frozen = float(usdt_balance.frozenBal or 0)  # OKX uses camelCase

                    balance_data = BalanceData(
                        total_equity=total_eq,
                        available=avail_bal,
                        frozen=frozen,
                        unrealized_pnl=sum(pos.upl for pos in position_data),
                        margin_used=sum(pos.margin for pos in position_data),
                    )
                
        except Exception as e:
            logger.error(f"Failed to fetch balance from OKX: {e}")
            # Don't use fallback data, leave as None
            balance_data = None
    
    total_pnl = session.total_pnl if session else 0.0
    total_trades = session.total_trades if session else 0

    return PortfolioSummary(
        has_trading_config=True,
        has_active_session=True,
        balance=balance_data,
        positions=position_data,
        total_pnl=total_pnl,
        total_trades=total_trades,
    )


@router.get("/api/portfolio/{strategy_id}/positions", response_model=list[PositionData])
async def get_positions(
    strategy_id: str,
    account_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> list[PositionData]:
    """Get current positions for strategy's active session."""
    config = None
    session = None
    account: Optional[StrategyExchangeAccount] = None

    if account_id:
        account = db.get(StrategyExchangeAccount, account_id)
        if account is None or account.strategy_id != strategy_id:
            raise HTTPException(status_code=404, detail="account_not_found")
    else:
        config = db.execute(
            select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
        ).scalar_one_or_none()
    
    if not account:
        if not config:
            return []
    
        session = db.execute(
            select(TradingSession)
            .where(TradingSession.config_id == config.id)
            .where(TradingSession.status.in_([TradingSessionStatus.STARTING, TradingSessionStatus.RUNNING]))
        ).scalar_one_or_none()
        
        if not session:
            return []
    
    # Load account from session or config
    if not account:
        account_id = session.exchange_account_id or config.account_id
        account = db.get(StrategyExchangeAccount, account_id) if account_id else None
    
    exchange = account.exchange if account else (config.exchange if config else None)
    if account and exchange == "okx":
        live_positions = _fetch_live_positions(config, account)
        if live_positions is not None:
            return live_positions

    positions = db.execute(
        select(Position)
        .where(Position.session_id == session.id)
        .where(Position.status == PositionStatus.OPEN)
        .order_by(Position.opened_at.desc())
    ).scalars().all()
    
    return [
        PositionData(
            inst_id=pos.symbol,
            pos_side=pos.side.value,
            pos=pos.size,
            avg_px=pos.entry_price,
            mark_px=pos.current_price,
            upl=pos.unrealized_pnl,
            upl_ratio=(pos.unrealized_pnl / (pos.entry_price * pos.size) * 100) if pos.size > 0 else 0.0,
            margin=pos.size * pos.entry_price / 10,
            lever=10,
            opened_at=pos.opened_at,
        )
        for pos in positions
    ]


@router.get("/api/portfolio/{strategy_id}/pending-orders", response_model=list[PendingOrderData])
async def get_pending_orders(
    strategy_id: str,
    account_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> list[PendingOrderData]:
    """Get pending orders from OKX."""
    config = None
    session = None
    account: Optional[StrategyExchangeAccount] = None

    if account_id:
        account = db.get(StrategyExchangeAccount, account_id)
        if account is None or account.strategy_id != strategy_id:
            raise HTTPException(status_code=404, detail="account_not_found")
    else:
        config = db.execute(
            select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
        ).scalar_one_or_none()

    if not account:
        if not config:
            return []

        # Get active session to find account
        session = db.execute(
            select(TradingSession)
            .where(TradingSession.config_id == config.id)
            .where(TradingSession.status.in_([TradingSessionStatus.STARTING, TradingSessionStatus.RUNNING]))
        ).scalar_one_or_none()

    # Load account from session or config
    if not account:
        account_id = session.exchange_account_id if session else config.account_id
        account = db.get(StrategyExchangeAccount, account_id) if account_id else None

    if not account:
        return []

    # Fetch from OKX API directly
    try:
        client = _create_okx_client(account)

        # Get pending orders from OKX
        orders_data = client.get_pending_orders(inst_type="SWAP")

        result = []
        for order in orders_data:
            # Parse timestamp
            created_ts = int(order.get("cTime", 0)) / 1000

            result.append(PendingOrderData(
                order_id=order.get("ordId", ""),
                exchange_order_id=order.get("ordId", ""),
                inst_id=order.get("instId", ""),
                side=order.get("side", ""),
                order_type=order.get("ordType", ""),
                sz=float(order.get("sz", 0)),
                px=float(order.get("px", 0)) if order.get("px") else None,
                filled_size=float(order.get("fillSz", 0) or 0),
                avg_fill_price=float(order.get("avgPx", 0)) if order.get("avgPx") else None,
                status=order.get("state", ""),
                created_at=datetime.fromtimestamp(created_ts, tz=timezone.utc),
            ))

        return result

    except Exception as e:
        logger.error(f"Failed to fetch pending orders from OKX: {e}")
        return []


@router.get("/api/portfolio/{strategy_id}/orders-history")
async def get_orders_history(
    strategy_id: str,
    limit: int = 50,
    account_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get order history from OKX (last 7 days)."""
    config = None
    session = None
    account: Optional[StrategyExchangeAccount] = None

    if account_id:
        account = db.get(StrategyExchangeAccount, account_id)
        if account is None or account.strategy_id != strategy_id:
            raise HTTPException(status_code=404, detail="account_not_found")
    else:
        config = db.execute(
            select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
        ).scalar_one_or_none()

    if not account:
        if not config:
            return {"items": [], "has_more": False}

        # Get active session to find account
        session = db.execute(
            select(TradingSession)
            .where(TradingSession.config_id == config.id)
            .where(TradingSession.status.in_([TradingSessionStatus.STARTING, TradingSessionStatus.RUNNING]))
        ).scalar_one_or_none()

    # Load account from session or config
    if not account:
        account_id = session.exchange_account_id if session else config.account_id
        account = db.get(StrategyExchangeAccount, account_id) if account_id else None

    if not account:
        return {"items": [], "has_more": False}

    # Fetch from OKX API directly
    try:
        client = _create_okx_client(account)

        # Get order history from OKX
        orders_data = client.get_orders_history(
            inst_type="SWAP",
            limit=limit,
            use_archive=True,
        )

        logger.info(f"[Portfolio] Fetched {len(orders_data)} orders from OKX")

        items = []
        for order in orders_data:
            # Parse timestamp
            created_ts = int(order.get("cTime", 0)) / 1000
            updated_ts = int(order.get("uTime", 0)) / 1000

            items.append({
                "order_id": order.get("ordId", ""),
                "exchange_order_id": order.get("ordId", ""),
                "symbol": order.get("instId", ""),
                "side": order.get("side", ""),
                "order_type": order.get("ordType", ""),
                "price": float(order.get("px", 0)) if order.get("px") else None,
                "size": float(order.get("sz", 0)),
                "filled_size": float(order.get("fillSz", 0) or 0),
                "avg_fill_price": float(order.get("avgPx", 0)) if order.get("avgPx") else None,
                "status": order.get("state", ""),
                "created_at": datetime.fromtimestamp(created_ts, tz=timezone.utc).isoformat(),
                "updated_at": datetime.fromtimestamp(updated_ts, tz=timezone.utc).isoformat(),
            })

        return {
            "items": items,
            "has_more": len(orders_data) >= limit,
        }

    except Exception as e:
        logger.error(f"Failed to fetch order history from OKX: {e}")
        return {"items": [], "has_more": False}


class PositionHistoryData(BaseModel):
    """Closed position history data."""
    inst_id: str
    pos_side: str
    pos: float
    entry_px: float
    exit_px: float
    realized_pnl: float
    return_pct: float
    opened_at: datetime
    closed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


@router.get("/api/portfolio/{strategy_id}/positions-history", response_model=list[PositionHistoryData])
async def get_positions_history(
    strategy_id: str,
    limit: int = 50,
    account_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> list[PositionHistoryData]:
    """Get closed positions history from OKX."""
    config = None
    session = None
    account: Optional[StrategyExchangeAccount] = None

    if account_id:
        account = db.get(StrategyExchangeAccount, account_id)
        if account is None or account.strategy_id != strategy_id:
            raise HTTPException(status_code=404, detail="account_not_found")
    else:
        config = db.execute(
            select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
        ).scalar_one_or_none()

    if not account:
        if not config:
            return []

        # Get active session to find account
        session = db.execute(
            select(TradingSession)
            .where(TradingSession.config_id == config.id)
            .where(TradingSession.status.in_([TradingSessionStatus.STARTING, TradingSessionStatus.RUNNING]))
        ).scalar_one_or_none()

    # Load account from session or config
    if not account:
        account_id = session.exchange_account_id if session else config.account_id
        account = db.get(StrategyExchangeAccount, account_id) if account_id else None

    if not account:
        return []

    # Fetch from OKX API directly
    try:
        client = _create_okx_client(account)

        # Get position history from OKX
        positions_data = client.get_positions_history(inst_type="SWAP", limit=limit)

        result = []
        for pos in positions_data:
            # Parse timestamps
            created_ts = int(pos.get("cTime", 0)) / 1000
            updated_ts = int(pos.get("uTime", 0)) / 1000

            # Parse values
            open_avg_px = float(pos.get("openAvgPx", 0) or 0)
            close_avg_px = float(pos.get("closeAvgPx", 0) or 0)
            close_total_pos = float(pos.get("closeTotalPos", 0) or 0)
            pnl = float(pos.get("pnl", 0) or 0)
            pnl_ratio = float(pos.get("pnlRatio", 0) or 0)

            result.append(PositionHistoryData(
                inst_id=pos.get("instId", ""),
                pos_side=pos.get("direction", ""),  # OKX uses 'direction' field
                pos=close_total_pos,
                entry_px=open_avg_px,
                exit_px=close_avg_px,
                realized_pnl=pnl,
                return_pct=pnl_ratio * 100,  # Convert to percentage
                opened_at=datetime.fromtimestamp(created_ts, tz=timezone.utc),
                closed_at=datetime.fromtimestamp(updated_ts, tz=timezone.utc),
            ))

        return result

    except Exception as e:
        logger.error(f"Failed to fetch position history from OKX: {e}")
        return []


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float


@router.get("/api/portfolio/{strategy_id}/equity-curve", response_model=list[EquityPoint])
async def get_equity_curve(
    strategy_id: str,
    db: Session = Depends(get_db),
) -> list[EquityPoint]:
    """Get equity curve based on realized PnL."""
    config = db.execute(
        select(TradingConfig).where(TradingConfig.strategy_id == strategy_id)
    ).scalar_one_or_none()
    
    if not config:
        return []
        
    session = db.execute(
        select(TradingSession)
        .where(TradingSession.config_id == config.id)
        .order_by(TradingSession.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    
    if not session:
        return []
        
    # Get all closed positions ordered by time
    closed_positions = db.execute(
        select(Position)
        .where(Position.session_id == session.id)
        .where(Position.status == PositionStatus.CLOSED)
        .order_by(Position.closed_at.asc())
    ).scalars().all()
    
    initial_equity = 10000.0  # Mock baseline
    equity = initial_equity
    curve = [EquityPoint(timestamp=session.started_at, equity=equity)]
    
    for pos in closed_positions:
        if pos.closed_at:
            equity += pos.realized_pnl
            curve.append(EquityPoint(timestamp=pos.closed_at, equity=equity))
            
    # Add current point if session is running
    if session.status == TradingSessionStatus.RUNNING:
        current_equity = equity  # + unrealized PnL?
        # Get active positions PnL
        active_positions = db.execute(
             select(Position)
            .where(Position.session_id == session.id)
            .where(Position.status == PositionStatus.OPEN)
        ).scalars().all()
        
        unrealized_pnl = sum(p.unrealized_pnl for p in active_positions)
        current_equity += unrealized_pnl
        curve.append(EquityPoint(timestamp=datetime.now(timezone.utc), equity=current_equity))
            
    return curve
