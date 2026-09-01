from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from strategy_templates.shared.indicators import ema
from .aggregator import MinuteBar
from .config import TrendFilterConfig
from .types import Direction


class TrendRegime(Enum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class TrendSnapshot:
    regime: TrendRegime
    timeframe_minutes: int
    ema_period: int
    slope_lookback: int
    price: float
    ema_value: float
    distance_pct: float
    slope: float
    bar_count: int
    ready: bool
    timestamp: pd.Timestamp


class EmaRegimeFilter:
    def __init__(self, cfg: TrendFilterConfig):
        self.cfg = cfg

    def compute(self, minute_bars: Sequence[MinuteBar]) -> TrendSnapshot | None:
        cfg = self.cfg
        if not minute_bars:
            return None

        tf = max(int(cfg.timeframe_minutes or 1), 1)
        ema_period = max(int(cfg.ema_period or 0), 1)
        slope_lb = max(int(cfg.slope_lookback or 0), 1)
        buffer_pct = abs(float(cfg.price_buffer_pct or 0.0))

        idx = pd.DatetimeIndex([b.timestamp for b in minute_bars])
        close = pd.Series([float(b.close) for b in minute_bars], index=idx, dtype="float64")

        close = close[~close.index.duplicated(keep="last")].sort_index()

        if tf > 1:
            close = close.resample(f"{tf}min").last().dropna()

        required = ema_period + slope_lb + 1
        if len(close) < required:
            ts = pd.Timestamp(close.index[-1]) if len(close) else pd.Timestamp.utcnow()
            return TrendSnapshot(
                regime=TrendRegime.NEUTRAL,
                timeframe_minutes=tf,
                ema_period=ema_period,
                slope_lookback=slope_lb,
                price=float(close.iloc[-1]) if len(close) else 0.0,
                ema_value=0.0,
                distance_pct=0.0,
                slope=0.0,
                bar_count=int(len(close)),
                ready=False,
                timestamp=ts,
            )

        ema_series = ema(close, window=ema_period)
        ema_last = float(ema_series.iloc[-1])
        ema_prev = float(ema_series.iloc[-1 - slope_lb])
        slope = ema_last - ema_prev

        price_last = float(close.iloc[-1])
        distance_pct = ((price_last - ema_last) / ema_last * 100.0) if ema_last else 0.0

        if abs(distance_pct) <= buffer_pct:
            regime = TrendRegime.NEUTRAL
        elif distance_pct > buffer_pct and slope > 0:
            regime = TrendRegime.UP
        elif distance_pct < -buffer_pct and slope < 0:
            regime = TrendRegime.DOWN
        else:
            regime = TrendRegime.NEUTRAL

        return TrendSnapshot(
            regime=regime,
            timeframe_minutes=tf,
            ema_period=ema_period,
            slope_lookback=slope_lb,
            price=price_last,
            ema_value=ema_last,
            distance_pct=distance_pct,
            slope=slope,
            bar_count=int(len(close)),
            ready=True,
            timestamp=pd.Timestamp(close.index[-1]),
        )

    def should_allow(
        self,
        direction: Direction,
        minute_bars: Sequence[MinuteBar],
    ) -> tuple[bool, str, TrendSnapshot | None]:
        cfg = self.cfg
        if not cfg.enabled:
            return True, "trend_filter_disabled", None

        snap = self.compute(minute_bars)
        if snap is None:
            policy = (cfg.insufficient_data_policy or "skip").strip().lower()
            if policy == "allow_both":
                return True, "trend_filter_no_data_allow", None
            return False, "trend_filter_no_data_skip", None

        if not snap.ready:
            policy = (cfg.insufficient_data_policy or "skip").strip().lower()
            if policy == "allow_both":
                return True, "trend_filter_warmup_allow", snap
            return False, "trend_filter_warmup_skip", snap

        max_entry_dist = float(getattr(cfg, "max_entry_distance_pct", 0.0) or 0.0)
        if max_entry_dist > 0:
            if direction == Direction.LONG and snap.distance_pct > max_entry_dist:
                return False, "trend_filter_overextended_long", snap
            if direction == Direction.SHORT and snap.distance_pct < -max_entry_dist:
                return False, "trend_filter_overextended_short", snap

        if snap.regime == TrendRegime.NEUTRAL:
            policy = (cfg.neutral_policy or "skip").strip().lower()
            if policy == "allow_both":
                return True, "trend_filter_neutral_allow", snap
            return False, "trend_filter_neutral_skip", snap

        if direction == Direction.LONG:
            if snap.regime != TrendRegime.UP:
                return False, f"trend_filter_block_long_regime={snap.regime.value}", snap
            return True, "trend_filter_allow_long", snap

        if direction == Direction.SHORT:
            if snap.regime != TrendRegime.DOWN:
                return False, f"trend_filter_block_short_regime={snap.regime.value}", snap
            return True, "trend_filter_allow_short", snap

        return False, "trend_filter_unknown_direction", snap


__all__ = ["EmaRegimeFilter", "TrendRegime", "TrendSnapshot"]
