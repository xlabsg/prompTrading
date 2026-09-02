from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import io
import os
import time

import pandas as pd
import requests

from data.cache import cached_fetch


YFINANCE_INTERVAL = "1d"
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
    Bars are served through the shared market-data cache, so a repeated request
    for an already-downloaded range performs no network call.
    """
    symbol = _normalize_symbol(req.symbol)

    provider = os.getenv("US_STOCK_PROVIDER", "yfinance").strip().lower()
    fallback_provider = os.getenv("US_STOCK_FALLBACK_PROVIDER", "stooq").strip().lower()
    allow_fallback = (os.getenv("US_STOCK_FALLBACK", "1") or "").strip().lower() not in ("0", "false", "no")

    def _download(start_ms: int | None, end_ms: int | None) -> pd.DataFrame:
        window = USStockDailyRequest(symbol=req.symbol, start_ms=start_ms, end_ms=end_ms)

        start_date: datetime | None = None
        end_date: datetime | None = None
        if start_ms is not None:
            start_date = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).date()
        if end_ms is not None:
            end_date = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc).date() + timedelta(days=1)

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
                # Surfaced to the cache layer, which falls back to stored bars.
                raise ValueError("us_stock_rate_limited") from last_err
            return _finalize_ohlcv(df_local, use_adj_close=True, req=window)

        def try_stooq() -> pd.DataFrame:
            df_local = _download_with_stooq(symbol)
            return _finalize_ohlcv(df_local, use_adj_close=False, req=window)

        if provider == "stooq":
            return try_stooq()

        try:
            df_out = try_yfinance()
        except ValueError as e:
            if allow_fallback and fallback_provider == "stooq" and str(e) == "us_stock_rate_limited":
                return try_stooq()
            raise
        if len(df_out) < 3 and allow_fallback and fallback_provider == "stooq":
            df_out = try_stooq()
        return df_out

    df_out = cached_fetch(
        exchange="us_stock",
        symbol=symbol,
        interval=YFINANCE_INTERVAL,
        start_ms=req.start_ms,
        end_ms=req.end_ms,
        fetch=_download,
        fallback_to_stale_on_error=True,
    )

    if df_out is None or len(df_out) < 3:
        raise ValueError("us_stock_no_data_or_rate_limited")
    return df_out
