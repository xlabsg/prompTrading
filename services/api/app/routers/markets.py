from __future__ import annotations

from fastapi import APIRouter, Query

from app.market_data.us_stocks import load_nasdaq_symbols
from app.schemas import USStockSymbolResponse

router = APIRouter()


@router.get("/markets/us-stocks", response_model=list[USStockSymbolResponse])
def list_us_stocks(
    q: str | None = None,
    limit: int = Query(500, ge=0),
    offset: int = Query(0, ge=0),
    force_refresh: bool = False,
) -> list[USStockSymbolResponse]:
    symbols = load_nasdaq_symbols(force_refresh=force_refresh)
    if q:
        needle = q.strip().lower()
        if needle:
            symbols = [
                s
                for s in symbols
                if needle in s.get("symbol", "").lower() or needle in s.get("name", "").lower()
            ]
    if offset:
        symbols = symbols[offset:]
    if limit == 0:
        return symbols
    return symbols[:limit]
