"""Shared OHLCV cache for market data providers.

Historical bars never change, so repeated backtests over the same dataset should
not re-hit the exchange. This module stores one parquet per
`(exchange, symbol, interval)` on the shared workspaces volume, alongside a meta
file recording which *requested* range the cache is known to cover.

Providers stay free of cache logic: they pass a `fetch` callable that takes
`(start_ms, end_ms)` and returns a DataFrame with the standard columns
(`timestamp`, `open`, `high`, `low`, `close`, `volume`).

Environment:
  MARKET_DATA_CACHE_DIR      cache root (default /workspaces/market_data_cache)
  MARKET_DATA_CACHE_ENABLED  set to 0/false/no to bypass the cache entirely
  MARKET_DATA_CACHE_TTL_S    freshness window for the trailing edge (default 300)
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

import pandas as pd

DEFAULT_CACHE_DIR = "/workspaces/market_data_cache"
DEFAULT_TTL_S = 300.0

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

FetchFn = Callable[[Optional[int], Optional[int]], pd.DataFrame]


def cache_dir() -> str:
    """Cache root. Falls back to the legacy US-stock variable for compatibility."""
    return (
        os.getenv("MARKET_DATA_CACHE_DIR")
        or os.getenv("US_STOCK_CACHE_DIR")
        or DEFAULT_CACHE_DIR
    )


def cache_enabled() -> bool:
    raw = (os.getenv("MARKET_DATA_CACHE_ENABLED") or "").strip().lower()
    if not raw:
        return True
    return raw not in ("0", "false", "no")


def _ttl_s() -> float:
    raw = (os.getenv("MARKET_DATA_CACHE_TTL_S") or "").strip()
    if not raw:
        return DEFAULT_TTL_S
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_TTL_S


def interval_to_ms(interval: str) -> int | None:
    """Best-effort '1h' / '15m' / '1D' -> milliseconds. None when unparseable."""
    s = (interval or "").strip()
    if len(s) < 2:
        return None
    unit = s[-1]
    try:
        n = int(s[:-1])
    except ValueError:
        return None
    if n <= 0:
        return None
    factors = {
        "m": 60_000,
        "h": 3_600_000,
        "H": 3_600_000,
        "d": 86_400_000,
        "D": 86_400_000,
        "w": 604_800_000,
        "W": 604_800_000,
    }
    factor = factors.get(unit)
    return n * factor if factor else None


def _slug(*parts: str) -> str:
    out = []
    for p in parts:
        s = (p or "").strip()
        for ch in "/\\:*?\"<>| ":
            s = s.replace(ch, "_")
        out.append(s or "_")
    return "__".join(out)


def _paths(exchange: str, symbol: str, interval: str) -> tuple[str, str]:
    base = cache_dir()
    stem = _slug(exchange, symbol, interval)
    return os.path.join(base, f"{stem}.parquet"), os.path.join(base, f"{stem}.meta.json")


def _read(data_path: str, meta_path: str) -> tuple[pd.DataFrame | None, dict]:
    if not os.path.exists(data_path) or not os.path.exists(meta_path):
        return None, {}
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        df = pd.read_parquet(data_path)
    except Exception:
        # A corrupt or half-written cache entry must never break a backtest.
        return None, {}
    if not isinstance(meta, dict) or df is None or df.empty:
        return None, {}
    return df, meta


def _write(data_path: str, meta_path: str, df: pd.DataFrame, meta: dict) -> None:
    """Write atomically so concurrent containers never read a partial file."""
    try:
        os.makedirs(os.path.dirname(data_path), exist_ok=True)
        tmp_data = f"{data_path}.tmp.{os.getpid()}"
        tmp_meta = f"{meta_path}.tmp.{os.getpid()}"
        df.to_parquet(tmp_data, index=False)
        with open(tmp_meta, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        os.replace(tmp_data, data_path)
        os.replace(tmp_meta, meta_path)
    except Exception:
        # Caching is an optimisation; a write failure must not fail the caller.
        for tmp in (f"{data_path}.tmp.{os.getpid()}", f"{meta_path}.tmp.{os.getpid()}"):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)
    out = df.copy()
    out["timestamp"] = out["timestamp"].astype("int64")
    return (
        out.drop_duplicates(subset=["timestamp"], keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def _merge(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    if old is None or old.empty:
        return _normalize(new)
    if new is None or new.empty:
        return _normalize(old)
    # `keep="last"` lets a refetch correct the previously-incomplete trailing bar.
    return _normalize(pd.concat([old, new], ignore_index=True))


def _slice(df: pd.DataFrame, start_ms: int | None, end_ms: int | None) -> pd.DataFrame:
    out = df
    if start_ms is not None:
        out = out[out["timestamp"] >= int(start_ms)]
    if end_ms is not None:
        out = out[out["timestamp"] <= int(end_ms)]
    return out.reset_index(drop=True)


def _covers_start(covered_start: int | None, start_ms: int | None) -> bool:
    if covered_start is None:
        # Cache was populated with an open-ended start: it covers everything.
        return True
    if start_ms is None:
        # Caller wants "from the beginning" but we only have a bounded history.
        return False
    return int(start_ms) >= int(covered_start)


def cached_fetch(
    *,
    exchange: str,
    symbol: str,
    interval: str,
    start_ms: int | None,
    end_ms: int | None,
    fetch: FetchFn,
    interval_ms: int | None = None,
    fallback_to_stale_on_error: bool = False,
) -> pd.DataFrame:
    """Return OHLCV for the requested range, hitting `fetch` only for what is missing.

    `fetch(start_ms, end_ms)` must return the standard OHLCV columns. Any cache
    failure degrades to a plain `fetch` call rather than raising.

    With `fallback_to_stale_on_error`, an upstream failure serves whatever the
    cache already holds instead of propagating — for providers that rate-limit.
    """
    if not cache_enabled():
        return fetch(start_ms, end_ms)

    step_ms = interval_ms if interval_ms is not None else interval_to_ms(interval)
    now_ms = int(time.time() * 1000)
    # An open-ended request tracks "now"; pin it so coverage bookkeeping is stable.
    effective_end = int(end_ms) if end_ms is not None else now_ms

    data_path, meta_path = _paths(exchange, symbol, interval)
    cached, meta = _read(data_path, meta_path)

    covered_start = meta.get("covered_start_ms")
    covered_end = meta.get("covered_end_ms")
    covered_start = None if covered_start is None else int(covered_start)
    covered_end = None if covered_end is None else int(covered_end)

    if cached is not None and covered_end is not None and _covers_start(covered_start, start_ms):
        at_trailing_edge = step_ms is not None and effective_end >= (now_ms - step_ms)
        stale = (time.time() - float(meta.get("updated_at") or 0)) > _ttl_s()

        if effective_end <= covered_end and not (at_trailing_edge and stale):
            return _slice(cached, start_ms, end_ms)

        # Extend forward only: refetch from the last cached bar so the previously
        # incomplete trailing bar gets corrected.
        gap_start = covered_end if step_ms is None else max(covered_end - step_ms, 0)
        try:
            fresh = fetch(gap_start, effective_end)
        except Exception:
            # Upstream is unavailable but we still hold usable history.
            if fallback_to_stale_on_error or effective_end <= covered_end:
                return _slice(cached, start_ms, end_ms)
            raise
        merged = _merge(cached, fresh)
        _write(
            data_path,
            meta_path,
            merged,
            {
                "exchange": exchange,
                "symbol": symbol,
                "interval": interval,
                "covered_start_ms": covered_start,
                "covered_end_ms": max(covered_end, effective_end),
                "updated_at": time.time(),
                "rows": int(len(merged)),
            },
        )
        return _slice(merged, start_ms, end_ms)

    # Cache miss (or a range we cannot serve): fetch the whole request.
    try:
        fresh = fetch(start_ms, end_ms)
    except Exception:
        if fallback_to_stale_on_error and cached is not None and not cached.empty:
            return _slice(cached, start_ms, end_ms)
        raise
    merged = _merge(cached, fresh)

    new_start: int | None = None if start_ms is None else int(start_ms)
    new_end = effective_end
    # Union with the old coverage only when the two ranges touch; otherwise the
    # gap between them would be silently claimed as cached.
    if covered_end is not None and _covers_start(covered_start, start_ms):
        new_start = covered_start
        new_end = max(covered_end, effective_end)
    elif covered_start is not None and covered_end is not None and new_start is not None:
        if new_start <= covered_end and new_end >= covered_start:
            new_start = min(new_start, covered_start)
            new_end = max(new_end, covered_end)

    _write(
        data_path,
        meta_path,
        merged,
        {
            "exchange": exchange,
            "symbol": symbol,
            "interval": interval,
            "covered_start_ms": new_start,
            "covered_end_ms": new_end,
            "updated_at": time.time(),
            "rows": int(len(merged)),
        },
    )
    return _slice(merged, start_ms, end_ms)


__all__ = [
    "cached_fetch",
    "cache_dir",
    "cache_enabled",
    "interval_to_ms",
    "OHLCV_COLUMNS",
]
