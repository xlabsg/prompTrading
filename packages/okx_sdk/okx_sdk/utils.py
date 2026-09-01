"""Utility functions for OKX SDK."""

from decimal import Decimal, ROUND_DOWN
from typing import Optional


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    """
    Floor a value to the nearest step size.
    
    Args:
        value: Value to floor
        step: Step size (lot size)
        
    Returns:
        Floored value
    """
    if step <= 0:
        return value
    if value <= 0:
        return Decimal("0")
    
    try:
        n = (value / step).to_integral_value(rounding=ROUND_DOWN)
        return n * step
    except Exception:
        return Decimal("0")


def normalize_order_size(
    size: float,
    lot_sz: Optional[str] = None,
    min_sz: Optional[str] = None,
    ct_val: Optional[str] = None,
    market_type: str = "swap",
) -> Decimal:
    """
    Normalize order size to exchange constraints.
    
    For SWAP: Converts base currency quantity to contracts using ct_val,
    then floors to lot_sz and enforces min_sz.
    
    For SPOT: Floors base currency quantity to lot_sz and enforces min_sz.
    
    Args:
        size: Requested size in base currency
        lot_sz: Lot size from instrument metadata
        min_sz: Minimum size from instrument metadata
        ct_val: Contract value (for SWAP only)
        market_type: Market type (spot or swap)
        
    Returns:
        Normalized size as Decimal
    """
    req = Decimal(str(size))
    if req <= 0:
        return Decimal("0")
    
    # Convert to contracts for SWAP
    if market_type.lower() != "spot" and ct_val:
        try:
            ct_val_dec = Decimal(ct_val)
            if ct_val_dec > 0:
                req = req / ct_val_dec
        except Exception:
            pass
    
    # Floor to lot size
    if lot_sz:
        try:
            lot_sz_dec = Decimal(lot_sz)
            if lot_sz_dec > 0:
                req = floor_to_step(req, lot_sz_dec)
        except Exception:
            pass
    
    # Enforce minimum size
    if min_sz:
        try:
            min_sz_dec = Decimal(min_sz)
            if min_sz_dec > 0 and req < min_sz_dec:
                return Decimal("0")
        except Exception:
            pass
    
    return req


def format_decimal(value: Decimal) -> str:
    """
    Format Decimal to string without scientific notation.
    
    Args:
        value: Decimal value
        
    Returns:
        String representation
    """
    try:
        return format(value, "f")
    except Exception:
        return str(value)
