"""In-memory simulated paper broker adhering to the live_trading_sdk.Broker protocol.

Enables risk-free simulated trading and shadow verification against live market data feeds.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .strategy import Broker

logger = logging.getLogger(__name__)


@dataclass
class PaperTrade:
    timestamp: datetime
    side: str
    size: float
    price: float
    fee: float
    reason: str | None
    realized_pnl: float = 0.0


class PaperBroker(Broker):
    """Realistic in-memory simulated broker for paper trading & shadow validation."""

    def __init__(
        self,
        initial_cash: float = 10_000.0,
        fee_rate: float = 0.0004,
        slippage_bps: float = 2.0,
    ) -> None:
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.fee_rate = float(fee_rate)
        self.slippage_bps = float(slippage_bps)

        self._position: float = 0.0
        self._last_price: float = 0.0
        self._avg_entry_price: float = 0.0
        self._realized_pnl: float = 0.0
        self.trades: list[PaperTrade] = []

    def set_target_allocation(self, target: float, *, reason: str | None = None) -> None:
        """Target exposure in range [-1.0, 1.0]."""
        target = max(-1.0, min(1.0, float(target)))
        if self._last_price <= 0:
            logger.warning("PaperBroker: Cannot set target allocation before price is known.")
            return

        equity = self.equity()
        target_value = equity * target
        current_value = self._position * self._last_price
        diff_value = target_value - current_value

        if abs(diff_value) < 1e-4:
            return

        side = "buy" if diff_value > 0 else "sell"
        size = abs(diff_value) / self._last_price
        self.market_order(side=side, size=size, reason=reason)

    def market_order(self, side: str, size: float, *, reason: str | None = None) -> None:
        """Execute an immediate simulated market order with slippage and fees."""
        side = side.lower().strip()
        if side not in ("buy", "sell"):
            raise ValueError(f"Invalid order side: {side}")

        if size <= 0 or self._last_price <= 0:
            return

        # Apply slippage: buy pays more, sell receives less
        slippage_mult = 1.0 + (self.slippage_bps / 10_000.0 if side == "buy" else -self.slippage_bps / 10_000.0)
        execution_price = self._last_price * slippage_mult
        order_value = size * execution_price
        fee = order_value * self.fee_rate

        realized_pnl = 0.0
        signed_size = size if side == "buy" else -size

        # Check closing/reducing existing position
        if self._position != 0.0 and (self._position > 0) != (signed_size > 0):
            closed_size = min(abs(self._position), abs(signed_size))
            direction = 1.0 if self._position > 0 else -1.0
            realized_pnl = closed_size * (execution_price - self._avg_entry_price) * direction

        new_position = self._position + signed_size
        if abs(new_position) < 1e-9:
            new_position = 0.0
            self._avg_entry_price = 0.0
        elif (self._position >= 0 and signed_size > 0) or (self._position <= 0 and signed_size < 0):
            # Increasing position: update weighted entry price
            total_size = abs(self._position) + abs(signed_size)
            self._avg_entry_price = (
                (abs(self._position) * self._avg_entry_price + abs(signed_size) * execution_price)
                / total_size
            )
        elif abs(new_position) > 0:
            # Flipped position
            self._avg_entry_price = execution_price

        self._position = new_position
        self.cash = self.cash - (order_value if side == "buy" else -order_value) - fee
        self._realized_pnl += (realized_pnl - fee)

        trade = PaperTrade(
            timestamp=datetime.now(timezone.utc),
            side=side,
            size=size,
            price=execution_price,
            fee=fee,
            reason=reason,
            realized_pnl=realized_pnl - fee,
        )
        self.trades.append(trade)

    def current_position(self) -> float:
        return self._position

    def last_price(self) -> float:
        return self._last_price

    def update_price(self, price: float) -> None:
        """Called upon new bar or tick arrival to mark market price."""
        if price > 0:
            self._last_price = float(price)

    def equity(self) -> float:
        """Total virtual equity: cash + current position market value."""
        return self.cash + (self._position * self._last_price)

    def unrealized_pnl(self) -> float:
        if self._position == 0 or self._last_price <= 0:
            return 0.0
        return self._position * (self._last_price - self._avg_entry_price)

    def total_return(self) -> float:
        if self.initial_cash <= 0:
            return 0.0
        return (self.equity() - self.initial_cash) / self.initial_cash

    def state_summary(self) -> dict[str, Any]:
        return {
            "initial_cash": self.initial_cash,
            "cash": round(self.cash, 2),
            "equity": round(self.equity(), 2),
            "position": round(self._position, 6),
            "last_price": self._last_price,
            "unrealized_pnl": round(self.unrealized_pnl(), 2),
            "realized_pnl": round(self._realized_pnl, 2),
            "total_return": round(self.total_return(), 4),
            "trades_count": len(self.trades),
        }
