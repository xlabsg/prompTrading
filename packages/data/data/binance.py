from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import requests

from data.cache import cached_fetch, interval_to_ms


@dataclass(frozen=True)
class KlinesRequest:
    symbol: str
    interval: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    limit: int = 1000


BINANCE_SPOT_BASE_URL = "https://api.binance.com"


def _fetch_klines_uncached(req: KlinesRequest) -> pd.DataFrame:
    """Fetch OHLCV klines from Binance Spot public API.

    Returns DataFrame with columns: timestamp (ms), open, high, low, close, volume.
    """
    per_page = int(req.limit)
    if per_page <= 0:
        raise ValueError("limit must be positive")
    if per_page > 1000:
        per_page = 1000

    rows: list[list[object]] = []

    # Binance returns ascending by open time.
    # We only paginate forward when start_ms is provided; otherwise keep it simple (single request).
    next_start_ms = int(req.start_ms) if req.start_ms is not None else None
    max_pages = 500  # safety cap
    for _ in range(max_pages):
        params: dict[str, object] = {"symbol": req.symbol, "interval": req.interval, "limit": per_page}
        if next_start_ms is not None:
            params["startTime"] = int(next_start_ms)
        if req.end_ms is not None:
            params["endTime"] = int(req.end_ms)

        resp = requests.get(f"{BINANCE_SPOT_BASE_URL}/api/v3/klines", params=params, timeout=30)
        resp.raise_for_status()
        batch = resp.json() or []
        if not batch:
            break
        rows.extend(batch)

        # Stop if we are not paginating.
        if next_start_ms is None:
            break

        # Stop when fewer bars than requested (no more data in range).
        if len(batch) < per_page:
            break

        last_open_ms = int(batch[-1][0])
        new_start = last_open_ms + 1
        if new_start <= next_start_ms:
            break
        next_start_ms = new_start
        if req.end_ms is not None and next_start_ms > int(req.end_ms):
            break

    # Binance kline schema:
    # [
    #   0 open time(ms),
    #   1 open, 2 high, 3 low, 4 close, 5 volume,
    #   6 close time, 7 quote asset volume, 8 number of trades, ...
    # ]
    df = pd.DataFrame(
        {
            "timestamp": [int(r[0]) for r in rows],
            "open": [float(r[1]) for r in rows],
            "high": [float(r[2]) for r in rows],
            "low": [float(r[3]) for r in rows],
            "close": [float(r[4]) for r in rows],
            "volume": [float(r[5]) for r in rows],
        }
    )
    if not df.empty:
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df



def fetch_klines(req: KlinesRequest) -> pd.DataFrame:
    """Cache-aware wrapper around the Binance klines API."""

    def _fetch(start_ms: int | None, end_ms: int | None) -> pd.DataFrame:
        return _fetch_klines_uncached(
            KlinesRequest(
                symbol=req.symbol,
                interval=req.interval,
                start_ms=start_ms,
                end_ms=end_ms,
                limit=req.limit,
            )
        )

    return cached_fetch(
        exchange="binance",
        symbol=req.symbol,
        interval=req.interval,
        start_ms=req.start_ms,
        end_ms=req.end_ms,
        fetch=_fetch,
        interval_ms=interval_to_ms(req.interval),
    )
