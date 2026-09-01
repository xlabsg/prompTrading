from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TradeEvent:
    trade_id: int
    price: float
    quantity: float
    notional: float
    timestamp_ms: int
    side: str
    is_buyer_maker: bool = False
