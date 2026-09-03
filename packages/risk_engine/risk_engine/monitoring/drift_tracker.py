"""Drift Tracker: Monitors divergence between backtest expectation and real-time execution.

Detects when paper or live trading significantly underperforms historical backtest
distributions, protecting capital from regime shifts or overfitted strategies.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BacktestExpectation:
    expected_sharpe: float
    max_drawdown: float
    win_rate: float
    daily_mean_return: float = 0.001
    daily_volatility: float = 0.02


@dataclass
class DriftStatus:
    z_score: float
    current_return: float
    current_drawdown: float
    is_drifting: bool
    drift_severity: str  # "normal", "moderate", "critical"
    alert_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "z_score": round(self.z_score, 2),
            "current_return": round(self.current_return, 4),
            "current_drawdown": round(self.current_drawdown, 4),
            "is_drifting": self.is_drifting,
            "drift_severity": self.drift_severity,
            "alert_message": self.alert_message,
        }


class DriftTracker:
    """Tracks live/paper execution drift against historical backtest benchmarks."""

    def __init__(
        self,
        expectation: BacktestExpectation,
        z_threshold: float = -2.0,
        drawdown_tolerance_mult: float = 1.25,
    ) -> None:
        self.expectation = expectation
        self.z_threshold = z_threshold
        self.drawdown_tolerance_mult = drawdown_tolerance_mult

        self._peak_equity: float = 0.0
        self._current_equity: float = 0.0
        self._initial_equity: float = 0.0
        self._returns_history: list[float] = []

    def reset(self, initial_equity: float) -> None:
        self._initial_equity = float(initial_equity)
        self._current_equity = float(initial_equity)
        self._peak_equity = float(initial_equity)
        self._returns_history.clear()

    def update_equity(self, current_equity: float) -> DriftStatus:
        """Update current equity and calculate drift metrics."""
        if self._initial_equity <= 0:
            self._initial_equity = current_equity
            self._peak_equity = current_equity

        self._current_equity = current_equity
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity

        total_return = (self._current_equity - self._initial_equity) / max(1e-9, self._initial_equity)
        current_drawdown = (
            (self._peak_equity - self._current_equity) / max(1e-9, self._peak_equity)
            if self._peak_equity > 0
            else 0.0
        )

        n_steps = max(1, len(self._returns_history))
        expected_cum_return = self.expectation.daily_mean_return * n_steps
        expected_cum_vol = self.expectation.daily_volatility * math.sqrt(n_steps)

        # Standardized return drift z-score
        if expected_cum_vol > 1e-6:
            z_score = (total_return - expected_cum_return) / expected_cum_vol
        else:
            z_score = 0.0

        # Drawdown breach check
        max_allowed_dd = abs(self.expectation.max_drawdown) * self.drawdown_tolerance_mult
        dd_breached = current_drawdown > max_allowed_dd and current_drawdown > 0.05

        # Classify drift severity
        is_drifting = False
        drift_severity = "normal"
        alert_msg: str | None = None

        if z_score < -3.0 or (dd_breached and current_drawdown > 0.15):
            is_drifting = True
            drift_severity = "critical"
            alert_msg = (
                f"Critical drift: Current return z-score is {z_score:.2f} and drawdown is {current_drawdown:.1%}, "
                f"exceeding backtest tolerance ({max_allowed_dd:.1%}). Strategy may be overfitted or regime shifted."
            )
        elif z_score < self.z_threshold or dd_breached:
            is_drifting = True
            drift_severity = "moderate"
            alert_msg = (
                f"Moderate drift warning: Performance is drifting below backtest distribution "
                f"(z-score: {z_score:.2f}, drawdown: {current_drawdown:.1%})."
            )

        return DriftStatus(
            z_score=z_score,
            current_return=total_return,
            current_drawdown=current_drawdown,
            is_drifting=is_drifting,
            drift_severity=drift_severity,
            alert_message=alert_msg,
        )

    def record_step_return(self, step_return: float) -> None:
        self._returns_history.append(float(step_return))
