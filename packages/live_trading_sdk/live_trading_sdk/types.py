"""Core dataclasses shared across the live trading SDK."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Bar:
    """Normalized OHLCV bar.

    Timestamp is expressed in milliseconds since epoch (UTC).
    """

    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str | None = None
    interval: str | None = None


@dataclass(slots=True)
class StrategyContext:
    """Metadata about the running live session."""

    exchange: str
    symbol: str
    interval: str
    params: dict[str, Any]
    max_position_pct: float
    stop_loss_pct: float
    symbols: list[str] | None = None
    intervals: list[str] | None = None
