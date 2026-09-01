from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from strategy_templates.shared.pivots import detect_pivots


class LevelType(Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"


@dataclass
class SupportResistanceLevel:
    price: float
    level_type: LevelType
    strength: int = 1
    last_touch_index: int = 0


@dataclass
class DynamicTPSL:
    entry_price: float
    take_profit: float
    stop_loss: float
    risk_reward_ratio: float
    support_level: float | None = None
    resistance_level: float | None = None
    is_valid: bool = True
    rejection_reason: str = ""

    @property
    def risk_pct(self) -> float:
        return abs(self.entry_price - self.stop_loss) / self.entry_price * 100

    @property
    def reward_pct(self) -> float:
        return abs(self.take_profit - self.entry_price) / self.entry_price * 100


class SupportResistanceCalculator:
    def __init__(
        self,
        lookback_bars: int = 50,
        pivot_period: int = 5,
        buffer_pct: float = 0.001,
        min_risk_reward: float = 1.0,
        fallback_sl_pct: float = 0.01,
        fallback_tp_pct: float = 0.02,
        min_sl_pct: float = 0.005,
    ):
        self.lookback_bars = lookback_bars
        self.pivot_period = pivot_period
        self.buffer_pct = buffer_pct
        self.min_risk_reward = min_risk_reward
        self.fallback_sl_pct = fallback_sl_pct
        self.fallback_tp_pct = fallback_tp_pct
        self.min_sl_pct = min_sl_pct

    def find_levels(
        self,
        data: pd.DataFrame,
        current_index: int,
        reference_price: float | None = None,
    ) -> tuple[list[SupportResistanceLevel], list[SupportResistanceLevel]]:
        start_idx = max(0, current_index - self.lookback_bars)
        window_data = data.iloc[start_idx : current_index + 1]

        if len(window_data) < self.pivot_period * 2 + 1:
            return [], []

        pivots = detect_pivots(
            close=window_data["close"].reset_index(drop=True),
            timestamps=window_data["datetime"].reset_index(drop=True),
            period=self.pivot_period,
        )

        ref_price = (
            reference_price if reference_price is not None else data.iloc[current_index]["close"]
        )

        supports: list[SupportResistanceLevel] = []
        resistances: list[SupportResistanceLevel] = []

        for pivot in pivots:
            if pivot.kind == "low" and pivot.price < ref_price:
                supports.append(
                    SupportResistanceLevel(
                        price=pivot.price,
                        level_type=LevelType.SUPPORT,
                        strength=1,
                        last_touch_index=start_idx + pivot.index,
                    )
                )
            elif pivot.kind == "high" and pivot.price > ref_price:
                resistances.append(
                    SupportResistanceLevel(
                        price=pivot.price,
                        level_type=LevelType.RESISTANCE,
                        strength=1,
                        last_touch_index=start_idx + pivot.index,
                    )
                )

        recent_high = window_data["high"].max()
        recent_low = window_data["low"].min()

        if recent_high > ref_price:
            if not any(abs(r.price - recent_high) / recent_high < 0.001 for r in resistances):
                resistances.append(
                    SupportResistanceLevel(
                        price=recent_high,
                        level_type=LevelType.RESISTANCE,
                        strength=2,
                        last_touch_index=current_index,
                    )
                )

        if recent_low < ref_price:
            if not any(abs(s.price - recent_low) / recent_low < 0.001 for s in supports):
                supports.append(
                    SupportResistanceLevel(
                        price=recent_low,
                        level_type=LevelType.SUPPORT,
                        strength=2,
                        last_touch_index=current_index,
                    )
                )

        supports.sort(key=lambda x: ref_price - x.price)
        resistances.sort(key=lambda x: x.price - ref_price)

        return supports, resistances

    def calculate_tpsl(
        self,
        data: pd.DataFrame,
        entry_index: int,
        direction: str,
        entry_price: float | None = None,
    ) -> DynamicTPSL:
        if entry_price is None:
            entry_price = data.iloc[entry_index]["close"]

        supports, resistances = self.find_levels(data, entry_index, reference_price=entry_price)

        if direction == "long":
            support = supports[0].price if supports else entry_price * (1 - self.fallback_sl_pct)
            resistance = (
                resistances[0].price if resistances else entry_price * (1 + self.fallback_tp_pct)
            )

            stop_loss = support * (1 - self.buffer_pct)
            take_profit = resistance * (1 - self.buffer_pct)

            if (entry_price - stop_loss) / entry_price < self.min_sl_pct:
                stop_loss = entry_price * (1 - self.min_sl_pct)

        else:
            resistance = (
                resistances[0].price if resistances else entry_price * (1 + self.fallback_sl_pct)
            )
            support = supports[0].price if supports else entry_price * (1 - self.fallback_tp_pct)

            stop_loss = resistance * (1 + self.buffer_pct)
            take_profit = support * (1 + self.buffer_pct)

            if (stop_loss - entry_price) / entry_price < self.min_sl_pct:
                stop_loss = entry_price * (1 + self.min_sl_pct)

        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        rr_ratio = reward / risk if risk > 0 else 0

        is_valid = rr_ratio >= self.min_risk_reward
        reason = "" if is_valid else f"RR {rr_ratio:.2f} < min {self.min_risk_reward}"

        return DynamicTPSL(
            entry_price=entry_price,
            take_profit=take_profit,
            stop_loss=stop_loss,
            risk_reward_ratio=rr_ratio,
            support_level=support if direction == "long" else support,
            resistance_level=resistance if direction == "long" else resistance,
            is_valid=is_valid,
            rejection_reason=reason,
        )
