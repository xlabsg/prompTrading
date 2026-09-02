"""Base class for template strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import pandas as pd

try:
    from live_trading_sdk import LiveStrategy, StrategyContext
except ImportError:
    LiveStrategy = None
    StrategyContext = None


@dataclass
class TemplateMetadata:
    """Metadata for a strategy template."""

    name: str
    description: str
    version: str = "1.0.0"
    author: str = "PrompTrading"
    tags: list[str] = field(default_factory=list)
    risk_level: str = "medium"  # low, medium, high
    trading_frequency: str = "intraday"  # low_frequency, intraday, high_frequency
    complexity_score: int = 3  # 1-5 scale
    min_capital_usdt: float = 100.0
    supported_exchanges: list[str] = field(default_factory=lambda: ["okx"])
    supported_symbols: list[str] = field(default_factory=list)  # Empty = all

    # Performance summary (populated after backtesting)
    backtest_summary: dict[str, Any] = field(default_factory=dict)


class BaseTemplateStrategy:
    """Base class for all template strategies.

    Template strategies should:
    1. Inherit from this class
    2. Implement the LiveStrategy protocol
    3. Provide metadata via the `metadata` class property
    4. Implement strategy logic in `on_bar` method
    """

    # Subclasses should override this
    metadata: TemplateMetadata = None

    def __init__(self):
        if LiveStrategy is None:
            raise RuntimeError("live_trading_sdk is required for template strategies")
        self._context: StrategyContext | None = None
        self._params: dict[str, Any] = {}

    # ---------- LiveStrategy Protocol ----------

    def initialize(self, context: StrategyContext) -> None:
        """Initialize the strategy with context."""
        self._context = context
        self._params = dict(context.params or {})

    def on_bar(self, bar: Any, history: pd.DataFrame, broker: Any) -> None:
        """Called on each new bar.

        Subclasses must implement this method.
        """
        raise NotImplementedError("Subclasses must implement on_bar")

    def on_error(self, error: Exception, broker: Any) -> None:
        """Optional error callback."""
        pass

    # ---------- Helper Methods ----------

    @property
    def context(self) -> StrategyContext:
        """Get the strategy context."""
        if self._context is None:
            raise RuntimeError("Strategy not initialized. Call initialize() first.")
        return self._context

    @property
    def params(self) -> dict[str, Any]:
        """Get strategy parameters."""
        return self._params

    def get_param(self, key: str, default: Any = None) -> Any:
        """Get a parameter value with default."""
        return self._params.get(key, default)

    # ---------- Class Methods ----------

    @classmethod
    def get_metadata(cls) -> TemplateMetadata:
        """Get the template metadata."""
        if cls.metadata is None:
            raise NotImplementedError("Subclasses must define metadata class property")
        return cls.metadata

    @classmethod
    def to_spec_dict(cls) -> dict[str, Any]:
        """Convert template to strategy spec dictionary."""
        metadata = cls.get_metadata()
        return {
            "name": metadata.name,
            "description": metadata.description,
            "version": metadata.version,
            "author": metadata.author,
            "tags": metadata.tags,
            "risk_level": metadata.risk_level,
            "trading_frequency": metadata.trading_frequency,
            "complexity_score": metadata.complexity_score,
            "min_capital_usdt": metadata.min_capital_usdt,
            "supported_exchanges": metadata.supported_exchanges,
            "supported_symbols": metadata.supported_symbols,
            "backtest_summary": metadata.backtest_summary,
        }
