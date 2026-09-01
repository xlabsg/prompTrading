from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from .aggregator import MinuteBar


@dataclass
class AnomalyConfig:
    absorption_weight: float = 0.40
    absorption_volume_zscore: float = 2.0
    absorption_max_price_change_pct: float = 0.15
    divergence_weight: float = 0.30
    divergence_lookback_bars: int = 15
    divergence_price_threshold_pct: float = 0.3
    volume_spike_weight: float = 0.20
    volume_spike_zscore: float = 2.5
    large_order_weight: float = 0.10
    large_order_multiplier: float = 3.0
    min_bars_for_stats: int = 10
    rolling_window_bars: int = 30


@dataclass
class AnomalySnapshot:
    timestamp: datetime
    price: float
    absorption_score: float
    divergence_score: float
    volume_spike_score: float
    large_order_score: float
    total_score: float
    direction: str
    details: dict


class AnomalyDetector:
    def __init__(self, config: AnomalyConfig):
        self.config = config
        self._bars: list[MinuteBar] = []

    @property
    def bars(self) -> list[MinuteBar]:
        return self._bars

    def add_bar(self, bar: MinuteBar) -> None:
        self._bars.append(bar)
        max_needed = (
            max(
                self.config.rolling_window_bars,
                self.config.divergence_lookback_bars,
            )
            + 10
        )
        if len(self._bars) > max_needed:
            self._bars = self._bars[-max_needed:]

    def analyze(
        self,
        current_bar: MinuteBar | None = None,
        *,
        direction_threshold: float = 0.3,
    ) -> AnomalySnapshot | None:
        bars = self._bars.copy()
        if current_bar:
            bars.append(current_bar)

        if len(bars) < self.config.min_bars_for_stats:
            return None

        latest = bars[-1]

        absorption_score, absorption_details = self._detect_absorption(bars)
        divergence_score, divergence_details = self._detect_divergence(bars)
        volume_spike_score, volume_details = self._detect_volume_spike(bars)
        large_order_score, large_order_details = self._detect_large_orders(bars)

        total_score = (
            self.config.absorption_weight * absorption_score
            + self.config.divergence_weight * divergence_score
            + self.config.volume_spike_weight * volume_spike_score
            + self.config.large_order_weight * large_order_score
        )

        threshold = max(float(direction_threshold or 0.0), 0.0)
        if total_score >= threshold:
            direction = "long"
        elif total_score <= -threshold:
            direction = "short"
        else:
            direction = "neutral"

        details = {
            "absorption": absorption_details,
            "divergence": divergence_details,
            "volume_spike": volume_details,
            "large_order": large_order_details,
            "bar_count": len(bars),
        }

        return AnomalySnapshot(
            timestamp=latest.timestamp,
            price=latest.close,
            absorption_score=absorption_score,
            divergence_score=divergence_score,
            volume_spike_score=volume_spike_score,
            large_order_score=large_order_score,
            total_score=total_score,
            direction=direction,
            details=details,
        )

    def _detect_absorption(self, bars: list[MinuteBar]) -> tuple[float, dict]:
        if len(bars) < self.config.min_bars_for_stats:
            return 0.0, {"reason": "insufficient_bars"}

        latest = bars[-1]
        lookback = bars[-self.config.rolling_window_bars :]

        volumes = [b.volume for b in lookback]
        vol_mean, vol_std = self._mean_std(volumes)

        if vol_std <= 0:
            return 0.0, {"reason": "no_volume_variance"}

        vol_zscore = (latest.volume - vol_mean) / vol_std
        price_change = abs(latest.price_change_pct)

        details = {
            "volume_zscore": round(vol_zscore, 3),
            "price_change_pct": round(price_change, 4),
            "threshold_zscore": self.config.absorption_volume_zscore,
            "threshold_price": self.config.absorption_max_price_change_pct,
        }

        if vol_zscore < self.config.absorption_volume_zscore:
            details["reason"] = "volume_not_high_enough"
            return 0.0, details

        if price_change > self.config.absorption_max_price_change_pct:
            details["reason"] = "price_moved_too_much"
            return 0.0, details

        delta_ratio = latest.delta / latest.volume if latest.volume > 0 else 0

        if delta_ratio < -0.2:
            score = min(1.0, vol_zscore / 3.0)
            details["reason"] = "bullish_absorption"
            details["delta_ratio"] = round(delta_ratio, 3)
            return score, details
        if delta_ratio > 0.2:
            score = -min(1.0, vol_zscore / 3.0)
            details["reason"] = "bearish_absorption"
            details["delta_ratio"] = round(delta_ratio, 3)
            return score, details

        details["reason"] = "delta_not_extreme"
        return 0.0, details

    def _detect_divergence(self, bars: list[MinuteBar]) -> tuple[float, dict]:
        if len(bars) < self.config.divergence_lookback_bars:
            return 0.0, {"reason": "insufficient_bars"}

        recent = bars[-self.config.divergence_lookback_bars :]
        prices = [b.close for b in recent]
        deltas = [b.delta for b in recent]

        price_change = (prices[-1] - prices[0]) / prices[0] * 100 if prices[0] else 0
        delta_change = (deltas[-1] - deltas[0]) / abs(deltas[0]) if deltas[0] else 0

        details = {
            "price_change_pct": round(price_change, 3),
            "delta_change_ratio": round(delta_change, 3),
        }

        if abs(price_change) < self.config.divergence_price_threshold_pct:
            details["reason"] = "price_move_too_small"
            return 0.0, details

        if price_change > 0 and delta_change < -0.2:
            score = min(1.0, abs(delta_change))
            details["reason"] = "bearish_divergence"
            return -score, details
        if price_change < 0 and delta_change > 0.2:
            score = min(1.0, abs(delta_change))
            details["reason"] = "bullish_divergence"
            return score, details

        details["reason"] = "no_divergence"
        return 0.0, details

    def _detect_volume_spike(self, bars: list[MinuteBar]) -> tuple[float, dict]:
        if len(bars) < self.config.min_bars_for_stats:
            return 0.0, {"reason": "insufficient_bars"}

        latest = bars[-1]
        lookback = bars[-self.config.rolling_window_bars :]
        volumes = [b.volume for b in lookback]
        vol_mean, vol_std = self._mean_std(volumes)

        if vol_std <= 0:
            return 0.0, {"reason": "no_volume_variance"}

        zscore = (latest.volume - vol_mean) / vol_std
        details = {"volume_zscore": round(zscore, 3)}

        if zscore < self.config.volume_spike_zscore:
            details["reason"] = "volume_not_high_enough"
            return 0.0, details

        if latest.delta > 0:
            score = min(1.0, zscore / 3.0)
        else:
            score = -min(1.0, zscore / 3.0)
        details["reason"] = "volume_spike"
        return score, details

    def _detect_large_orders(self, bars: list[MinuteBar]) -> tuple[float, dict]:
        if len(bars) < self.config.min_bars_for_stats:
            return 0.0, {"reason": "insufficient_bars"}

        latest = bars[-1]
        lookback = bars[-self.config.rolling_window_bars :]
        avg_sizes = [b.avg_trade_size for b in lookback]
        avg_mean, avg_std = self._mean_std(avg_sizes)

        if avg_std <= 0:
            return 0.0, {"reason": "no_size_variance"}

        if latest.max_trade_size <= avg_mean * self.config.large_order_multiplier:
            return 0.0, {"reason": "no_large_orders"}

        score = 1.0 if latest.delta >= 0 else -1.0
        details = {
            "max_trade_size": round(latest.max_trade_size, 2),
            "avg_trade_size": round(avg_mean, 2),
        }
        return score, details

    @staticmethod
    def _mean_std(values: list[float]) -> tuple[float, float]:
        if not values:
            return 0.0, 0.0
        mean = sum(values) / len(values)
        var = sum((v - mean) ** 2 for v in values) / len(values)
        return mean, math.sqrt(var)


__all__ = ["AnomalyConfig", "AnomalyDetector", "AnomalySnapshot"]
