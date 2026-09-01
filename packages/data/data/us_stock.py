from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import io
import json
import os
import time

import pandas as pd
import requests


YFINANCE_INTERVAL = "1d"
DEFAULT_CACHE_DIR = "/workspaces/us_stock_cache"
DEFAULT_CACHE_TTL_DAYS = 7
DEFAULT_MAX_RETRIES = 5
DEFAULT_RATE_LIMIT_SLEEP_S = 10.0
STOOQ_BASE_URL = "https://stooq.com"
STOOQ_DAILY_INTERVAL = "d"


@dataclass(frozen=True)
class USStockDailyRequest:
    symbol: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None


def _normalize_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s:
        raise ValueError("symbol is required")
    if s.endswith(".US"):
        s = s[:-3]
    s = s.replace(".", "-")
    return s


def _cache_dir() -> str:
    return os.getenv("US_STOCK_CACHE_DIR", DEFAULT_CACHE_DIR)


def _cache_ttl_days() -> int:
    raw = os.getenv("US_STOCK_CACHE_TTL_DAYS", "")
    if not raw:
        return DEFAULT_CACHE_TTL_DAYS
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_CACHE_TTL_DAYS


def _max_retries() -> int:
    raw = os.getenv("US_STOCK_MAX_RETRIES", "")
    if not raw:
        return DEFAULT_MAX_RETRIES
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_RETRIES


def _rate_limit_sleep_s() -> float:
    raw = os.getenv("US_STOCK_RATE_LIMIT_SLEEP_S", "")
    if not raw:
        return DEFAULT_RATE_LIMIT_SLEEP_S
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_RATE_LIMIT_SLEEP_S


def _cache_paths(symbol: str) -> tuple[str, str]:
    safe = symbol.replace("/", "_").replace(":", "_")
    base = _cache_dir()
    return os.path.join(base, f"{safe}.parquet"), os.path.join(base, f"{safe}.meta.json")


def _read_cache(symbol: str) -> Optional[pd.DataFrame]:
    data_path, meta_path = _cache_paths(symbol)
    if not os.path.exists(data_path) or not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        ttl_days = _cache_ttl_days()
        if ttl_days > 0:
            updated_at = float(meta.get("updated_at", 0))
            if updated_at and (time.time() - updated_at) > ttl_days * 86400:
                return None
        df = pd.read_parquet(data_path)
        return df
    except Exception:
        return None


def _write_cache(symbol: str, df: pd.DataFrame) -> None:
    data_path, meta_path = _cache_paths(symbol)
    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    df.to_parquet(data_path, index=False)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"updated_at": time.time()}, f)


def _is_rate_limit_error(err: Exception) -> bool:
    msg = str(err).lower()
    return "rate limit" in msg or "too many requests" in msg or "ratelimit" in msg


def _download_with_yfinance(symbol: str, *, start_date: datetime | None, end_date: datetime | None) -> pd.DataFrame | None:
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:
        raise RuntimeError("yfinance_not_installed") from exc

    download_kwargs = {
        "interval": YFINANCE_INTERVAL,
        "auto_adjust": False,
        "actions": False,
        "progress": False,
        "threads": False,
        "group_by": "column",
    }
    if start_date or end_date:
        if start_date:
            download_kwargs["start"] = start_date
        if end_date:
            download_kwargs["end"] = end_date
    else:
        download_kwargs["period"] = "max"

    df = yf.download(symbol, **download_kwargs)
    if df is not None and not df.empty:
        return df

    history_kwargs = {
        "interval": YFINANCE_INTERVAL,
        "auto_adjust": False,
        "actions": False,
    }
    if start_date or end_date:
        if start_date:
            history_kwargs["start"] = start_date
        if end_date:
            history_kwargs["end"] = end_date
    else:
        history_kwargs["period"] = "max"

    ticker = yf.Ticker(symbol)
    df = ticker.history(**history_kwargs)
    return df


def _download_with_stooq(symbol: str) -> pd.DataFrame:
    stooq_symbol = symbol.lower()
    stooq_symbol = stooq_symbol.replace(".", "-")
    params = {
        "s": f"{stooq_symbol}.us",
        "i": STOOQ_DAILY_INTERVAL,
    }
    resp = requests.get(f"{STOOQ_BASE_URL}/q/d/l/", params=params, timeout=30)
    resp.raise_for_status()

    raw = resp.text.strip()
    if not raw:
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(raw))
    return df


def _finalize_ohlcv(
    df: pd.DataFrame,
    *,
    use_adj_close: bool,
    req: USStockDailyRequest,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(-1, axis=1)

    if "Date" in df.columns:
        required_cols = {"Date", "Open", "High", "Low", "Close", "Volume"}
        if not required_cols.issubset(set(df.columns)):
            raise ValueError("stooq_invalid_response")
        ts = pd.to_datetime(df["Date"], utc=True, errors="coerce")
        open_px = df["Open"].astype(float)
        high_px = df["High"].astype(float)
        low_px = df["Low"].astype(float)
        close_px = df["Close"].astype(float)
        volume = df["Volume"].astype(float)
    else:
        required_cols = {"Open", "High", "Low", "Close", "Volume"}
        if not required_cols.issubset(set(df.columns)):
            raise ValueError("yfinance_invalid_response")
        adj_factor = pd.Series(1.0, index=df.index)
        if use_adj_close and "Adj Close" in df.columns:
            close = df["Close"].replace(0, pd.NA)
            adj_factor = (df["Adj Close"] / close).fillna(1.0).replace([float("inf"), float("-inf")], 1.0)
        open_px = (df["Open"] * adj_factor).astype(float)
        high_px = (df["High"] * adj_factor).astype(float)
        low_px = (df["Low"] * adj_factor).astype(float)
        close_px = (df["Close"] * adj_factor).astype(float)
        volume = df["Volume"].astype(float)

        ts_index = pd.to_datetime(df.index, errors="coerce")
        if getattr(ts_index, "tz", None) is None:
            ts = ts_index.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")
        else:
            ts = ts_index.tz_convert("UTC")

    df_out = pd.DataFrame(
        {
            "timestamp": (ts.astype("int64") // 1_000_000).astype("int64"),
            "open": open_px,
            "high": high_px,
            "low": low_px,
            "close": close_px,
            "volume": volume,
        }
    )

    if req.start_ms is not None:
        df_out = df_out[df_out["timestamp"] >= int(req.start_ms)]
    if req.end_ms is not None:
        df_out = df_out[df_out["timestamp"] <= int(req.end_ms)]

    df_out = df_out.dropna(subset=["timestamp", "open", "high", "low", "close"])
    df_out = df_out[df_out["close"] > 0]
    df_out = df_out.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    return df_out.reset_index(drop=True)


def fetch_us_stock_daily(req: USStockDailyRequest) -> pd.DataFrame:
    """Fetch US stock daily OHLCV data from Yahoo Finance (yfinance).

    Returns DataFrame with columns: timestamp (ms), open, high, low, close, volume.
    """
    symbol = _normalize_symbol(req.symbol)

    start_date: datetime | None = None
    end_date: datetime | None = None
    if req.start_ms is not None:
        start_date = datetime.fromtimestamp(req.start_ms / 1000, tz=timezone.utc).date()
    if req.end_ms is not None:
        end_date = datetime.fromtimestamp(req.end_ms / 1000, tz=timezone.utc).date() + timedelta(days=1)

    provider = os.getenv("US_STOCK_PROVIDER", "yfinance").strip().lower()
    fallback_provider = os.getenv("US_STOCK_FALLBACK_PROVIDER", "stooq").strip().lower()
    allow_fallback = (os.getenv("US_STOCK_FALLBACK", "1") or "").strip().lower() not in ("0", "false", "no")

    cache_df = _read_cache(symbol)
    if cache_df is not None and not cache_df.empty:
        if req.start_ms is None and req.end_ms is None:
            return cache_df.copy()
        filtered = cache_df.copy()
        if req.start_ms is not None:
            filtered = filtered[filtered["timestamp"] >= int(req.start_ms)]
        if req.end_ms is not None:
            filtered = filtered[filtered["timestamp"] <= int(req.end_ms)]
        if len(filtered) >= 3:
            return filtered.reset_index(drop=True)

    def try_yfinance() -> pd.DataFrame:
        df_local = None
        last_err: Exception | None = None
        max_retries = _max_retries()
        rate_limit_sleep_s = _rate_limit_sleep_s()
        for attempt in range(max_retries):
            try:
                df_local = _download_with_yfinance(symbol, start_date=start_date, end_date=end_date)
                last_err = None
                break
            except Exception as e:
                last_err = e
                if _is_rate_limit_error(e):
                    time.sleep(rate_limit_sleep_s * (attempt + 1))
                    continue
                break
        if last_err is not None and _is_rate_limit_error(last_err):
            if cache_df is not None and not cache_df.empty:
                return cache_df.copy()
            raise ValueError("us_stock_rate_limited") from last_err
        return _finalize_ohlcv(df_local, use_adj_close=True, req=req)

    def try_stooq() -> pd.DataFrame:
        df_local = _download_with_stooq(symbol)
        return _finalize_ohlcv(df_local, use_adj_close=False, req=req)

    if provider == "stooq":
        df_out = try_stooq()
    else:
        try:
            df_out = try_yfinance()
        except ValueError as e:
            if allow_fallback and fallback_provider == "stooq" and str(e) == "us_stock_rate_limited":
                df_out = try_stooq()
            else:
                raise
        if (df_out is None or len(df_out) < 3) and allow_fallback and fallback_provider == "stooq":
            df_out = try_stooq()

    if df_out is None or len(df_out) < 3:
        raise ValueError("us_stock_no_data_or_rate_limited")

    if len(df_out) >= 3:
        _write_cache(symbol, df_out)
    return df_out
