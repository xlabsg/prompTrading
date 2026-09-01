from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .detector import Direction, DivergenceSignal
from .entry import EntryPlan


def _parse_bar_duration(value: str | pd.Timedelta | None) -> pd.Timedelta:
    if value is None:
        return pd.Timedelta(minutes=15)
    if isinstance(value, pd.Timedelta):
        return value
    unit = value[-1].lower()
    amount = int(value[:-1])
    if unit == "m":
        return pd.Timedelta(minutes=amount)
    if unit == "h":
        return pd.Timedelta(hours=amount)
    if unit == "d":
        return pd.Timedelta(days=amount)
    raise ValueError(f"Unsupported timeframe '{value}'")


@dataclass
class AggregatedSignal:
    timestamp: pd.Timestamp
    price: float
    direction: Direction
    indicators: list[str] = field(default_factory=list)
    trend_aligned: bool | None = None
    funding_rate: float | None = None
    funding_tailwind: str | None = None
    rejection_reason: str = ""
    bar_index: int = -1
    entry: EntryPlan | None = None
    tp_target_price: float | None = None

    @property
    def indicator_count(self) -> int:
        return len(self.indicators)

    @property
    def strength(self) -> float:
        return min(self.indicator_count / 6.0, 1.0)


@dataclass
class FilterResult:
    passed: list[AggregatedSignal] = field(default_factory=list)
    rejected_trend: list[tuple[AggregatedSignal, str]] = field(default_factory=list)
    rejected_funding: list[tuple[AggregatedSignal, str]] = field(default_factory=list)
    rejected_rr: list[tuple[AggregatedSignal, str]] = field(default_factory=list)

    @property
    def total_rejected(self) -> int:
        return len(self.rejected_trend) + len(self.rejected_funding) + len(self.rejected_rr)

    def summary(self) -> str:
        return (
            f"Passed: {len(self.passed)}, "
            f"Rejected (trend): {len(self.rejected_trend)}, "
            f"Rejected (funding): {len(self.rejected_funding)}, "
            f"Rejected (R:R): {len(self.rejected_rr)}"
        )


def aggregate_signals(
    divergence_signals: list[DivergenceSignal],
    min_confirmations: int,
    bar_duration: str | pd.Timedelta | None = None,
) -> list[AggregatedSignal]:
    bar_delta = _parse_bar_duration(bar_duration)

    buckets: dict[tuple[int, Direction], AggregatedSignal] = {}
    indicator_sets: dict[tuple[int, Direction], set[str]] = {}

    for signal in divergence_signals:
        key = (signal.pivot.index, signal.direction)

        confirmed_ts = signal.pivot.confirmed_timestamp or signal.pivot.timestamp
        signal_perceivable_ts = confirmed_ts + bar_delta

        confirmed_idx = (
            signal.pivot.confirmed_index
            if signal.pivot.confirmed_index is not None
            else signal.pivot.index
        )
        if key not in buckets:
            buckets[key] = AggregatedSignal(
                timestamp=signal_perceivable_ts,
                price=signal.price_value,
                direction=signal.direction,
                indicators=[signal.indicator],
                bar_index=confirmed_idx,
            )
            indicator_sets[key] = {signal.indicator}
        else:
            if signal.indicator not in indicator_sets[key]:
                indicator_sets[key].add(signal.indicator)
                buckets[key].indicators.append(signal.indicator)

    filtered = [sig for sig in buckets.values() if sig.indicator_count >= min_confirmations]
    filtered.sort(key=lambda s: s.timestamp)
    return filtered


def apply_filters(
    signals: list[AggregatedSignal],
    trend_filter=None,
    funding_filter=None,
    trend_context=None,
    funding_data=None,
    strict_funding: bool = False,
) -> FilterResult:
    result = FilterResult()

    for signal in signals:
        if trend_filter:
            allowed, reason = trend_filter.should_allow_signal(signal.direction, trend_context)
            if not allowed:
                signal.trend_aligned = False
                signal.rejection_reason = reason
                result.rejected_trend.append((signal, reason))
                continue
            signal.trend_aligned = True

        if funding_filter:
            resolved_funding_data = funding_data(signal) if callable(funding_data) else funding_data
            if strict_funding and resolved_funding_data is None:
                allowed = False
                reason = "Funding rate not available for signal timestamp"
                tailwind_indicator = None
            else:
                allowed, reason, tailwind_indicator = funding_filter.should_allow_signal(
                    signal.direction, resolved_funding_data
                )
            if not allowed:
                if resolved_funding_data:
                    signal.funding_rate = resolved_funding_data.funding_rate
                signal.rejection_reason = reason
                result.rejected_funding.append((signal, reason))
                continue
            if resolved_funding_data:
                signal.funding_rate = resolved_funding_data.funding_rate
            if tailwind_indicator:
                signal.funding_tailwind = tailwind_indicator
                if tailwind_indicator not in signal.indicators:
                    signal.indicators.append(tailwind_indicator)

        result.passed.append(signal)

    return result


def signals_to_dataframe(signals: list[AggregatedSignal]) -> pd.DataFrame:
    if not signals:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "price",
                "direction",
                "indicator_count",
                "indicators",
                "trend_aligned",
                "funding_rate",
                "funding_tailwind",
                "rejection_reason",
                "entry_limit_price",
                "entry_zone_low",
                "entry_zone_high",
                "entry_expires_at",
            ]
        )
    return pd.DataFrame(
        {
            "timestamp": [s.timestamp for s in signals],
            "price": [s.price for s in signals],
            "direction": [s.direction for s in signals],
            "indicator_count": [s.indicator_count for s in signals],
            "indicators": [",".join(s.indicators) for s in signals],
            "trend_aligned": [s.trend_aligned for s in signals],
            "funding_rate": [s.funding_rate for s in signals],
            "funding_tailwind": [s.funding_tailwind for s in signals],
            "rejection_reason": [s.rejection_reason for s in signals],
            "entry_limit_price": [s.entry.limit_price if s.entry else None for s in signals],
            "entry_zone_low": [s.entry.zone_low if s.entry else None for s in signals],
            "entry_zone_high": [s.entry.zone_high if s.entry else None for s in signals],
            "entry_expires_at": [s.entry.expires_at if s.entry else None for s in signals],
        }
    )


def filter_result_to_dataframe(result: FilterResult) -> pd.DataFrame:
    records = []

    def add_record(signal: AggregatedSignal, status: str, reason: str) -> None:
        records.append(
            {
                "timestamp": signal.timestamp,
                "price": signal.price,
                "direction": signal.direction,
                "indicator_count": signal.indicator_count,
                "indicators": ",".join(signal.indicators),
                "funding_tailwind": signal.funding_tailwind,
                "status": status,
                "rejection_reason": reason,
                "entry_limit_price": signal.entry.limit_price if signal.entry else None,
                "entry_zone_low": signal.entry.zone_low if signal.entry else None,
                "entry_zone_high": signal.entry.zone_high if signal.entry else None,
                "entry_expires_at": signal.entry.expires_at if signal.entry else None,
            }
        )

    for signal in result.passed:
        add_record(signal, "passed", "")

    for signal, reason in result.rejected_trend:
        add_record(signal, "rejected_trend", reason)

    for signal, reason in result.rejected_funding:
        add_record(signal, "rejected_funding", reason)

    for signal, reason in result.rejected_rr:
        add_record(signal, "rejected_rr", reason)

    if not records:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "price",
                "direction",
                "indicator_count",
                "indicators",
                "funding_tailwind",
                "status",
                "rejection_reason",
                "entry_limit_price",
                "entry_zone_low",
                "entry_zone_high",
                "entry_expires_at",
            ]
        )

    df = pd.DataFrame(records)
    df.sort_values("timestamp", inplace=True)
    return df.reset_index(drop=True)
