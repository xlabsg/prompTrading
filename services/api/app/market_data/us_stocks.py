from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

NASDAQ_API_URL = "https://api.nasdaq.com/api/screener/stocks"
CACHE_TTL_S = 24 * 60 * 60
CACHE_FILENAME = "us_stock_nasdaq_symbols.json"
DEFAULT_SESSION = "09:30-16:00 America/New_York"


def _cache_path() -> str:
    return os.path.join("/tmp", CACHE_FILENAME)


def _load_cache() -> dict[str, Any] | None:
    path = _cache_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(payload: dict[str, Any]) -> None:
    path = _cache_path()
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp_path, path)


def _fetch_nasdaq_rows() -> list[dict[str, Any]]:
    params = {
        "tableonly": "true",
        "download": "true",
        "limit": "0",
        "offset": "0",
        "exchange": "NASDAQ",
    }
    headers = {
        "accept": "application/json, text/plain, */*",
        "user-agent": "Mozilla/5.0",
        "origin": "https://www.nasdaq.com",
        "referer": "https://www.nasdaq.com/",
    }
    resp = requests.get(NASDAQ_API_URL, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    payload = resp.json() or {}
    rows = ((payload.get("data") or {}).get("rows") or [])
    if not isinstance(rows, list):
        raise ValueError("nasdaq_invalid_response")
    return rows


def load_nasdaq_symbols(*, force_refresh: bool = False) -> list[dict[str, str]]:
    now = int(time.time())
    cache = _load_cache()
    if cache and not force_refresh:
        updated_at = int(cache.get("updated_at", 0))
        if updated_at and now - updated_at < CACHE_TTL_S:
            symbols = cache.get("symbols") or []
            if isinstance(symbols, list):
                return symbols

    rows = _fetch_nasdaq_rows()
    symbols: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = (row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        name = (row.get("name") or "").strip() or symbol
        sector = (row.get("sector") or "").strip() or "Unknown"
        symbols.append(
            {
                "symbol": symbol,
                "name": name,
                "sector": sector,
                "exchange": "NASDAQ",
                "session": DEFAULT_SESSION,
            }
        )

    _write_cache({"updated_at": now, "symbols": symbols})
    return symbols
