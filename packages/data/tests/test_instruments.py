import pytest

from data.instruments import (
    Exchange,
    InstrumentKind,
    InvalidInstrument,
    normalize_symbol,
    parse_instrument,
)


@pytest.mark.parametrize(
    "raw,exchange,kind,canonical,native",
    [
        # OKX — the legacy slash form that used to reach the API verbatim and 51001.
        ("BTC/USDT", Exchange.OKX, None, "BTC-USDT", "BTC-USDT"),
        ("btc/usdt", Exchange.OKX, None, "BTC-USDT", "BTC-USDT"),
        ("BTC-USDT", Exchange.OKX, None, "BTC-USDT", "BTC-USDT"),
        ("BTC-USDT-SWAP", Exchange.OKX, None, "BTC-USDT-SWAP", "BTC-USDT-SWAP"),
        ("btc-usdt-swap", Exchange.OKX, None, "BTC-USDT-SWAP", "BTC-USDT-SWAP"),
        ("BTC/USDT:USDT", Exchange.OKX, None, "BTC-USDT-SWAP", "BTC-USDT-SWAP"),
        ("BTCUSDT", Exchange.OKX, None, "BTC-USDT", "BTC-USDT"),
        # Bare base defaults to /USDT spot rather than an unparseable instId.
        ("BTC", Exchange.OKX, None, "BTC-USDT", "BTC-USDT"),
        # Explicit kind upgrades a slash/concatenated symbol.
        ("BTC/USDT", Exchange.OKX, InstrumentKind.SWAP, "BTC-USDT-SWAP", "BTC-USDT-SWAP"),
        # Binance — concatenated native, canonical stays dashed.
        ("BTCUSDT", Exchange.BINANCE, None, "BTC-USDT", "BTCUSDT"),
        ("BTC-USDT", Exchange.BINANCE, None, "BTC-USDT", "BTCUSDT"),
        ("ETH/USDT", Exchange.BINANCE, None, "ETH-USDT", "ETHUSDT"),
        ("sol-usdt", Exchange.BINANCE, None, "SOL-USDT", "SOLUSDT"),
        ("BTC-USDT-SWAP", Exchange.BINANCE, None, "BTC-USDT-SWAP", "BTCUSDT"),
        # US stock.
        ("AAPL", Exchange.US_STOCK, None, "AAPL", "AAPL"),
        ("aapl.us", Exchange.US_STOCK, None, "AAPL", "AAPL"),
        ("brk.b", Exchange.US_STOCK, None, "BRK-B", "BRK-B"),
    ],
)
def test_parse_and_convert(raw, exchange, kind, canonical, native):
    instrument = parse_instrument(raw, exchange=exchange, kind=kind)
    assert instrument.canonical() == canonical
    assert instrument.to_native() == native


def test_normalize_symbol_is_canonical():
    assert normalize_symbol("BTC/USDT", exchange="okx") == "BTC-USDT"
    assert normalize_symbol("btcusdt", exchange="binance") == "BTC-USDT"


@pytest.mark.parametrize("raw", ["", "   ", "/", "-"])
def test_blank_symbol_rejected(raw):
    with pytest.raises(InvalidInstrument):
        parse_instrument(raw, exchange=Exchange.OKX)


def test_unknown_exchange_rejected():
    with pytest.raises(InvalidInstrument):
        parse_instrument("BTC-USDT", exchange="nasdaq")


def test_cache_symbol_is_canonical_so_variants_collapse():
    forms = ["BTC/USDT", "BTC-USDT", "BTCUSDT", "btc-usdt"]
    keys = {parse_instrument(f, exchange=Exchange.OKX).cache_symbol() for f in forms}
    assert keys == {"BTC-USDT"}
