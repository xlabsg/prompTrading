from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class EntryPlan:
    zone_low: float
    zone_high: float
    limit_price: float
    reference_level: float
    created_at: pd.Timestamp
    active_after: pd.Timestamp
    expires_at: pd.Timestamp
    supports: list[float] = field(default_factory=list)
    resistances: list[float] = field(default_factory=list)

    def is_active(self, timestamp: pd.Timestamp) -> bool:
        return timestamp >= self.active_after

    def is_expired(self, timestamp: pd.Timestamp) -> bool:
        return timestamp > self.expires_at

    def contains_price(self, price: float) -> bool:
        return self.zone_low <= price <= self.zone_high

    @property
    def width(self) -> float:
        return max(0.0, self.zone_high - self.zone_low)


def normalize_timestamp(ts: pd.Timestamp) -> pd.Timestamp:
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")
