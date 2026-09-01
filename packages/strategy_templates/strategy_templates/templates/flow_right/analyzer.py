from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .config import WindowConfig
from .stream import TradeEvent


@dataclass
class WindowState:
    name: str
    seconds: int
    weight: float
    buy_notional: float = 0.0
    sell_notional: float = 0.0
    trade_count: int = 0
    prices: deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    window_start_ms: int = 0
    last_update_ms: int = 0

    @property
    def total_notional(self) -> float:
        return self.buy_notional + self.sell_notional

    @property
    def imbalance(self) -> float:
        total = self.total_notional
        if total <= 0:
            return 0.0
        return (self.buy_notional - self.sell_notional) / total

    @property
    def avg_trade_size(self) -> float:
        if self.trade_count <= 0:
            return 0.0
        return self.total_notional / self.trade_count

    def reset(self, timestamp_ms: int) -> None:
        self.buy_notional = 0.0
        self.sell_notional = 0.0
        self.trade_count = 0
        self.prices.clear()
        self.window_start_ms = timestamp_ms

    def add_trade(self, trade: TradeEvent) -> None:
        if trade.side == "buy":
            self.buy_notional += trade.notional
        else:
            self.sell_notional += trade.notional
        self.trade_count += 1
        self.prices.append(trade.price)
        self.last_update_ms = trade.timestamp_ms


@dataclass
class FlowSnapshot:
    timestamp: datetime
    price: float
    score: float
    total_notional: float
    velocity_bps: float
    volatility_bps: float
    windows: dict[str, WindowState] = field(default_factory=dict)
    impulse_score: float = 0.0
    context_score: float = 0.0


class FlowAnalyzer:
    def __init__(
        self,
        windows: list[WindowConfig],
        analytics=None,
    ) -> None:
        self.windows_config = windows
        self._states: dict[str, WindowState] = {
            w.name: WindowState(name=w.name, seconds=w.seconds, weight=w.weight) for w in windows
        }

        self._price_history: deque[tuple[int, float]] = deque(maxlen=2000)
        self._last_price: float | None = None
        self._last_timestamp_ms: int | None = None

        if analytics is None:
            analytics = type(
                "AnalyticsConfig",
                (),
                {
                    "volatility_window_seconds": 30,
                    "velocity_window_seconds": 3,
                    "max_price_history_seconds": 60,
                },
            )()
        self._analytics = analytics

        self._warmup_trades = 0
        self._min_warmup_trades = 20

    def ingest(self, trade: TradeEvent) -> FlowSnapshot:
        ts_ms = trade.timestamp_ms

        self._price_history.append((ts_ms, trade.price))
        self._last_price = trade.price
        self._last_timestamp_ms = ts_ms
        self._warmup_trades += 1

        for window_cfg in self.windows_config:
            state = self._states[window_cfg.name]
            self._update_window(state, trade, ts_ms)

        score = self._compute_composite_score()
        velocity_bps = self._compute_velocity_bps()
        volatility_bps = self._compute_volatility_bps()

        windows_dict = {name: state for name, state in self._states.items()}

        impulse_state = self._states.get("impulse")
        context_state = self._states.get("context")
        impulse_score = impulse_state.imbalance if impulse_state else 0.0
        context_score = context_state.imbalance if context_state else 0.0

        return FlowSnapshot(
            timestamp=datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC),
            price=trade.price,
            score=score,
            total_notional=sum(s.total_notional for s in self._states.values()),
            velocity_bps=velocity_bps,
            volatility_bps=volatility_bps,
            windows=windows_dict,
            impulse_score=impulse_score,
            context_score=context_score,
        )

    def _update_window(self, state: WindowState, trade: TradeEvent, ts_ms: int) -> None:
        if state.window_start_ms == 0:
            state.reset(ts_ms)

        window_duration_ms = state.seconds * 1000
        if ts_ms - state.window_start_ms >= window_duration_ms:
            state.reset(ts_ms)

        state.add_trade(trade)

    def _compute_composite_score(self) -> float:
        if self._warmup_trades < self._min_warmup_trades:
            return 0.0

        total_weight = 0.0
        weighted_sum = 0.0

        for state in self._states.values():
            if state.trade_count < 3:
                continue
            weighted_sum += state.imbalance * state.weight
            total_weight += state.weight

        if total_weight <= 0:
            return 0.0

        return weighted_sum / total_weight

    def _compute_velocity_bps(self) -> float:
        if len(self._price_history) < 2:
            return 0.0

        velocity_window_sec = getattr(self._analytics, "velocity_window_seconds", 3)
        cutoff_ms = self._last_timestamp_ms - (velocity_window_sec * 1000)

        oldest_price = None
        oldest_ts = None
        for ts, px in self._price_history:
            if ts >= cutoff_ms:
                oldest_price = px
                oldest_ts = ts
                break

        if oldest_price is None or oldest_price <= 0:
            return 0.0

        price_change_pct = ((self._last_price - oldest_price) / oldest_price) * 100
        time_elapsed_sec = (self._last_timestamp_ms - oldest_ts) / 1000.0 if oldest_ts else 1.0

        if time_elapsed_sec <= 0:
            return 0.0

        velocity_bps = price_change_pct / time_elapsed_sec
        return velocity_bps

    def _compute_volatility_bps(self) -> float:
        if len(self._price_history) < 10:
            return 0.0

        vol_window_sec = getattr(self._analytics, "volatility_window_seconds", 30)
        cutoff_ms = self._last_timestamp_ms - (vol_window_sec * 1000)

        prices = [px for ts, px in self._price_history if ts >= cutoff_ms]
        if len(prices) < 5:
            return 0.0

        returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0:
                ret = (prices[i] - prices[i - 1]) / prices[i - 1]
                returns.append(ret)

        if len(returns) < 3:
            return 0.0

        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance)

        return std_dev * 100 * 100

    def is_warmed_up(self) -> bool:
        return self._warmup_trades >= self._min_warmup_trades

    def reset(self) -> None:
        for state in self._states.values():
            state.reset(0)
        self._price_history.clear()
        self._last_price = None
        self._last_timestamp_ms = None
        self._warmup_trades = 0


__all__ = ["FlowAnalyzer", "FlowSnapshot", "WindowState"]
