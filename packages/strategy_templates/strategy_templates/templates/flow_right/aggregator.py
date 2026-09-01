from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime

from .stream import TradeEvent


@dataclass
class MinuteBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    buy_volume: float
    sell_volume: float
    delta: float
    trade_count: int
    buy_count: int
    sell_count: int
    avg_trade_size: float
    max_trade_size: float
    vwap: float

    @property
    def imbalance(self) -> float:
        total = self.buy_volume + self.sell_volume
        if total <= 0:
            return 0.0
        return (self.buy_volume - self.sell_volume) / total

    @property
    def price_change_pct(self) -> float:
        if self.open <= 0:
            return 0.0
        return (self.close - self.open) / self.open * 100

    @property
    def range_pct(self) -> float:
        if self.open <= 0:
            return 0.0
        return (self.high - self.low) / self.open * 100


@dataclass
class BarBuilder:
    minute_ts_ms: int
    open_price: float | None = None
    high_price: float = 0.0
    low_price: float = float("inf")
    close_price: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    max_trade_size: float = 0.0
    notional_sum: float = 0.0
    price_volume_sum: float = 0.0

    def add_trade(self, trade: TradeEvent) -> None:
        if self.open_price is None:
            self.open_price = trade.price

        self.high_price = max(self.high_price, trade.price)
        self.low_price = min(self.low_price, trade.price)
        self.close_price = trade.price

        if trade.side == "buy":
            self.buy_volume += trade.notional
            self.buy_count += 1
        else:
            self.sell_volume += trade.notional
            self.sell_count += 1

        self.max_trade_size = max(self.max_trade_size, trade.notional)
        self.notional_sum += trade.notional
        self.price_volume_sum += trade.price * trade.notional

    def build(self) -> MinuteBar | None:
        if self.open_price is None:
            return None

        total_volume = self.buy_volume + self.sell_volume
        trade_count = self.buy_count + self.sell_count
        avg_size = total_volume / trade_count if trade_count > 0 else 0.0
        vwap = self.price_volume_sum / total_volume if total_volume > 0 else self.close_price

        minute_ts = datetime.fromtimestamp(self.minute_ts_ms / 1000.0, tz=UTC)
        return MinuteBar(
            timestamp=minute_ts,
            open=self.open_price,
            high=self.high_price,
            low=self.low_price if self.low_price != float("inf") else self.open_price,
            close=self.close_price,
            volume=total_volume,
            buy_volume=self.buy_volume,
            sell_volume=self.sell_volume,
            delta=self.buy_volume - self.sell_volume,
            trade_count=trade_count,
            buy_count=self.buy_count,
            sell_count=self.sell_count,
            avg_trade_size=avg_size,
            max_trade_size=self.max_trade_size,
            vwap=vwap,
        )


class MinuteBarAggregator:
    def __init__(self, max_bars: int = 60):
        self.max_bars = max_bars
        self.bars: deque[MinuteBar] = deque(maxlen=max_bars)
        self._current_builder: BarBuilder | None = None
        self._current_minute_ms: int | None = None

    def ingest(self, trade: TradeEvent) -> MinuteBar | None:
        trade_minute_ms = self._truncate_to_minute_ms(trade.timestamp_ms)

        if self._current_minute_ms is None:
            self._current_minute_ms = trade_minute_ms
            self._current_builder = BarBuilder(minute_ts_ms=trade_minute_ms)
            self._current_builder.add_trade(trade)
            return None

        if trade_minute_ms == self._current_minute_ms:
            if self._current_builder:
                self._current_builder.add_trade(trade)
            return None

        completed_bar: MinuteBar | None = None
        if self._current_builder:
            completed_bar = self._current_builder.build()
            if completed_bar:
                self.bars.append(completed_bar)

        self._current_minute_ms = trade_minute_ms
        self._current_builder = BarBuilder(minute_ts_ms=trade_minute_ms)
        self._current_builder.add_trade(trade)

        return completed_bar

    def get_current_bar(self) -> MinuteBar | None:
        if self._current_builder:
            return self._current_builder.build()
        return None

    def get_bars(self, n: int | None = None) -> list[MinuteBar]:
        if n is None:
            return list(self.bars)
        return list(self.bars)[-n:] if n > 0 else []

    def get_cumulative_delta(self, n_bars: int) -> float:
        bars = self.get_bars(n_bars)
        return sum(bar.delta for bar in bars)

    def get_cumulative_volume(self, n_bars: int) -> float:
        bars = self.get_bars(n_bars)
        return sum(bar.volume for bar in bars)

    @staticmethod
    def _truncate_to_minute_ms(timestamp_ms: int) -> int:
        if timestamp_ms <= 0:
            return 0
        return timestamp_ms - (timestamp_ms % 60_000)

    def reset(self) -> None:
        self.bars.clear()
        self._current_builder = None
        self._current_minute_ms = None


__all__ = ["MinuteBar", "MinuteBarAggregator"]
