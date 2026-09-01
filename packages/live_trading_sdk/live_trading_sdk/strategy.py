"""Strategy-side interfaces for real-time execution."""

from __future__ import annotations

from typing import Protocol, runtime_checkable, Any

import pandas as pd

from .types import Bar, StrategyContext


@runtime_checkable
class Broker(Protocol):
    """Abstraction injected by the trading engine.

    Strategy authors interact with the broker to express intent instead of
    calling exchange APIs directly.
    """

    def set_target_allocation(self, target: float, *, reason: str | None = None) -> None:
        """Request the portfolio to move toward `target` exposure.

        `target` is normalized to the range [-1, 1], where:
        -1 = max short exposure, 0 = flat/neutral, 1 = max long exposure.
        """

    def market_order(self, side: str, size: float, *, reason: str | None = None) -> None:
        """Submit an immediate-or-cancel style market order.

        `side` should be either "buy" or "sell". Implementations may round
        `size` to comply with exchange lot sizes.
        """

    def current_position(self) -> float:
        """Return the current net position size in base units."""

    def last_price(self) -> float:
        """Return the last traded price used for sizing decisions."""


@runtime_checkable
class LiveStrategy(Protocol):
    """Optional interface for strategies that want direct live hooks."""

    def initialize(self, context: StrategyContext) -> None:
        """Called once before live execution begins."""

    def on_bar(self, bar: Bar, history: pd.DataFrame, broker: Broker) -> None:
        """Called each time the engine ingests a fresh OHLCV bar."""

    def on_error(self, error: Exception, broker: Broker) -> None:
        """Optional error callback (default implementation may ignore)."""
