"""Crypto-native derivative data fetchers (Funding Rate & Open Interest).

Fetches historical funding rate and open interest metrics from public endpoints:
- OKX: /api/v5/public/funding-rate-history & /api/v5/rubik/stat/contracts/open-interest-volume
- Binance: /fapi/v1/fundingRate & /futures/data/openInterestHist

Provides lookahead-free alignment onto standard OHLCV DataFrames via backward as-of merges.
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import requests

from data.instruments import (
    Exchange,
    InstrumentKind,
    InvalidInstrument,
    parse_instrument,
)

logger = logging.getLogger(__name__)

BINANCE_FAPI_BASE = "https://fapi.binance.com"
OKX_API_BASE = "https://www.okx.com"


# =====================================================================
# Symbol Helpers
# =====================================================================

def _binance_futures_symbol(symbol: str) -> str:
    """Binance USDⓈ-M native symbol (`BTC-USDT` / `BTCUSDT` -> `BTCUSDT`)."""
    return parse_instrument(symbol, exchange=Exchange.BINANCE).to_native()


def _okx_swap_inst_id(inst_id: str) -> str:
    """OKX perpetual instId (`BTC-USDT` -> `BTC-USDT-SWAP`). Funding is swap-only."""
    return parse_instrument(inst_id, exchange=Exchange.OKX, kind=InstrumentKind.SWAP).to_native()


def _extract_base_ccy(symbol_or_inst: str) -> str:
    try:
        return parse_instrument(symbol_or_inst, exchange=Exchange.OKX).base
    except InvalidInstrument:
        return "BTC"


# =====================================================================
# Binance Fetchers
# =====================================================================

def fetch_binance_funding_rates(
    symbol: str,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    limit: int = 1000,
) -> pd.DataFrame:
    """Fetch funding rate history from Binance Futures (fapi.binance.com).

    Returns DataFrame: ['timestamp', 'funding_rate']
    """
    sym = _binance_futures_symbol(symbol)
    params: dict[str, object] = {"symbol": sym, "limit": min(1000, max(1, limit))}
    if start_ms is not None:
        params["startTime"] = int(start_ms)
    if end_ms is not None:
        params["endTime"] = int(end_ms)

    headers = {"User-Agent": "Mozilla/5.0 (compatible; PromptTrading/1.0)"}
    try:
        resp = requests.get(f"{BINANCE_FAPI_BASE}/fapi/v1/fundingRate", params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json() or []
    except Exception as e:
        logger.warning("Failed to fetch Binance funding rates for %s: %s", sym, e)
        return pd.DataFrame(columns=["timestamp", "funding_rate"])

    if not isinstance(data, list) or not data:
        return pd.DataFrame(columns=["timestamp", "funding_rate"])

    records = []
    for item in data:
        if isinstance(item, dict) and "fundingTime" in item and "fundingRate" in item:
            try:
                records.append({
                    "timestamp": int(item["fundingTime"]),
                    "funding_rate": float(item["fundingRate"]),
                })
            except (ValueError, TypeError):
                continue

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def fetch_binance_open_interest(
    symbol: str,
    period: str = "1h",
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    limit: int = 500,
) -> pd.DataFrame:
    """Fetch historical Open Interest from Binance Futures (fapi.binance.com).

    Returns DataFrame: ['timestamp', 'open_interest']
    """
    sym = _binance_futures_symbol(symbol)
    p = period.lower()
    if p not in ("5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"):
        p = "1h"

    params: dict[str, object] = {"symbol": sym, "period": p, "limit": min(500, max(1, limit))}
    if start_ms is not None:
        params["startTime"] = int(start_ms)
    if end_ms is not None:
        params["endTime"] = int(end_ms)

    headers = {"User-Agent": "Mozilla/5.0 (compatible; PromptTrading/1.0)"}
    try:
        resp = requests.get(
            f"{BINANCE_FAPI_BASE}/futures/data/openInterestHist",
            params=params,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json() or []
    except Exception as e:
        logger.warning("Failed to fetch Binance open interest for %s: %s", sym, e)
        return pd.DataFrame(columns=["timestamp", "open_interest"])

    if not isinstance(data, list) or not data:
        return pd.DataFrame(columns=["timestamp", "open_interest"])

    records = []
    for item in data:
        if isinstance(item, dict) and "timestamp" in item:
            try:
                oi_val = float(item.get("sumOpenInterest") or item.get("sumOpenInterestValue") or 0.0)
                records.append({
                    "timestamp": int(item["timestamp"]),
                    "open_interest": oi_val,
                })
            except (ValueError, TypeError):
                continue

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


# =====================================================================
# OKX Fetchers
# =====================================================================

def fetch_okx_funding_rates(
    inst_id: str,
    limit: int = 100,
) -> pd.DataFrame:
    """Fetch funding rate history from OKX public API.

    Returns DataFrame: ['timestamp', 'funding_rate']
    """
    inst = _okx_swap_inst_id(inst_id)
    params: dict[str, object] = {"instId": inst, "limit": min(100, max(1, limit))}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PromptTrading/1.0)"}
    try:
        resp = requests.get(
            f"{OKX_API_BASE}/api/v5/public/funding-rate-history",
            params=params,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json() or {}
        data = payload.get("data") or []
    except Exception as e:
        logger.warning("Failed to fetch OKX funding rates for %s: %s", inst, e)
        return pd.DataFrame(columns=["timestamp", "funding_rate"])

    records = []
    for item in data:
        if isinstance(item, dict) and "fundingTime" in item and "fundingRate" in item:
            try:
                records.append({
                    "timestamp": int(item["fundingTime"]),
                    "funding_rate": float(item["fundingRate"]),
                })
            except (ValueError, TypeError):
                continue

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def fetch_okx_open_interest(
    symbol_or_ccy: str,
    period: str = "1H",
) -> pd.DataFrame:
    """Fetch historical Open Interest from OKX Rubik statistics API.

    Returns DataFrame: ['timestamp', 'open_interest']
    """
    ccy = _extract_base_ccy(symbol_or_ccy)
    params: dict[str, object] = {"ccy": ccy, "period": period}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PromptTrading/1.0)"}
    try:
        resp = requests.get(
            f"{OKX_API_BASE}/api/v5/rubik/stat/contracts/open-interest-volume",
            params=params,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json() or {}
        data = payload.get("data") or []
    except Exception as e:
        logger.warning("Failed to fetch OKX open interest for %s: %s", ccy, e)
        return pd.DataFrame(columns=["timestamp", "open_interest"])

    records = []
    for row in data:
        # Format: [timestamp, oi_usd, vol_usd]
        if isinstance(row, list) and len(row) >= 2:
            try:
                records.append({
                    "timestamp": int(row[0]),
                    "open_interest": float(row[1]),
                })
            except (ValueError, TypeError):
                continue

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


# =====================================================================
# Alignment onto OHLCV (Zero Lookahead)
# =====================================================================

def align_derivatives_onto_ohlcv(
    ohlcv_df: pd.DataFrame,
    funding_df: Optional[pd.DataFrame] = None,
    oi_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Merge derivative series onto OHLCV DataFrame with strict lookahead prevention.

    Uses `pd.merge_asof(direction='backward')` so at bar open timestamp T,
    only derivative information timestamped <= T is used.
    """
    if ohlcv_df is None or ohlcv_df.empty:
        return ohlcv_df

    df = ohlcv_df.copy()
    if not pd.api.types.is_numeric_dtype(df["timestamp"]):
        df["timestamp"] = df["timestamp"].astype("int64")

    # 1. Align Funding Rate
    if funding_df is not None and not funding_df.empty and "funding_rate" in funding_df.columns:
        f_clean = funding_df[["timestamp", "funding_rate"]].dropna().copy()
        f_clean["timestamp"] = f_clean["timestamp"].astype("int64")
        f_clean = f_clean.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        df = pd.merge_asof(df, f_clean, on="timestamp", direction="backward")
    elif "funding_rate" not in df.columns:
        df["funding_rate"] = 0.0

    # 2. Align Open Interest
    if oi_df is not None and not oi_df.empty and "open_interest" in oi_df.columns:
        oi_clean = oi_df[["timestamp", "open_interest"]].dropna().copy()
        oi_clean["timestamp"] = oi_clean["timestamp"].astype("int64")
        oi_clean = oi_clean.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        df = pd.merge_asof(df, oi_clean, on="timestamp", direction="backward")
    elif "open_interest" not in df.columns:
        df["open_interest"] = 0.0

    # Forward fill trailing values and backfill warmup period
    df["funding_rate"] = df["funding_rate"].ffill().bfill().fillna(0.0)
    df["open_interest"] = df["open_interest"].ffill().bfill().fillna(0.0)

    return df
