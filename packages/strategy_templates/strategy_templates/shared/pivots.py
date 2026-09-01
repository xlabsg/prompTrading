from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

PivotKind = Literal["high", "low"]


@dataclass
class Pivot:
    index: int
    timestamp: pd.Timestamp
    price: float
    kind: PivotKind
    confirmed_index: int | None = None
    confirmed_timestamp: pd.Timestamp | None = None


def detect_pivots_confirmed(
    close: pd.Series,
    timestamps: pd.Series,
    *,
    left: int,
    right: int,
) -> list[Pivot]:
    pivots: list[Pivot] = []
    length = len(close)
    if left < 0 or right < 0:
        raise ValueError("left/right pivot window sizes must be non-negative")
    if length < (left + right) + 1:
        return pivots

    for idx in range(left, length - right):
        center_price = close.iloc[idx]
        if pd.isna(center_price):
            continue

        left_slice = close.iloc[idx - left : idx] if left > 0 else None
        right_slice = close.iloc[idx + 1 : idx + right + 1] if right > 0 else None

        max_left = left_slice.max(skipna=True) if left_slice is not None else float("-inf")
        max_right = right_slice.max(skipna=True) if right_slice is not None else float("-inf")
        min_left = left_slice.min(skipna=True) if left_slice is not None else float("inf")
        min_right = right_slice.min(skipna=True) if right_slice is not None else float("inf")

        if pd.isna(max_left):
            max_left = float("-inf")
        if pd.isna(max_right):
            max_right = float("-inf")
        if pd.isna(min_left):
            min_left = float("inf")
        if pd.isna(min_right):
            min_right = float("inf")

        confirmed_index = idx + right
        confirmed_ts = timestamps.iloc[confirmed_index]

        if center_price > max(max_left, max_right):
            pivots.append(
                Pivot(
                    index=idx,
                    timestamp=timestamps.iloc[idx],
                    price=float(center_price),
                    kind="high",
                    confirmed_index=confirmed_index,
                    confirmed_timestamp=confirmed_ts,
                )
            )

        if center_price < min(min_left, min_right):
            pivots.append(
                Pivot(
                    index=idx,
                    timestamp=timestamps.iloc[idx],
                    price=float(center_price),
                    kind="low",
                    confirmed_index=confirmed_index,
                    confirmed_timestamp=confirmed_ts,
                )
            )
    return pivots


def detect_pivots(
    close: pd.Series,
    timestamps: pd.Series,
    period: int,
) -> list[Pivot]:
    return detect_pivots_confirmed(close, timestamps, left=period, right=period)
