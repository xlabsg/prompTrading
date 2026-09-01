"""Broker abstraction exposed to live strategies."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from control_plane.enums import LogLevel, OrderSide
from control_plane.models import TradingConfig
from app.trading_engine.executor import OrderExecutor
from app.trading_engine.logging_utils import log_trading_event

logger = logging.getLogger(__name__)


@dataclass
class RiskBudgetState:
    session_start_equity: float
    today_start_equity: float
    peak_equity: float
    day_key: str
    is_frozen: bool = False
    frozen_reason: str | None = None


class LiveBroker:
    """Manages position targets and order placement for live strategies."""

    def __init__(
        self,
        *,
        strategy_id: str,
        session_id: str,
        config: TradingConfig,
        okx_client,
    ) -> None:
        self.strategy_id = strategy_id
        self.session_id = session_id
        self.config = config
        self._okx_client = okx_client
        self._order_executor: Optional[OrderExecutor] = None
        self._db: Optional[Session] = None
        self._lock = threading.Lock()
        self._last_price: dict[str, float] = {}
        self._risk_state: RiskBudgetState | None = None
        self._last_risk_notification_reason: str | None = None

    def attach(self, order_executor: OrderExecutor, db: Session) -> None:
        """Attach thread-local resources before invoking the strategy."""

        with self._lock:
            self._order_executor = order_executor
            self._db = db

    def detach(self) -> None:
        with self._lock:
            self._order_executor = None
            self._db = None

    # ------------------------------------------------------------------
    # Strategy-facing helpers
    # ------------------------------------------------------------------
    def set_target_allocation(
        self,
        target: float,
        *,
        reason: str | None = None,
        symbol: Optional[str] = None,
    ) -> None:
        order_executor, db = self._ensure_resources()
        symbol = symbol or self.config.symbol
        target = float(target)
        if target > 1.0:
            target = 1.0
        if target < -1.0:
            target = -1.0

        try:
            equity = self._fetch_equity_usd()
            price = self.last_price(symbol)
            if price <= 0 or equity <= 0:
                return
            risk = self._get_risk_budget(db, equity=equity)

            max_notional = equity * (self.config.max_position_pct / 100.0)
            positions = self._fetch_positions_snapshot()
            current = positions.get(symbol, {})
            current_long_notional = float(current.get("long_notional") or 0.0)
            current_short_notional = float(current.get("short_notional") or 0.0)
            current_symbol_gross = current_long_notional + current_short_notional
            current_total_gross = sum(float(p.get("gross_notional") or 0.0) for p in positions.values())

            desired_long_notional = max_notional * max(target, 0.0)
            desired_short_notional = max_notional * max(-target, 0.0)
            desired_symbol_gross = desired_long_notional + desired_short_notional

            available = max_notional - (current_total_gross - current_symbol_gross)
            if available <= 0 and desired_symbol_gross > current_symbol_gross:
                return
            if risk and risk.is_frozen and desired_symbol_gross > current_symbol_gross:
                self._maybe_notify_risk_budget(db, reason=risk.frozen_reason or "risk_budget_frozen", equity=equity)
                return

            # Avoid churning on tiny diffs (<2% of desired exposure or <min size).
            desired_size = desired_symbol_gross / price if price > 0 else 0.0
            threshold = max(desired_size * 0.02, 1e-5)

            long_diff_notional = desired_long_notional - current_long_notional
            short_diff_notional = desired_short_notional - current_short_notional

            # Cap increases by available gross headroom.
            inc_notional = max(0.0, long_diff_notional) + max(0.0, short_diff_notional)
            if inc_notional > 0 and available > 0:
                scale = min(1.0, available / inc_notional)
                long_diff_notional = long_diff_notional if long_diff_notional <= 0 else long_diff_notional * scale
                short_diff_notional = short_diff_notional if short_diff_notional <= 0 else short_diff_notional * scale

            if abs(long_diff_notional) / max(price, 1e-9) < threshold and abs(short_diff_notional) / max(price, 1e-9) < threshold:
                return

            if long_diff_notional > 0:
                log_trading_event(
                    db,
                    strategy_id=self.strategy_id,
                    session_id=self.session_id,
                    level=LogLevel.INFO,
                    message="Increasing long exposure",
                    metadata={"target": target, "reason": reason, "symbol": symbol},
                )
                self._maybe_notify_signal(db, side="BUY", symbol=symbol, price=price, reason=reason)
                order_executor.place_market_order(
                    OrderSide.BUY,
                    long_diff_notional / price,
                    symbol=symbol,
                    pos_side="long",
                    reduce_only=False,
                )
            elif long_diff_notional < 0:
                log_trading_event(
                    db,
                    strategy_id=self.strategy_id,
                    session_id=self.session_id,
                    level=LogLevel.INFO,
                    message="Reducing long exposure",
                    metadata={"target": target, "reason": reason, "symbol": symbol},
                )
                self._maybe_notify_signal(db, side="SELL", symbol=symbol, price=price, reason=reason)
                order_executor.place_market_order(
                    OrderSide.SELL,
                    abs(long_diff_notional) / price,
                    symbol=symbol,
                    pos_side="long",
                    reduce_only=True,
                )

            if short_diff_notional > 0:
                log_trading_event(
                    db,
                    strategy_id=self.strategy_id,
                    session_id=self.session_id,
                    level=LogLevel.INFO,
                    message="Increasing short exposure",
                    metadata={"target": target, "reason": reason, "symbol": symbol},
                )
                self._maybe_notify_signal(db, side="SELL", symbol=symbol, price=price, reason=reason)
                order_executor.place_market_order(
                    OrderSide.SELL,
                    short_diff_notional / price,
                    symbol=symbol,
                    pos_side="short",
                    reduce_only=False,
                )
            elif short_diff_notional < 0:
                log_trading_event(
                    db,
                    strategy_id=self.strategy_id,
                    session_id=self.session_id,
                    level=LogLevel.INFO,
                    message="Reducing short exposure",
                    metadata={"target": target, "reason": reason, "symbol": symbol},
                )
                self._maybe_notify_signal(db, side="BUY", symbol=symbol, price=price, reason=reason)
                order_executor.place_market_order(
                    OrderSide.BUY,
                    abs(short_diff_notional) / price,
                    symbol=symbol,
                    pos_side="short",
                    reduce_only=True,
                )
        except Exception as exc:  # pragma: no cover - relies on live exchange
            logger.error("Failed to adjust allocation: %s", exc, exc_info=True)
            log_trading_event(
                db,
                strategy_id=self.strategy_id,
                session_id=self.session_id,
                level=LogLevel.ERROR,
                message="Allocation adjustment failed",
                metadata={"error": str(exc)},
            )

    def market_order(
        self,
        side: str,
        size: float,
        *,
        reason: str | None = None,
        symbol: Optional[str] = None,
    ) -> None:
        order_executor, db = self._ensure_resources()
        if size <= 0:
            return
        normalized_side = side.lower()
        if normalized_side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        symbol = symbol or self.config.symbol

        try:
            price = self.last_price(symbol)
            equity = self._fetch_equity_usd()
            risk = self._get_risk_budget(db, equity=equity) if equity > 0 else None
            if risk and risk.is_frozen:
                self._maybe_notify_risk_budget(db, reason=risk.frozen_reason or "risk_budget_frozen", equity=equity)
                if normalized_side != "sell":
                    return
            log_trading_event(
                db,
                strategy_id=self.strategy_id,
                session_id=self.session_id,
                level=LogLevel.INFO,
                message="Submitting discretionary market order",
                metadata={"side": normalized_side, "size": size, "reason": reason, "symbol": symbol},
            )
            self._maybe_notify_signal(
                db,
                side=normalized_side.upper(),
                symbol=symbol,
                price=price,
                reason=reason,
            )
            order_executor.place_market_order(
                OrderSide.BUY if normalized_side == "buy" else OrderSide.SELL,
                size,
                symbol=symbol,
                pos_side="long",
                reduce_only=normalized_side == "sell",
            )
        except Exception as exc:
            logger.error("market_order failed: %s", exc, exc_info=True)
            log_trading_event(
                db,
                strategy_id=self.strategy_id,
                session_id=self.session_id,
                level=LogLevel.ERROR,
                message="Market order failed",
                metadata={"side": normalized_side, "size": size, "error": str(exc)},
            )

    def current_position(self, symbol: Optional[str] = None) -> float:
        symbol = symbol or self.config.symbol
        try:
            positions = self._okx_client.get_positions()
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to fetch positions: %s", exc)
            return 0.0

        total = 0.0
        for pos in positions:
            if pos.inst_id != symbol:
                continue
            try:
                size = float(pos.pos or 0)
            except (TypeError, ValueError):
                size = 0.0
            total += abs(size)
        return total

    def last_price(self, symbol: Optional[str] = None) -> float:
        symbol = symbol or self.config.symbol
        cached = self._last_price.get(symbol)
        if cached and cached > 0:
            return cached
        try:
            ticker = self._okx_client.get_ticker(symbol)
            last = float(ticker.get("last", 0.0))
            if last > 0:
                self._last_price[symbol] = last
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to fetch ticker: %s", exc)
            return 0.0
        return self._last_price.get(symbol, 0.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _maybe_notify_signal(
        self,
        db: Session,
        *,
        side: str,
        symbol: str,
        price: float,
        reason: str | None,
    ) -> None:
        try:
            from control_plane.models import StrategySubscription
            from app.services.telegram import send_signal_notification

            sub = (
                db.query(StrategySubscription)
                .filter_by(strategy_id=self.strategy_id, status="active")
                .first()
            )
            if not sub or not sub.telegram_config:
                return
            send_signal_notification(
                db,
                subscription_id=sub.id,
                signal_info={
                    "symbol": symbol,
                    "side": side,
                    "price": price,
                    "reason": reason,
                },
                config=sub.telegram_config,
            )
        except Exception:
            return

    def _get_risk_budget(self, db: Session, *, equity: float) -> RiskBudgetState | None:
        """Update and return the current in-memory risk budget state (if configured)."""
        try:
            from control_plane.models import StrategySubscription

            sub = (
                db.query(StrategySubscription)
                .filter_by(strategy_id=self.strategy_id, status="active")
                .first()
            )
            if not sub:
                return None
            user_cfg = sub.user_config or {}
            budget = user_cfg.get("risk_budget") if isinstance(user_cfg, dict) else None
            if not isinstance(budget, dict):
                return None

            max_daily_loss_pct = float(budget.get("max_daily_loss_pct", 0.0))
            max_drawdown_pct = float(budget.get("max_drawdown_pct", 0.0))
            freeze_on_breach = bool(budget.get("freeze_on_breach", True))
            if max_daily_loss_pct <= 0 and max_drawdown_pct <= 0:
                return None

            now = datetime.now(timezone.utc)
            day_key = now.strftime("%Y-%m-%d")
            if self._risk_state is None:
                self._risk_state = RiskBudgetState(
                    session_start_equity=float(equity),
                    today_start_equity=float(equity),
                    peak_equity=float(equity),
                    day_key=day_key,
                )
            elif self._risk_state.day_key != day_key:
                self._risk_state.today_start_equity = float(equity)
                self._risk_state.day_key = day_key
                self._risk_state.is_frozen = False
                self._risk_state.frozen_reason = None
                self._last_risk_notification_reason = None

            if float(equity) > float(self._risk_state.peak_equity):
                self._risk_state.peak_equity = float(equity)

            if not freeze_on_breach:
                return self._risk_state

            if max_daily_loss_pct > 0 and self._risk_state.today_start_equity > 0:
                daily_pnl_pct = (float(equity) / float(self._risk_state.today_start_equity) - 1.0) * 100.0
                if daily_pnl_pct <= -abs(max_daily_loss_pct):
                    self._risk_state.is_frozen = True
                    self._risk_state.frozen_reason = f"max_daily_loss_pct_breached:{daily_pnl_pct:.2f}%"
                    return self._risk_state

            if max_drawdown_pct > 0 and self._risk_state.peak_equity > 0:
                dd_pct = (1.0 - float(equity) / float(self._risk_state.peak_equity)) * 100.0
                if dd_pct >= abs(max_drawdown_pct):
                    self._risk_state.is_frozen = True
                    self._risk_state.frozen_reason = f"max_drawdown_pct_breached:{dd_pct:.2f}%"
                    return self._risk_state

            self._risk_state.is_frozen = False
            self._risk_state.frozen_reason = None
            return self._risk_state
        except Exception:
            return None

    def _maybe_notify_risk_budget(self, db: Session, *, reason: str, equity: float) -> None:
        if not reason:
            return
        if self._last_risk_notification_reason == reason:
            return
        self._last_risk_notification_reason = reason
        try:
            from control_plane.models import StrategySubscription
            from app.services.telegram import send_error_notification

            sub = (
                db.query(StrategySubscription)
                .filter_by(strategy_id=self.strategy_id, status="active")
                .first()
            )
            if not sub or not sub.telegram_config:
                return
            send_error_notification(
                db,
                subscription_id=sub.id,
                error_message=f"Risk budget blocked new exposure: {reason} (equity≈{equity:.2f})",
                config=sub.telegram_config,
            )
        except Exception:
            return

    def _ensure_resources(self) -> tuple[OrderExecutor, Session]:
        with self._lock:
            if not self._order_executor or not self._db:
                raise RuntimeError("Broker resources not attached")
            return self._order_executor, self._db

    def _fetch_equity_usd(self) -> float:
        try:
            balances = self._okx_client.get_balance()
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to fetch balance: %s", exc)
            return 0.0
        total = 0.0
        for bal in balances:
            try:
                eq = float(getattr(bal, "eqUsd", None) or bal.eq or 0)
            except (TypeError, ValueError):
                eq = 0.0
            total += max(eq, 0.0)
        return total

    def _fetch_positions_snapshot(self) -> dict[str, dict[str, float]]:
        symbols = set(self.config.symbols or [self.config.symbol])
        try:
            positions = self._okx_client.get_positions()
        except Exception:  # pragma: no cover
            return {}
        snapshot: dict[str, dict[str, float]] = {}
        for pos in positions:
            if pos.inst_id not in symbols:
                continue
            side = (pos.pos_side or "net").lower()
            try:
                size = float(pos.pos or 0.0)
            except (TypeError, ValueError):
                size = 0.0
            try:
                mark_px = float(pos.mark_px or pos.avg_px or 0.0)
            except (TypeError, ValueError):
                mark_px = 0.0
            notional = abs(size) * max(mark_px, 0.0)
            entry = snapshot.setdefault(
                pos.inst_id,
                {"long_notional": 0.0, "short_notional": 0.0, "gross_notional": 0.0},
            )
            if side == "short" or (side == "net" and size < 0):
                entry["short_notional"] += notional
            else:
                entry["long_notional"] += notional
            entry["gross_notional"] = entry["long_notional"] + entry["short_notional"]
        return snapshot
