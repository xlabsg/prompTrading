from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.routers.backtests import _create_dataset
from app.schemas import DatasetRequest


def _make(exchange: str, symbol: str, interval: str | None = None):
    if interval is None:
        interval = "1d" if exchange == "us_stock" else "1h"
    return _create_dataset(MagicMock(), DatasetRequest(exchange=exchange, symbol=symbol, interval=interval))


def test_okx_slash_symbol_is_canonicalized_before_storage():
    # The regression: `okx:BTC/USDT` used to reach the container as an instId.
    ds = _make("okx", "BTC/USDT")
    assert ds.symbol == "BTC-USDT"
    assert ds.exchange == "okx"


@pytest.mark.parametrize(
    "exchange,raw,canonical",
    [
        ("okx", "BTC-USDT-SWAP", "BTC-USDT-SWAP"),
        ("okx", "btc/usdt:usdt", "BTC-USDT-SWAP"),
        ("okx", "BTCUSDT", "BTC-USDT"),
        ("binance", "BTCUSDT", "BTC-USDT"),
        ("us_stock", "aapl.us", "AAPL"),
        ("us_stock", "brk.b", "BRK-B"),
    ],
)
def test_symbols_are_stored_canonical(exchange, raw, canonical):
    assert _make(exchange, raw).symbol == canonical


def test_unparseable_symbol_fails_fast():
    with pytest.raises(HTTPException) as exc:
        _make("okx", "/")
    assert exc.value.status_code == 400
    assert exc.value.detail.startswith("invalid_symbol:")


def test_unsupported_exchange_rejected():
    with pytest.raises(HTTPException) as exc:
        _make("nasdaq", "AAPL")
    assert exc.value.detail == "unsupported_exchange"


def test_blank_symbol_rejected():
    with pytest.raises(HTTPException) as exc:
        _make("okx", "   ")
    assert exc.value.detail == "missing_symbol"
