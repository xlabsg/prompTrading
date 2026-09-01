from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import requests


@dataclass(frozen=True)
class CandlesRequest:
    """OKX candles request.

    inst_id examples:
      - Spot: BTC-USDT
      - Swap: BTC-USDT-SWAP
    """

    inst_id: str
    bar: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    limit: int = 1000


OKX_BASE_URL = "https://www.okx.com"
# OKX candle endpoints accept up to 300 bars per request (values above are capped server-side).
OKX_MAX_LIMIT = 300
OKX_CANDLES_PATH = "/api/v5/market/candles"
OKX_HISTORY_CANDLES_PATH = "/api/v5/market/history-candles"
_RECENT_CANDLES_MAX_DAYS = 60


def interval_to_okx_bar(interval: str) -> str:
    """Convert common intervals (e.g. '1h') to OKX bar format (e.g. '1H')."""
    s = (interval or "").strip()
    if not s:
        raise ValueError("interval is required")

    # Accept OKX native formats directly.
    if s[-1] in ("m", "H", "D", "W", "M", "Y"):
        return s

    unit = s[-1]
    n_str = s[:-1]
    try:
        n = int(n_str)
    except Exception as e:
        raise ValueError(f"invalid_interval:{interval}") from e
    if n <= 0:
        raise ValueError(f"invalid_interval:{interval}")

    if unit == "m":
        return f"{n}m"
    if unit == "h":
        return f"{n}H"
    if unit == "d":
        return f"{n}D"
    if unit == "w":
        return f"{n}W"

    raise ValueError(f"unsupported_interval:{interval}")


def _bar_ms(bar: str) -> int | None:
    s = (bar or "").strip()
    if not s:
        return None
    unit = s[-1]
    try:
        n = int(s[:-1])
    except Exception:
        return None
    if n <= 0:
        return None
    if unit == "m":
        return n * 60 * 1000
    if unit == "H":
        return n * 60 * 60 * 1000
    if unit == "D":
        return n * 24 * 60 * 60 * 1000
    if unit == "W":
        return n * 7 * 24 * 60 * 60 * 1000
    return None


def _parse_okx_payload(payload: dict) -> list[list[str]]:
    if not isinstance(payload, dict):
        raise ValueError("okx_invalid_response")
    code = str(payload.get("code", ""))
    if code != "0":
        msg = payload.get("msg", "")
        raise RuntimeError(f"okx_api_error:{code}:{msg}")
    data = payload.get("data") or []
    if not isinstance(data, list):
        raise ValueError("okx_invalid_response_data")
    return data


def _fetch_page(
    *,
    path: str,
    inst_id: str,
    bar: str,
    limit: int,
    cursor_param: str | None,
    cursor_ms: int | None,
) -> list[list[str]]:
    params: dict[str, object] = {"instId": inst_id, "bar": bar, "limit": int(limit)}
    if cursor_param and cursor_ms is not None:
        params[cursor_param] = str(int(cursor_ms))
    resp = requests.get(f"{OKX_BASE_URL}{path}", params=params, timeout=30)
    resp.raise_for_status()
    return _parse_okx_payload(resp.json())


def fetch_candles(req: CandlesRequest) -> pd.DataFrame:
    """Fetch OHLCV candles from OKX public API (v5 market/candles).

    Returns DataFrame with columns: timestamp (ms), open, high, low, close, volume.
    Notes:
    - OKX returns candles in reverse chronological order; we normalize to ascending.
    - MVP supports best-effort pagination to collect up to `req.limit` bars.
    """
    inst_id = (req.inst_id or "").strip()
    if not inst_id:
        raise ValueError("inst_id is required")
    bar = (req.bar or "").strip()
    if not bar:
        raise ValueError("bar is required")
    total_limit = int(req.limit)
    if total_limit <= 0:
        raise ValueError("limit must be positive")

    # OKX provides two endpoints:
    # - /market/candles: recent-only (1H stops around ~60 days)
    # - /market/history-candles: deeper history (supports 1y+ with pagination)
    path = OKX_CANDLES_PATH
    span_days = None
    if req.start_ms is not None and req.end_ms is not None:
        span_days = (int(req.end_ms) - int(req.start_ms)) / (1000.0 * 60.0 * 60.0 * 24.0)
    elif req.start_ms is None and req.end_ms is None:
        # Heuristic: infer the approximate span requested from limit * bar interval.
        step_ms = _bar_ms(bar)
        if step_ms:
            span_days = (float(step_ms) * float(total_limit)) / (1000.0 * 60.0 * 60.0 * 24.0)

    if span_days is not None and span_days > float(_RECENT_CANDLES_MAX_DAYS):
        path = OKX_HISTORY_CANDLES_PATH

    rows: list[list[str]] = []
    remaining = total_limit
    # OKX candle endpoint uses counter-intuitive cursor semantics:
    # - "after" returns candles with timestamp < after (older data, reverse-chron order)
    # - "before" returns candles with timestamp > before (newer data)
    # For a bounded [start_ms, end_ms] fetch, we page older using "after".
    cursor_param: str | None = "after"
    cursor_ms: int | None = (int(req.end_ms) + 1) if req.end_ms is not None else None

    max_pages = 500  # safety cap
    last_oldest: int | None = None

    for _ in range(max_pages):
        page_limit = min(OKX_MAX_LIMIT, remaining)
        batch = _fetch_page(
            path=path,
            inst_id=inst_id,
            bar=bar,
            limit=page_limit,
            cursor_param=cursor_param,
            cursor_ms=cursor_ms,
        )
        if not batch:
            break

        rows.extend(batch)
        remaining = total_limit - len(rows)

        ts_list = [int(r[0]) for r in batch if r]
        if not ts_list:
            break
        oldest = min(ts_list)

        # Stop when we reached the requested start boundary (best-effort).
        if req.start_ms is not None and oldest <= int(req.start_ms):
            break
        if remaining <= 0:
            break

        # Cursor is set to the oldest timestamp we have; with "after" this moves older.
        cursor_ms = oldest
        if last_oldest is not None and oldest >= last_oldest:
            # No progress; avoid infinite loops.
            break
        last_oldest = oldest

    # OKX candle schema (strings): [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
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
    if df.empty:
        return df

    # Filter by optional range.
    if req.start_ms is not None:
        df = df[df["timestamp"] >= int(req.start_ms)]
    if req.end_ms is not None:
        df = df[df["timestamp"] <= int(req.end_ms)]

    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    # Keep at most total_limit bars (newest within any filtered range).
    if len(df) > total_limit:
        df = df.tail(total_limit).reset_index(drop=True)
    return df
