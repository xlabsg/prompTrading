"""Flow Right Strategy - order flow template adapted for bar data."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
from live_trading_sdk import Bar, Broker, StrategyContext

from strategy_templates.base import BaseTemplateStrategy, TemplateMetadata

from .analyzer import FlowAnalyzer
from .anomaly import AnomalyConfig, AnomalyDetector
from .aggregator import MinuteBar
from .config import FlowRightConfig, WindowConfig
from .multiscale import confirm_multiscale
from .trend_filter import EmaRegimeFilter
from .types import Direction, Signal
from .stream import TradeEvent


class FlowRightStrategy(BaseTemplateStrategy):
    """Flow Right strategy adapted to bar-based data."""

    metadata = TemplateMetadata(
        name="flow_right",
        description="Order-flow momentum strategy with multi-window flow scoring and regime filters.",
        version="1.0.0",
        author="Stratsmith",
        tags=["order_flow", "momentum", "high_frequency"],
        risk_level="high",
        trading_frequency="high_frequency",
        complexity_score=4,
        min_capital_usdt=500.0,
        supported_exchanges=["okx", "binance"],
        supported_symbols=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
    )

    def initialize(self, context: StrategyContext) -> None:
        super().initialize(context)
        self._cfg = self._build_config(self._params)
        self._bar_interval_sec = self._parse_interval_seconds(
            self._params.get("live_bar_interval") or "1m"
        )

        self._windows = self._build_windows(self._cfg.windows, self._bar_interval_sec)
        self._analyzer = FlowAnalyzer(self._windows, analytics=self._cfg.analytics)
        self._anomaly = AnomalyDetector(AnomalyConfig())
        self._trend_filter = EmaRegimeFilter(self._cfg.trend_filter)

        self._minute_bars: list[MinuteBar] = []
        self._last_signal_ts: datetime | None = None
        self._position_dir = 0
        self._entry_time: datetime | None = None
        self._last_bar_ts_ms: int | None = None

    def on_bar(self, bar: Bar, history: pd.DataFrame, broker: Broker) -> None:
        self._last_bar_ts_ms = int(getattr(bar, "timestamp", 0) or 0)
        trade = self._bar_to_trade(bar)
        snapshot = self._analyzer.ingest(trade)

        minute_bar = self._bar_to_minute_bar(bar)
        self._minute_bars.append(minute_bar)
        max_bars = max(60, max([w.seconds for w in self._windows]) // 60 + 30)
        if len(self._minute_bars) > max_bars:
            self._minute_bars = self._minute_bars[-max_bars:]

        self._anomaly.add_bar(minute_bar)

        if self._should_exit(bar, broker):
            broker.set_target_allocation(0.0, reason="flow_right_time_exit")
            self._position_dir = 0
            self._entry_time = None
            return

        signal = self._maybe_emit_signal(snapshot)
        if not signal:
            return

        signal_dir = 1 if signal.direction == Direction.LONG else -1
        if signal_dir == self._position_dir:
            return

        target = float(self._params.get("position_size_pct", 0.15))
        target = max(0.0, min(1.0, target)) * signal_dir
        broker.set_target_allocation(target, reason=signal.reason)
        self._position_dir = signal_dir
        self._entry_time = signal.timestamp

    def _maybe_emit_signal(self, snapshot) -> Signal | None:
        cfg = self._cfg.entry
        impulse = snapshot.windows.get(cfg.impulse_window)
        confirmation = snapshot.windows.get(cfg.confirmation_window)
        context = snapshot.windows.get(cfg.context_window)

        if not impulse or not confirmation or not context:
            return None
        if impulse.trade_count < cfg.min_trade_count:
            return None
        if snapshot.total_notional < cfg.min_total_notional:
            return None
        if abs(snapshot.score) < cfg.min_score:
            return None
        if snapshot.volatility_bps > cfg.max_volatility_bps:
            return None

        direction: Direction | None = None
        if snapshot.score >= cfg.min_score and (
            impulse.imbalance >= cfg.min_short_imbalance
            and confirmation.imbalance >= cfg.min_mid_imbalance
            and context.imbalance >= cfg.min_long_imbalance
            and snapshot.velocity_bps >= cfg.min_velocity_bps
        ):
            direction = Direction.LONG
        elif snapshot.score <= -cfg.min_score and (
            impulse.imbalance <= -cfg.min_short_imbalance
            and confirmation.imbalance <= -cfg.min_mid_imbalance
            and context.imbalance <= -cfg.min_long_imbalance
            and snapshot.velocity_bps <= -cfg.min_velocity_bps
        ):
            direction = Direction.SHORT

        if direction is None:
            return None

        if not self._cooldown_passed(snapshot.timestamp):
            return None

        if self._cfg.signal.anomaly_enabled:
            anomaly = self._anomaly.analyze(
                direction_threshold=self._cfg.signal.anomaly_min_score
            )
            if not anomaly or anomaly.direction == "neutral":
                return None
            if direction == Direction.LONG and anomaly.direction != "long":
                return None
            if direction == Direction.SHORT and anomaly.direction != "short":
                return None

        ok, reason, _ = self._trend_filter.should_allow(direction, self._minute_bars)
        if not ok:
            return None

        ms_result = confirm_multiscale(direction, self._minute_bars, self._cfg.signal)
        if not ms_result.ok:
            return None

        signal_age = (self._resolve_now() - snapshot.timestamp).total_seconds()
        if signal_age > self._cfg.risk.signal_expiry_seconds:
            return None

        self._last_signal_ts = snapshot.timestamp

        metadata = {
            "score": round(snapshot.score, 4),
            "velocity_bps": round(snapshot.velocity_bps, 2),
            "volatility_bps": round(snapshot.volatility_bps, 2),
            "impulse_imbalance": round(impulse.imbalance, 3),
            "confirmation_imbalance": round(confirmation.imbalance, 3),
            "context_imbalance": round(context.imbalance, 3),
            "total_notional": snapshot.total_notional,
            "trade_count": impulse.trade_count,
        }

        strength = min(1.0, abs(snapshot.score))
        return Signal(
            direction=direction,
            timestamp=snapshot.timestamp,
            price=snapshot.price,
            strength=strength,
            reason=f"order_flow_{direction.value}",
            metadata=metadata,
        )

    def _cooldown_passed(self, timestamp: datetime) -> bool:
        if not self._last_signal_ts:
            return True
        elapsed_ms = (timestamp - self._last_signal_ts).total_seconds() * 1000
        return elapsed_ms >= self._cfg.risk.cooldown_ms

    def _resolve_now(self) -> datetime:
        now = datetime.now(UTC)
        ts_ms = self._last_bar_ts_ms
        if not ts_ms:
            return now
        if ts_ms < 10_000_000_000:
            ts_ms *= 1000
        bar_time = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
        if abs((now - bar_time).total_seconds()) > 2 * 24 * 3600:
            return bar_time
        return now

    def _should_exit(self, bar: Bar, broker: Broker) -> bool:
        if self._position_dir == 0 or not self._entry_time:
            return False
        max_hold = int(self._cfg.risk.max_position_seconds or 0)
        if max_hold <= 0:
            return False
        return (bar.timestamp - int(self._entry_time.timestamp() * 1000)) >= max_hold * 1000

    def _bar_to_trade(self, bar: Bar) -> TradeEvent:
        price = float(bar.close)
        open_px = float(bar.open)
        volume = float(getattr(bar, "volume", 0.0) or 0.0)
        notional = price * volume if volume > 0 else 0.0
        side = "buy" if price >= open_px else "sell"
        timestamp_ms = int(bar.timestamp)
        if timestamp_ms < 10_000_000_000:
            timestamp_ms *= 1000
        qty = volume if volume > 0 else 0.0
        trade_id = int(timestamp_ms)
        return TradeEvent(
            trade_id=trade_id,
            price=price,
            quantity=qty,
            notional=notional,
            timestamp_ms=timestamp_ms,
            side=side,
            is_buyer_maker=side != "buy",
        )

    def _bar_to_minute_bar(self, bar: Bar) -> MinuteBar:
        open_px = float(bar.open)
        close_px = float(bar.close)
        high_px = float(bar.high)
        low_px = float(bar.low)
        volume = float(getattr(bar, "volume", 0.0) or 0.0)

        rng = max(high_px - low_px, 1e-12)
        ratio = max(-1.0, min(1.0, (close_px - open_px) / rng))
        buy_share = 0.5 * (1.0 + ratio)
        sell_share = 1.0 - buy_share
        buy_volume = volume * buy_share
        sell_volume = volume * sell_share

        trade_count = max(1, int(volume / max(close_px, 1e-6))) if volume > 0 else 1
        avg_size = volume / trade_count if trade_count > 0 else 0.0
        max_trade = avg_size * 2.5
        vwap = close_px

        timestamp_ms = int(bar.timestamp)
        if timestamp_ms < 10_000_000_000:
            timestamp_ms *= 1000
        ts = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=UTC)
        return MinuteBar(
            timestamp=ts,
            open=open_px,
            high=high_px,
            low=low_px,
            close=close_px,
            volume=volume,
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            delta=buy_volume - sell_volume,
            trade_count=trade_count,
            buy_count=max(1, trade_count // 2),
            sell_count=max(1, trade_count // 2),
            avg_trade_size=avg_size,
            max_trade_size=max_trade,
            vwap=vwap,
        )

    def _parse_interval_seconds(self, interval: str) -> int:
        text = str(interval or "1m").strip().lower()
        if text.endswith("m"):
            return int(text[:-1]) * 60
        if text.endswith("h"):
            return int(text[:-1]) * 3600
        if text.endswith("d"):
            return int(text[:-1]) * 86400
        return 60

    def _build_windows(
        self, windows: list[WindowConfig], bar_interval_sec: int
    ) -> list[WindowConfig]:
        if not windows:
            return [
                WindowConfig(name="impulse", seconds=bar_interval_sec * 3, weight=1.0),
                WindowConfig(name="confirmation", seconds=bar_interval_sec * 9, weight=0.7),
                WindowConfig(name="context", seconds=bar_interval_sec * 18, weight=0.5),
            ]
        out: list[WindowConfig] = []
        for w in windows:
            secs = max(int(w.seconds), bar_interval_sec)
            if secs % bar_interval_sec != 0:
                secs = ((secs // bar_interval_sec) + 1) * bar_interval_sec
            out.append(WindowConfig(name=w.name, seconds=secs, weight=w.weight))
        return out

    def _build_config(self, params: dict[str, Any]) -> FlowRightConfig:
        cfg = FlowRightConfig()

        entry = replace(
            cfg.entry,
            min_score=float(params.get("min_score", cfg.entry.min_score)),
            min_short_imbalance=float(params.get("min_short_imbalance", cfg.entry.min_short_imbalance)),
            min_mid_imbalance=float(params.get("min_mid_imbalance", cfg.entry.min_mid_imbalance)),
            min_long_imbalance=float(params.get("min_long_imbalance", cfg.entry.min_long_imbalance)),
            min_total_notional=float(params.get("min_total_notional", cfg.entry.min_total_notional)),
            min_trade_count=int(params.get("min_trade_count", cfg.entry.min_trade_count)),
            min_velocity_bps=float(params.get("min_velocity_bps", cfg.entry.min_velocity_bps)),
            max_volatility_bps=float(params.get("max_volatility_bps", cfg.entry.max_volatility_bps)),
        )

        risk = replace(
            cfg.risk,
            cooldown_ms=int(params.get("cooldown_ms", cfg.risk.cooldown_ms)),
            max_position_seconds=int(params.get("max_position_seconds", cfg.risk.max_position_seconds)),
            signal_expiry_seconds=float(
                params.get("signal_expiry_seconds", cfg.risk.signal_expiry_seconds)
            ),
        )

        signal = replace(
            cfg.signal,
            anomaly_enabled=bool(params.get("anomaly_enabled", cfg.signal.anomaly_enabled)),
            anomaly_min_score=float(params.get("anomaly_min_score", cfg.signal.anomaly_min_score)),
            ms_confirm_enabled=bool(params.get("ms_confirm_enabled", cfg.signal.ms_confirm_enabled)),
            ms_confirm_5m_bars=int(params.get("ms_confirm_5m_bars", cfg.signal.ms_confirm_5m_bars)),
            ms_confirm_15m_bars=int(params.get("ms_confirm_15m_bars", cfg.signal.ms_confirm_15m_bars)),
            ms_confirm_5m_min_imbalance=float(
                params.get("ms_confirm_5m_min_imbalance", cfg.signal.ms_confirm_5m_min_imbalance)
            ),
            ms_confirm_15m_min_imbalance=float(
                params.get("ms_confirm_15m_min_imbalance", cfg.signal.ms_confirm_15m_min_imbalance)
            ),
            ms_confirm_5m_min_volume_zscore=float(
                params.get("ms_confirm_5m_min_volume_zscore", cfg.signal.ms_confirm_5m_min_volume_zscore)
            ),
            ms_confirm_15m_min_volume_zscore=float(
                params.get("ms_confirm_15m_min_volume_zscore", cfg.signal.ms_confirm_15m_min_volume_zscore)
            ),
        )

        trend = replace(
            cfg.trend_filter,
            enabled=bool(params.get("trend_filter_enabled", cfg.trend_filter.enabled)),
            timeframe_minutes=int(params.get("trend_timeframe_minutes", cfg.trend_filter.timeframe_minutes)),
            ema_period=int(params.get("trend_ema_period", cfg.trend_filter.ema_period)),
            slope_lookback=int(params.get("trend_slope_lookback", cfg.trend_filter.slope_lookback)),
            price_buffer_pct=float(params.get("trend_price_buffer_pct", cfg.trend_filter.price_buffer_pct)),
            neutral_policy=str(params.get("trend_neutral_policy", cfg.trend_filter.neutral_policy)),
            insufficient_data_policy=str(
                params.get("trend_insufficient_policy", cfg.trend_filter.insufficient_data_policy)
            ),
            max_entry_distance_pct=float(
                params.get("trend_max_entry_distance_pct", cfg.trend_filter.max_entry_distance_pct)
            ),
        )

        windows = cfg.windows
        if "flow_windows" in params:
            raw_windows = params.get("flow_windows") or []
            raw_weights = params.get("window_weights") or []
            windows = []
            for idx, value in enumerate(raw_windows):
                weight = (
                    float(raw_weights[idx])
                    if idx < len(raw_weights)
                    else cfg.windows[min(idx, len(cfg.windows) - 1)].weight
                )
                windows.append(WindowConfig(name=f"w{idx+1}", seconds=int(value), weight=weight))
            if len(windows) >= 3:
                windows[0] = replace(windows[0], name="impulse")
                windows[1] = replace(windows[1], name="confirmation")
                windows[2] = replace(windows[2], name="context")

        return replace(cfg, entry=entry, risk=risk, signal=signal, trend_filter=trend, windows=windows)


def create_live_strategy() -> FlowRightStrategy:
    return FlowRightStrategy()
