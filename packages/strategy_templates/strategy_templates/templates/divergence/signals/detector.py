from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategy_templates.shared.pivots import Pivot

Direction = Literal["long", "short"]


@dataclass
class DivergenceSignal:
    pivot: Pivot
    indicator: str
    direction: Direction
    price_value: float
    indicator_value: float


def _pairwise(pivots: list[Pivot]) -> list[tuple[Pivot, Pivot]]:
    return list(zip(pivots, pivots[1:]))


def detect_regular_divergence(
    pivots: list[Pivot],
    indicator_series: pd.Series,
    indicator_name: str,
) -> list[DivergenceSignal]:
    signals: list[DivergenceSignal] = []
    highs = [p for p in pivots if p.kind == "high"]
    lows = [p for p in pivots if p.kind == "low"]

    for first, second in _pairwise(highs):
        first_val = indicator_series.iloc[first.index]
        second_val = indicator_series.iloc[second.index]
        if pd.isna(first_val) or pd.isna(second_val):
            continue
        if second.price > first.price and second_val < first_val:
            signals.append(
                DivergenceSignal(
                    pivot=second,
                    indicator=indicator_name,
                    direction="short",
                    price_value=second.price,
                    indicator_value=float(second_val),
                )
            )

    for first, second in _pairwise(lows):
        first_val = indicator_series.iloc[first.index]
        second_val = indicator_series.iloc[second.index]
        if pd.isna(first_val) or pd.isna(second_val):
            continue
        if second.price < first.price and second_val > first_val:
            signals.append(
                DivergenceSignal(
                    pivot=second,
                    indicator=indicator_name,
                    direction="long",
                    price_value=second.price,
                    indicator_value=float(second_val),
                )
            )
    return signals


def filter_signals_by_zone(
    signals: list[DivergenceSignal],
    *,
    short_min: float | None = None,
    long_max: float | None = None,
) -> list[DivergenceSignal]:
    if not signals:
        return []

    smin = None if short_min is None else float(short_min)
    lmax = None if long_max is None else float(long_max)

    out: list[DivergenceSignal] = []
    for s in signals:
        v = float(getattr(s, "indicator_value", float("nan")))
        if not math.isfinite(v):
            continue
        if s.direction == "short":
            if smin is None or v >= smin:
                out.append(s)
            continue
        if lmax is None or v <= lmax:
            out.append(s)
    return out
