"""
Generate realistic performance data for strategy templates.

This module creates synthetic but realistic backtest results and signals
for strategy templates, with strategy-aware patterns that vary by type
(momentum, mean-reversion, grid, etc.).
"""

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from control_plane.models import (
    StrategyTemplate,
    TemplatePerformanceRun,
    TemplateSignal,
)


class TemplatePerformanceGenerator:
    """Generates synthetic but realistic performance data."""

    # Strategy type profiles (affects data patterns)
    STRATEGY_PROFILES = {
        "momentum": {
            "avg_return_range": (20, 60),
            "sharpe_range": (1.5, 3.5),
            "drawdown_range": (-8, -20),
            "win_rate_range": (55, 70),
            "trade_frequency": "high",
        },
        "mean-reversion": {
            "avg_return_range": (15, 40),
            "sharpe_range": (1.2, 2.8),
            "drawdown_range": (-5, -15),
            "win_rate_range": (60, 75),
            "trade_frequency": "medium",
        },
        "trend-following": {
            "avg_return_range": (25, 80),
            "sharpe_range": (1.0, 3.0),
            "drawdown_range": (-10, -25),
            "win_rate_range": (45, 60),
            "trade_frequency": "low",
        },
        "scalping": {
            "avg_return_range": (10, 35),
            "sharpe_range": (0.8, 2.5),
            "drawdown_range": (-3, -10),
            "win_rate_range": (50, 65),
            "trade_frequency": "very_high",
        },
        "grid": {
            "avg_return_range": (8, 25),
            "sharpe_range": (0.5, 2.0),
            "drawdown_range": (-2, -8),
            "win_rate_range": (65, 80),
            "trade_frequency": "very_high",
        },
    }

    @classmethod
    def detect_strategy_profile(cls, template: StrategyTemplate) -> str:
        """Detect strategy type from tags and description."""
        text = f"{template.name} {template.description or ''} {' '.join(template.tags or [])}".lower()

        if any(kw in text for kw in ["momentum", "breakout", "ma crossover", "trend", "moving average"]):
            return "momentum"
        elif any(kw in text for kw in ["mean reversion", "rsi", "oversold", "overbought", "bollinger"]):
            return "mean-reversion"
        elif any(kw in text for kw in ["grid", "range"]):
            return "grid"
        elif "scalp" in text:
            return "scalping"
        else:
            return "trend-following"  # Default

    @classmethod
    def generate_backtest_metrics(
        cls,
        profile: str,
        days: int = 90,
        base_quality: float = 50.0,
    ) -> dict[str, Any]:
        """Generate realistic backtest metrics."""
        profile_config = cls.STRATEGY_PROFILES[profile]

        # Convert Decimal to float if needed
        base_quality = float(base_quality)

        # Adjust ranges based on quality score (0-100)
        quality_multiplier = base_quality / 50.0

        total_return = random.uniform(*profile_config["avg_return_range"]) * quality_multiplier
        sharpe_ratio = random.uniform(*profile_config["sharpe_range"]) * min(quality_multiplier, 1.5)
        max_drawdown = random.uniform(*profile_config["drawdown_range"])  # Already negative
        win_rate = random.uniform(*profile_config["win_rate_range"])

        # Derive other metrics
        total_trades = int(random.randint(50, 200) * (days / 90))
        winning_trades = int(total_trades * (win_rate / 100))
        losing_trades = total_trades - winning_trades

        avg_win = abs(total_return) / total_trades * 1.5 if total_return > 0 else abs(total_return) / total_trades * 0.8
        avg_loss = abs(total_return) / total_trades * 0.7

        profit_factor = (avg_win * winning_trades) / (avg_loss * losing_trades) if losing_trades > 0 else 2.0

        # Generate equity curve
        equity_curve = cls._generate_equity_curve(
            days=days,
            total_return=total_return,
            max_drawdown=max_drawdown,
        )

        return {
            "total_return": round(total_return, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "max_drawdown": round(max_drawdown, 2),
            "win_rate": round(win_rate, 1),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "avg_trade_pnl": round(total_return / total_trades, 2) if total_trades > 0 else 0,
            "profit_factor": round(profit_factor, 2),
            "equity_curve": equity_curve,
        }

    @classmethod
    def _generate_equity_curve(
        cls,
        days: int,
        total_return: float,
        max_drawdown: float,
    ) -> list[list[int]]:
        """Generate realistic equity curve with random walk and drawdowns."""
        initial_capital = 10000
        points_per_day = 24  # Hourly points
        total_points = days * points_per_day

        curve = []
        current_equity = initial_capital
        timestamp = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

        # Target final value
        target_final = initial_capital * (1 + total_return / 100)

        for i in range(total_points):
            # Progress toward target with random noise
            progress = i / total_points
            target_at_point = initial_capital + (target_final - initial_capital) * progress

            # Add randomness (geometric Brownian motion approximation)
            noise = random.gauss(0, initial_capital * 0.005)

            # Add occasional drawdown
            if random.random() < 0.02:  # 2% chance per point
                drawdown_depth = random.uniform(0, abs(max_drawdown) / 100)
                current_equity *= (1 - drawdown_depth)

            # Smooth recovery
            recovery_rate = 0.1
            current_equity = current_equity * (1 - recovery_rate) + (target_at_point + noise) * recovery_rate

            # Ensure equity stays positive
            current_equity = max(current_equity, initial_capital * 0.5)

            curve.append([timestamp + i * (24 * 3600 * 1000 // points_per_day), round(current_equity, 2)])

        return curve

    @classmethod
    def generate_signals(
        cls,
        template: StrategyTemplate,
        days: int = 90,
        signals_per_day: int = 3,
    ) -> list[dict[str, Any]]:
        """Generate historical signals."""
        profile = cls.detect_strategy_profile(template)
        freq_multiplier = {
            "very_high": 2.0,
            "high": 1.5,
            "medium": 1.0,
            "low": 0.5,
        }.get(cls.STRATEGY_PROFILES[profile]["trade_frequency"], 1.0)

        actual_signals_per_day = int(signals_per_day * freq_multiplier)
        total_signals = days * actual_signals_per_day

        signals = []
        base_time = datetime.now(timezone.utc) - timedelta(days=days)

        # Get symbols from template config or use default
        if template.config_snapshot and isinstance(template.config_snapshot, dict):
            symbols = template.config_snapshot.get("symbols", ["BTC-USDT-SWAP"])
            if isinstance(symbols, str):
                symbols = [symbols]
        else:
            symbols = ["BTC-USDT-SWAP"]

        # Convert OKX format to simpler format if needed
        symbols = [s.replace("-SWAP", "").replace("-", "") for s in symbols]

        for i in range(total_signals):
            signal_time = base_time + timedelta(
                days=random.randint(0, days),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )

            side = "buy" if random.random() > 0.5 else "sell"
            confidence = random.uniform(0.5, 0.95)

            # Simulate outcome (executed signals)
            status = "executed" if confidence > 0.6 else "expired"

            # Generate realistic price based on symbol
            base_price = random.uniform(30000, 70000) if "BTC" in symbols[0] else random.uniform(1500, 4000)

            signal = {
                "id": str(uuid.uuid4()),
                "template_id": template.id,
                "symbol": random.choice(symbols),
                "side": side,
                "price": round(base_price, 2),
                "confidence": round(confidence, 2),
                "status": status,
                "created_at": signal_time,
            }

            # Add outcome for executed signals
            if status == "executed":
                signal["executed_at"] = signal_time + timedelta(hours=random.randint(1, 24))
                signal["entry_price"] = signal["price"]

                # Simulate PnL based on side and randomness
                pnl_pct = random.uniform(-5, 8)
                signal["exit_price"] = round(signal["price"] * (1 + pnl_pct / 100), 2)
                signal["pnl"] = round(pnl_pct, 2)
                signal["hold_duration_hours"] = round(random.uniform(1, 72), 1)

            signals.append(signal)

        return sorted(signals, key=lambda x: x["created_at"])

    @classmethod
    def generate_performance_data(
        cls,
        db: Session,
        template: StrategyTemplate,
        days_history: int = 90,
        run_count: int = 10,
    ) -> tuple[list[TemplatePerformanceRun], list[TemplateSignal]]:
        """Generate complete performance dataset for a template."""
        profile = cls.detect_strategy_profile(template)
        base_quality = 50.0

        # Generate historical backtest runs
        runs = []
        for i in range(run_count):
            # Spread runs over the history period
            days_ago = random.randint(0, days_history)
            run_date = datetime.now(timezone.utc) - timedelta(days=days_ago)

            run = TemplatePerformanceRun(
                id=str(uuid.uuid4()),
                template_id=template.id,
                run_date=run_date,
                exchange="okx",
                symbol="BTC-USDT-SWAP",
                interval="1h",
                start_ms=int((run_date - timedelta(days=days_history)).timestamp() * 1000),
                end_ms=int(run_date.timestamp() * 1000),
                metrics=cls.generate_backtest_metrics(profile, days=days_history, base_quality=base_quality),
                status="succeeded",
            )
            runs.append(run)

        # Generate signals
        signal_data = cls.generate_signals(template, days=days_history, signals_per_day=3)
        signals = []
        for sig_data in signal_data:
            signal = TemplateSignal(
                id=sig_data["id"],
                template_id=sig_data["template_id"],
                symbol=sig_data["symbol"],
                side=sig_data["side"],
                price=sig_data["price"],
                confidence=sig_data["confidence"],
                status=sig_data["status"],
                entry_price=sig_data.get("entry_price"),
                exit_price=sig_data.get("exit_price"),
                pnl=sig_data.get("pnl"),
                hold_duration_hours=sig_data.get("hold_duration_hours"),
                created_at=sig_data["created_at"],
                executed_at=sig_data.get("executed_at"),
            )
            signals.append(signal)

        return runs, signals
