from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from live_trading_sdk import Bar, StrategyContext


@dataclass
class LiveAdapterConfig:
    exchange: str = "okx"
    symbol: str = "BTC-USDT-SWAP"
    interval: str = "1h"
    history_bars: int = 200
    max_position_pct: float = 10.0
    stop_loss_pct: float = 5.0


class BacktestBroker:
    def __init__(self, n: int, *, max_position_pct: float) -> None:
        self._target: float = 0.0
        self._last_price: float = 0.0
        self._target_weights = np.zeros(n, dtype=np.float64)
        self._max_position_frac = max(0.0, min(1.0, float(max_position_pct) / 100.0))

    @property
    def target_weights(self) -> np.ndarray:
        return self._target_weights

    def step(self, i: int, *, last_price: float) -> None:
        self._last_price = float(last_price)
        self._target_weights[i] = float(self._target) * self._max_position_frac

    def set_target_allocation(self, target: float, *, reason: str | None = None) -> None:  # noqa: ARG002
        self._target = float(np.clip(float(target), -1.0, 1.0))

    def market_order(self, side: str, size: float, *, reason: str | None = None) -> None:  # noqa: ARG002
        if size <= 0:
            return
        normalized = (side or "").strip().lower()
        if normalized == "buy":
            self._target = 1.0
        elif normalized == "sell":
            self._target = -1.0
        else:
            raise ValueError("side must be 'buy' or 'sell'")

    def current_position(self) -> float:
        return 0.0

    def last_price(self) -> float:
        return float(self._last_price)


def generate_signals_from_live_strategy(
    create_strategy: Callable[[], Any],
    data: pd.DataFrame,
    *,
    params: dict[str, Any] | None = None,
    adapter: LiveAdapterConfig | None = None,
) -> dict[str, Any]:
    if data.empty:
        raise ValueError("data is empty")
    adapter = adapter or LiveAdapterConfig()
    params = dict(params or {})

    strategy = create_strategy()
    context = StrategyContext(
        exchange=adapter.exchange,
        symbol=adapter.symbol,
        interval=adapter.interval,
        symbols=[adapter.symbol],
        intervals=[adapter.interval],
        params=params,
        max_position_pct=adapter.max_position_pct,
        stop_loss_pct=adapter.stop_loss_pct,
    )
    strategy.initialize(context)

    n = int(len(data))
    broker = BacktestBroker(n=n, max_position_pct=adapter.max_position_pct)
    history_bars = int(params.get("live_history_bars", adapter.history_bars))
    history_bars = max(1, min(history_bars, 10_000))

    for i in range(n):
        row = data.iloc[i]
        bar = Bar(
            timestamp=int(row["timestamp"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            symbol=adapter.symbol,
            interval=adapter.interval,
        )
        start = max(0, i + 1 - history_bars)
        history = data.iloc[start : i + 1].copy()
        try:
            strategy.on_bar(bar, history, broker)
        except Exception as exc:
            try:
                strategy.on_error(exc, broker)
            except Exception:
                raise
        broker.step(i, last_price=bar.close)

    return {"target_weights": broker.target_weights}
