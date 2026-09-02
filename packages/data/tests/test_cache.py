"""Tests for the shared OHLCV cache."""

from __future__ import annotations

import time

import pandas as pd
import pytest

from data.cache import cached_fetch, interval_to_ms

HOUR_MS = 3_600_000


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_DATA_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("MARKET_DATA_CACHE_ENABLED", raising=False)
    monkeypatch.delenv("MARKET_DATA_CACHE_TTL_S", raising=False)
    monkeypatch.delenv("US_STOCK_CACHE_DIR", raising=False)


def make_bars(start_ms: int, end_ms: int, step_ms: int = HOUR_MS) -> pd.DataFrame:
    ts = list(range(start_ms, end_ms + 1, step_ms))
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": [float(t) for t in ts],
            "high": [float(t) + 2 for t in ts],
            "low": [float(t) - 2 for t in ts],
            "close": [float(t) + 1 for t in ts],
            "volume": [1.0] * len(ts),
        }
    )


class Recorder:
    """Fetch callable that records the ranges it was asked for."""

    def __init__(self, step_ms: int = HOUR_MS, fail: bool = False):
        self.calls: list[tuple[int | None, int | None]] = []
        self.step_ms = step_ms
        self.fail = fail

    def __call__(self, start_ms, end_ms):
        self.calls.append((start_ms, end_ms))
        if self.fail:
            raise RuntimeError("upstream_down")
        lo = start_ms if start_ms is not None else 0
        hi = end_ms if end_ms is not None else lo + 10 * self.step_ms
        return make_bars(lo, hi, self.step_ms)


def fetch_range(fetch, start_ms, end_ms, *, exchange="okx", symbol="BTC-USDT", interval="1h", **kw):
    return cached_fetch(
        exchange=exchange,
        symbol=symbol,
        interval=interval,
        start_ms=start_ms,
        end_ms=end_ms,
        fetch=fetch,
        interval_ms=HOUR_MS,
        **kw,
    )


def test_interval_to_ms():
    assert interval_to_ms("1h") == HOUR_MS
    assert interval_to_ms("15m") == 15 * 60_000
    assert interval_to_ms("1D") == 86_400_000
    assert interval_to_ms("1H") == HOUR_MS
    assert interval_to_ms("bogus") is None
    assert interval_to_ms("0h") is None
    assert interval_to_ms("") is None


def test_second_identical_request_makes_no_network_call():
    """The core win: an agent re-running the same backtest hits zero upstream calls."""
    rec = Recorder()
    start, end = 1_000 * HOUR_MS, 1_050 * HOUR_MS

    first = fetch_range(rec, start, end)
    assert len(rec.calls) == 1
    assert len(first) == 51

    second = fetch_range(rec, start, end)
    assert len(rec.calls) == 1, "cached range must not re-fetch"
    pd.testing.assert_frame_equal(first, second)


def test_subrange_served_from_cache():
    rec = Recorder()
    start, end = 1_000 * HOUR_MS, 1_050 * HOUR_MS
    fetch_range(rec, start, end)

    narrow = fetch_range(rec, 1_010 * HOUR_MS, 1_020 * HOUR_MS)
    assert len(rec.calls) == 1
    assert narrow["timestamp"].min() == 1_010 * HOUR_MS
    assert narrow["timestamp"].max() == 1_020 * HOUR_MS


def test_extending_forward_fetches_only_the_gap():
    rec = Recorder()
    start = 1_000 * HOUR_MS
    fetch_range(rec, start, 1_050 * HOUR_MS)

    extended = fetch_range(rec, start, 1_060 * HOUR_MS)
    assert len(rec.calls) == 2
    gap_start, gap_end = rec.calls[1]
    # Refetches from the last cached bar so the incomplete trailing bar is corrected.
    assert gap_start >= 1_049 * HOUR_MS
    assert gap_end == 1_060 * HOUR_MS
    assert extended["timestamp"].min() == start
    assert extended["timestamp"].max() == 1_060 * HOUR_MS
    assert extended["timestamp"].is_monotonic_increasing
    assert not extended["timestamp"].duplicated().any()


def test_earlier_start_refetches():
    """Cache covering [t1, t2] must not silently claim to cover an earlier start."""
    rec = Recorder()
    fetch_range(rec, 1_000 * HOUR_MS, 1_050 * HOUR_MS)

    wider = fetch_range(rec, 900 * HOUR_MS, 1_050 * HOUR_MS)
    assert len(rec.calls) == 2
    assert wider["timestamp"].min() == 900 * HOUR_MS
    assert wider["timestamp"].max() == 1_050 * HOUR_MS


def test_cache_key_separates_symbol_interval_exchange():
    rec = Recorder()
    start, end = 1_000 * HOUR_MS, 1_010 * HOUR_MS

    fetch_range(rec, start, end, symbol="BTC-USDT")
    fetch_range(rec, start, end, symbol="ETH-USDT")
    fetch_range(rec, start, end, symbol="BTC-USDT", interval="4h")
    fetch_range(rec, start, end, symbol="BTC-USDT", exchange="binance")
    assert len(rec.calls) == 4, "each key must be cached independently"

    fetch_range(rec, start, end, symbol="BTC-USDT")
    assert len(rec.calls) == 4


def test_disabled_cache_always_fetches(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_CACHE_ENABLED", "0")
    rec = Recorder()
    start, end = 1_000 * HOUR_MS, 1_010 * HOUR_MS
    fetch_range(rec, start, end)
    fetch_range(rec, start, end)
    assert len(rec.calls) == 2


def test_stale_fallback_serves_cached_bars_on_upstream_error():
    rec = Recorder()
    start, end = 1_000 * HOUR_MS, 1_050 * HOUR_MS
    fetch_range(rec, start, end)

    broken = Recorder(fail=True)
    out = fetch_range(broken, 900 * HOUR_MS, 1_050 * HOUR_MS, fallback_to_stale_on_error=True)
    assert len(out) == 51, "must degrade to stored bars rather than raise"


def test_upstream_error_propagates_without_fallback():
    broken = Recorder(fail=True)
    with pytest.raises(RuntimeError, match="upstream_down"):
        fetch_range(broken, 1_000 * HOUR_MS, 1_010 * HOUR_MS)


def test_trailing_edge_refreshes_after_ttl(monkeypatch):
    """A range ending ~now must re-check upstream once the TTL lapses."""
    monkeypatch.setenv("MARKET_DATA_CACHE_TTL_S", "0")
    rec = Recorder()
    now_ms = int(time.time() * 1000)
    start = now_ms - 50 * HOUR_MS

    fetch_range(rec, start, None)
    assert len(rec.calls) == 1

    fetch_range(rec, start, None)
    assert len(rec.calls) == 2, "trailing-edge request must refresh once stale"


def test_historical_range_never_refreshes(monkeypatch):
    """A fully historical range is immutable, so TTL must not trigger a refetch."""
    monkeypatch.setenv("MARKET_DATA_CACHE_TTL_S", "0")
    rec = Recorder()
    start, end = 1_000 * HOUR_MS, 1_050 * HOUR_MS

    fetch_range(rec, start, end)
    fetch_range(rec, start, end)
    assert len(rec.calls) == 1


def test_corrupt_cache_falls_back_to_fetch(tmp_path):
    rec = Recorder()
    start, end = 1_000 * HOUR_MS, 1_010 * HOUR_MS
    fetch_range(rec, start, end)

    for p in tmp_path.iterdir():
        p.write_text("garbage")

    out = fetch_range(rec, start, end)
    assert len(rec.calls) == 2, "unreadable cache must degrade to a fetch"
    assert len(out) == 11


def test_open_ended_start_covers_later_bounded_request():
    rec = Recorder()
    fetch_range(rec, None, 1_050 * HOUR_MS)
    assert len(rec.calls) == 1

    fetch_range(rec, 1_000 * HOUR_MS, 1_050 * HOUR_MS)
    assert len(rec.calls) == 1, "open-ended start covers any bounded start"


def test_bounded_cache_does_not_claim_open_ended_start():
    rec = Recorder()
    fetch_range(rec, 1_000 * HOUR_MS, 1_050 * HOUR_MS)
    fetch_range(rec, None, 1_050 * HOUR_MS)
    assert len(rec.calls) == 2


def test_write_failure_does_not_break_caller(monkeypatch):
    """Caching is an optimisation: an unwritable cache must still return data."""

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", boom)

    rec = Recorder()
    out = fetch_range(rec, 1_000 * HOUR_MS, 1_010 * HOUR_MS)
    assert len(out) == 11

    # Nothing was persisted, so the next call goes upstream again.
    out2 = fetch_range(rec, 1_000 * HOUR_MS, 1_010 * HOUR_MS)
    assert len(rec.calls) == 2
    assert len(out2) == 11


def test_merge_prefers_fresh_trailing_bar():
    """Refetching the trailing bar must overwrite the earlier incomplete copy."""
    start, end = 1_000 * HOUR_MS, 1_005 * HOUR_MS
    rec = Recorder()
    fetch_range(rec, start, end)

    def corrected(start_ms, end_ms):
        df = make_bars(start_ms, end_ms)
        df["close"] = 999.0
        return df

    out = fetch_range(corrected, start, 1_010 * HOUR_MS)
    assert out.loc[out["timestamp"] == 1_005 * HOUR_MS, "close"].iloc[0] == 999.0
    assert out.loc[out["timestamp"] == 1_000 * HOUR_MS, "close"].iloc[0] == float(start) + 1
