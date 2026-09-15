"""Canonical instrument symbols and exchange-native conversion.

Exchanges disagree on how a market is written down: OKX wants `BTC-USDT` /
`BTC-USDT-SWAP`, Binance wants the concatenated `BTCUSDT`, a US stock listing is
`BRK-B`. Nothing outside a provider/adapter boundary should ever see those
spellings. Callers work in one canonical notation and convert at the edge.

Canonical notation (`Instrument.canonical()`):
  - crypto spot:   `BASE-QUOTE`      e.g. `BTC-USDT`
  - crypto swap:   `BASE-QUOTE-SWAP` e.g. `BTC-USDT-SWAP`
  - us stock:      `BASE`            e.g. `BRK-B`

`parse_instrument()` is deliberately forgiving about *input* notation so legacy
values already stored in the database (slash form, concatenated form, ccxt-style
`BTC/USDT:USDT`) still resolve, but its output is always the canonical
`Instrument`. `to_native()` is the only thing that may produce an
exchange-specific string, and it is only meant to be called from a provider.

This module is stdlib-only on purpose: it is copied into the backtest and agent
images, and imported by the API and worker, so it must not pull in pandas,
requests, or control_plane.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Exchange(str, Enum):
    OKX = "okx"
    BINANCE = "binance"
    US_STOCK = "us_stock"


class InstrumentKind(str, Enum):
    SPOT = "spot"
    SWAP = "swap"


class InvalidInstrument(ValueError):
    """Raised when a symbol cannot be resolved to base/quote for its exchange."""


# Quote assets, longest first so `USDT` wins over `USD` when stripping a
# concatenated symbol like `BTCUSDT`.
_QUOTES = ("USDT", "USDC", "BUSD", "TUSD", "DAI", "USD", "BTC", "ETH", "EUR", "TRY")

# Tokens that mark a perpetual swap regardless of separator.
_SWAP_SUFFIXES = ("-SWAP", "-PERP", "-PERPETUAL")


@dataclass(frozen=True)
class Instrument:
    exchange: Exchange
    base: str
    quote: str
    kind: InstrumentKind = InstrumentKind.SPOT

    def canonical(self) -> str:
        """Exchange-independent internal notation. Store and compare this."""
        if self.exchange is Exchange.US_STOCK:
            return self.base
        symbol = f"{self.base}-{self.quote}"
        if self.kind is InstrumentKind.SWAP:
            symbol = f"{symbol}-SWAP"
        return symbol

    def to_native(self) -> str:
        """The exchange's own spelling. Only providers/adapters may call this."""
        if self.exchange is Exchange.US_STOCK:
            return self.base
        if self.exchange is Exchange.BINANCE:
            # Spot and USDⓈ-M futures share the concatenated symbol; the venue is
            # carried by `kind` and chosen by the caller, not by this string.
            return f"{self.base}{self.quote}"
        if self.exchange is Exchange.OKX:
            return self.canonical()
        raise InvalidInstrument(f"unsupported_exchange:{self.exchange}")

    def cache_symbol(self) -> str:
        """Cache key. Canonical, so `BTC/USDT` and `BTCUSDT` hit one file."""
        return self.canonical()


def _split_concatenated(symbol: str) -> tuple[str, str]:
    """Split `BTCUSDT` into `("BTC", "USDT")`; bare `BTC` defaults to USDT."""
    for quote in _QUOTES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    return symbol, "USDT"


def _parse_us_stock(raw: str) -> Instrument:
    base = raw
    if base.endswith(".US"):
        base = base[: -len(".US")]
    base = base.replace(".", "-")
    if not base:
        raise InvalidInstrument("symbol is required")
    return Instrument(exchange=Exchange.US_STOCK, base=base, quote="", kind=InstrumentKind.SPOT)


def parse_instrument(
    raw: str,
    *,
    exchange: Exchange | str,
    kind: InstrumentKind | str | None = None,
) -> Instrument:
    """Resolve a user/exchange symbol to a canonical `Instrument`.

    Accepted crypto inputs: `BTC/USDT`, `BTC-USDT`, `BTCUSDT`, `BTC`,
    `BTC-USDT-SWAP`, `BTC/USDT:USDT`. `kind` only decides the spot/swap default
    when the input does not already say so.
    """
    try:
        ex = exchange if isinstance(exchange, Exchange) else Exchange(str(exchange).strip().lower())
    except ValueError as exc:
        raise InvalidInstrument(f"unsupported_exchange:{exchange}") from exc

    text = (raw or "").strip().upper()
    if not text:
        raise InvalidInstrument("symbol is required")

    if ex is Exchange.US_STOCK:
        return _parse_us_stock(text)

    explicit_kind: InstrumentKind | None = None
    # ccxt-style perpetual: `BTC/USDT:USDT`.
    if ":" in text:
        text, _, settle = text.partition(":")
        if settle.strip():
            explicit_kind = InstrumentKind.SWAP
    for suffix in _SWAP_SUFFIXES:
        if text.endswith(suffix):
            explicit_kind = InstrumentKind.SWAP
            text = text[: -len(suffix)]
            break

    if "/" in text:
        parts: list[str] | None = text.split("/")
    elif "-" in text:
        parts = text.split("-")
    else:
        parts = None

    # A separated symbol is exactly BASE-QUOTE. Anything longer (dated futures,
    # a stray prefix/suffix) or with a blank component is a different market and
    # must not be silently coerced into one.
    if parts is not None:
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise InvalidInstrument(f"invalid_symbol:{raw}")
        base, quote = parts[0], parts[1]
    else:
        base, quote = _split_concatenated(text)

    if not base or not quote:
        raise InvalidInstrument(f"invalid_symbol:{raw}")

    if explicit_kind is None:
        if kind is None:
            explicit_kind = InstrumentKind.SPOT
        elif isinstance(kind, InstrumentKind):
            explicit_kind = kind
        else:
            try:
                explicit_kind = InstrumentKind(str(kind).strip().lower())
            except ValueError as exc:
                raise InvalidInstrument(f"invalid_kind:{kind}") from exc

    return Instrument(exchange=ex, base=base, quote=quote, kind=explicit_kind)


def normalize_symbol(
    raw: str,
    *,
    exchange: Exchange | str,
    kind: InstrumentKind | str | None = None,
) -> str:
    """Canonical spelling of `raw`. The convenience used at API boundaries."""
    return parse_instrument(raw, exchange=exchange, kind=kind).canonical()
