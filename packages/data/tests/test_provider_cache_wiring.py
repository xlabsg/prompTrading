"""Each provider's public fetch must route through the shared cache."""

from __future__ import annotations

import pandas as pd
import pytest

from data import binance, okx

HOUR_MS = 3_600_000


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_DATA_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("MARKET_DATA_CACHE_ENABLED", raising=False)


def _bars(start_ms: int, end_ms: int) -> pd.DataFrame:
    ts = list(range(start_ms, end_ms + 1, HOUR_MS))
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": [1.0] * len(ts),
            "high": [2.0] * len(ts),
            "low": [0.5] * len(ts),
            "close": [1.5] * len(ts),
            "volume": [10.0] * len(ts),
        }
    )


def test_okx_fetch_candles_is_cached(monkeypatch):
    calls = []

    def fake(req):
        calls.append(req)
        return _bars(req.start_ms, req.end_ms)

    monkeypatch.setattr(okx, "_fetch_candles_uncached", fake)
    req = okx.CandlesRequest(
        inst_id="BTC-USDT-SWAP", bar="1H",
        start_ms=1_000 * HOUR_MS, end_ms=1_050 * HOUR_MS, limit=1000,
    )

    first = okx.fetch_candles(req)
    assert len(calls) == 1
    assert len(first) == 51

    second = okx.fetch_candles(req)
    assert len(calls) == 1, "second identical OKX request must hit the cache"
    pd.testing.assert_frame_equal(first, second)


def test_okx_limit_applied_after_cache(monkeypatch):
    monkeypatch.setattr(okx, "_fetch_candles_uncached", lambda r: _bars(r.start_ms, r.end_ms))
    base = dict(inst_id="BTC-USDT", bar="1H", start_ms=1_000 * HOUR_MS, end_ms=1_050 * HOUR_MS)

    full = okx.fetch_candles(okx.CandlesRequest(**base, limit=1000))
    assert len(full) == 51

    capped = okx.fetch_candles(okx.CandlesRequest(**base, limit=10))
    assert len(capped) == 10, "limit must trim the cached slice"
    assert capped["timestamp"].max() == full["timestamp"].max()


def test_binance_fetch_klines_is_cached(monkeypatch):
    calls = []

    def fake(req):
        calls.append(req)
        return _bars(req.start_ms, req.end_ms)

    monkeypatch.setattr(binance, "_fetch_klines_uncached", fake)
    req = binance.KlinesRequest(
        symbol="BTCUSDT", interval="1h",
        start_ms=1_000 * HOUR_MS, end_ms=1_050 * HOUR_MS, limit=1000,
    )

    first = binance.fetch_klines(req)
    assert len(calls) == 1
    assert len(first) == 51

    binance.fetch_klines(req)
    assert len(calls) == 1, "second identical Binance request must hit the cache"
