"""Data models for OKX SDK."""

from typing import Optional
from pydantic import BaseModel, Field


class OrderRequest(BaseModel):
    """Request model for placing an order."""
    inst_id: str = Field(..., description="Instrument ID, e.g. BTC-USDT-SWAP")
    td_mode: str = Field(..., description="Trade mode: cash, cross, isolated")
    side: str = Field(..., description="Order side: buy, sell")
    ord_type: str = Field(..., description="Order type: market, limit")
    sz: str = Field(..., description="Order size")
    px: Optional[str] = Field(None, description="Order price (required for limit orders)")
    pos_side: Optional[str] = Field(None, description="Position side: net, long, short")
    reduce_only: Optional[bool] = Field(None, description="Reduce only flag")
    cl_ord_id: Optional[str] = Field(None, description="Client order ID")


class OrderResponse(BaseModel):
    """Response model for order placement."""
    ord_id: str = Field(..., description="Order ID")
    cl_ord_id: Optional[str] = Field(None, description="Client order ID")
    s_code: Optional[str] = Field(None, description="Error code")
    s_msg: Optional[str] = Field(None, description="Error message")


class Position(BaseModel):
    """Position model."""
    inst_id: str
    pos_side: str  # long, short, or net
    pos: str  # Position size
    avg_px: str  # Average price
    mark_px: Optional[str] = None  # Mark price (current price)
    last: Optional[str] = None  # Last traded price
    upl: Optional[str] = None  # Unrealized PnL
    upl_ratio: Optional[str] = None  # Unrealized PnL ratio
    lever: Optional[str] = None  # Leverage
    margin: Optional[str] = None  # Margin
    imr: Optional[str] = None  # Initial margin requirement
    mmr: Optional[str] = None  # Maintenance margin requirement
    liq_px: Optional[str] = None  # Estimated liquidation price
    
    
class Balance(BaseModel):
    """Account balance model - matches OKX API response format."""
    ccy: str  # Currency
    availBal: str  # Available balance (OKX uses camelCase)
    cashBal: Optional[str] = None  # Cash balance
    eq: str  # Equity (total balance)
    frozenBal: Optional[str] = None  # Frozen balance
    eqUsd: Optional[str] = None  # Equity in USD

    # Additional optional fields from OKX API
    ordFrozen: Optional[str] = None  # Order frozen balance
    crossLiab: Optional[str] = None  # Cross liability
    isoLiab: Optional[str] = None  # Isolated liability
    upl: Optional[str] = None  # Unrealized PnL
    liab: Optional[str] = None  # Liability

    class Config:
        # Allow field name aliases for backward compatibility
        populate_by_name = True
