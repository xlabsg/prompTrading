"""
Scheduled job to run backtests for all strategy templates.

This script can be run as a cron job or scheduled task to:
1. Fetch latest market data
2. Run backtests for all templates
3. Save results to database
4. Generate signals for current market conditions
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Any, Optional
import uuid

# Add packages to path
sys.path.insert(0, "/app/packages")
sys.path.insert(0, "/app/packages/data/data")
sys.path.insert(0, "/app/packages/backtest")

from control_plane.db import create_db_engine, create_session_factory
from control_plane.models import StrategyTemplate, TemplatePerformanceRun
from control_plane.enums import StrategyTemplateType

from data.okx import CandlesRequest, fetch_candles, interval_to_okx_bar
from backtest.vectorized import BacktestConfig, run_backtest

import pandas as pd
import numpy as np


def _fmt_percent(value: Any, decimals: int = 2, *, signed: bool = True) -> str:
    if value is None:
        return "N/A"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if not np.isfinite(numeric):
        return "N/A"
    prefix = "+" if signed and numeric > 0 else ""
    return f"{prefix}{numeric:.{decimals}f}%"


@dataclass
class BacktestResult:
    """Result of a backtest run."""
    template_id: str
    template_name: str
    exchange: str
    symbol: str
    interval: str
    metrics: dict[str, Any]
    signals: list[dict[str, Any]]
    status: str = "succeeded"
    error_message: Optional[str] = None


class TemplateBacktestScheduler:
    """Scheduler for running template backtests."""

    def __init__(
        self,
        db_url: str,
        symbols: list[str] = None,
        intervals: list[str] = None,
        days: int = 30,
    ):
        self.db_url = db_url
        self.symbols = symbols or ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
        self.intervals = intervals or ["1h", "4h"]
        self.days = days
        self.engine = create_db_engine(db_url)
        self.session_factory = create_session_factory(self.engine)

    def run_all_backtests(self) -> list[BacktestResult]:
        """Run backtests for all public templates."""
        results = []

        with self.session_factory() as db:
            # Get all public templates
            templates = db.query(StrategyTemplate).filter_by(
                is_public=True,
                template_type=StrategyTemplateType.BUILTIN.value,
            ).all()

            print(f"Found {len(templates)} templates to backtest")

            for template in templates:
                for symbol in self.symbols:
                    for interval in self.intervals:
                        result = self.run_single_backtest(
                            template, symbol, interval, db
                        )
                        if result:
                            results.append(result)

        return results

    def run_single_backtest(
        self,
        template: StrategyTemplate,
        symbol: str,
        interval: str,
        db,
    ) -> Optional[BacktestResult]:
        """Run a single backtest for a template."""
        template_id = template.id
        template_name = template.name

        print(f"\nBacktesting {template_name} on {symbol} ({interval})...")

        try:
            # Fetch data
            df = self.fetch_data(symbol, interval)
            if df is None or len(df) == 0:
                return BacktestResult(
                    template_id=template_id,
                    template_name=template_name,
                    exchange="okx",
                    symbol=symbol,
                    interval=interval,
                    metrics={},
                    signals=[],
                    status="no_data",
                )

            # Get config
            config = template.config_snapshot or {}
            score_threshold = config.get("score_threshold", 0.3)
            min_confidence = config.get("min_confidence", 0.5)
            cooldown_bars = config.get("cooldown_bars", 3)
            position_size_pct = config.get("position_size_pct", 0.15)

            # Generate signals using the template's logic
            signals, backtest_result = self.generate_signals_and_backtest(
                df,
                score_threshold=score_threshold,
                min_confidence=min_confidence,
                cooldown_bars=cooldown_bars,
                position_size_pct=position_size_pct,
            )

            # Save to database
            self.save_performance_run(
                db, template_id, symbol, interval, backtest_result, signals
            )

            print(
                "  Result: "
                f"Return={_fmt_percent(backtest_result.get('total_return'))}, "
                f"Trades={backtest_result.get('total_trades')}, "
                f"WinRate={_fmt_percent(backtest_result.get('win_rate'), decimals=1, signed=False)}"
            )

            return BacktestResult(
                template_id=template_id,
                template_name=template_name,
                exchange="okx",
                symbol=symbol,
                interval=interval,
                metrics=backtest_result,
                signals=signals,
                status="succeeded",
            )

        except Exception as e:
            print(f"  Error: {e}")
            return BacktestResult(
                template_id=template_id,
                template_name=template_name,
                exchange="okx",
                symbol=symbol,
                interval=interval,
                metrics={},
                signals=[],
                status="failed",
                error_message=str(e),
            )

    def fetch_data(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        """Fetch market data."""
        interval_minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
        mins_per_bar = interval_minutes.get(interval, 60)
        bars_needed = self.days * 24 * 60 // mins_per_bar + 100

        bar = interval_to_okx_bar(interval)
        df = fetch_candles(
            CandlesRequest(
                inst_id=symbol,
                bar=bar,
                limit=min(bars_needed, 1000),
            )
        )
        return df

    def generate_signals_and_backtest(
        self,
        df: pd.DataFrame,
        score_threshold: float = 0.3,
        min_confidence: float = 0.5,
        cooldown_bars: int = 3,
        position_size_pct: float = 0.15,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Generate signals and run backtest.

        Uses candlestick data to estimate order flow and generate signals.
        Implements cooldown to avoid duplicate signals.
        """
        n = len(df)

        # Calculate indicators
        df = df.copy()
        df["body"] = df["close"] - df["open"]
        df["body_abs"] = df["body"].abs()
        df["direction"] = np.where(df["body"] > 0, 1, np.where(df["body"] < 0, -1, 0))
        df["direction_strength"] = df["direction"] * df["body_abs"]

        # Flow windows
        flow_windows = [5, 10, 20]
        flow_weights = [1.0, 0.6, 0.4]

        for i, window in enumerate(flow_windows):
            df[f"flow_sum_{window}"] = df["direction_strength"].rolling(window=window).sum()
            df[f"flow_total_{window}"] = df["body_abs"].rolling(window=window).sum()
            total = df[f"flow_total_{window}"].replace(0, 1e-10)
            df[f"flow_imbalance_{window}"] = (df[f"flow_sum_{window}"] / total).fillna(0)
            df[f"flow_score_{window}"] = df[f"flow_imbalance_{window}"] * flow_weights[i]

        flow_cols = [f"flow_score_{w}" for w in flow_windows]
        df["composite_flow"] = df[flow_cols].sum(axis=1)
        total_weight = sum(flow_weights)
        df["composite_flow"] = df["composite_flow"] / total_weight

        # Generate signals with cooldown
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        target_weights = np.zeros(n, dtype=np.float64)

        position = 0
        entry_idx = 0
        cooldown_remaining = 0
        signals = []

        for i in range(n):
            if cooldown_remaining > 0:
                cooldown_remaining -= 1

            flow_score = df["composite_flow"].iloc[i]
            confidence = min(abs(flow_score) * 0.5 + 0.3, 1.0)

            direction = "neutral"
            if cooldown_remaining == 0:
                if flow_score > score_threshold and confidence >= min_confidence:
                    direction = "long"
                elif flow_score < -score_threshold and confidence >= min_confidence:
                    direction = "short"

            if position == 0 and direction != "neutral":
                if direction == "long":
                    entries[i] = True
                    position = 1
                    entry_idx = i
                    signals.append({
                        "timestamp": int(df["timestamp"].iloc[i]),
                        "direction": "long",
                        "price": float(df["close"].iloc[i]),
                        "score": float(flow_score),
                        "confidence": float(confidence),
                    })
                else:
                    entries[i] = True
                    position = -1
                    entry_idx = i
                    signals.append({
                        "timestamp": int(df["timestamp"].iloc[i]),
                        "direction": "short",
                        "price": float(df["close"].iloc[i]),
                        "score": float(flow_score),
                        "confidence": float(confidence),
                    })
            elif position != 0:
                # Time exit after 10 bars
                if i - entry_idx >= 10:
                    exits[i] = True
                    signals.append({
                        "timestamp": int(df["timestamp"].iloc[i]),
                        "direction": "exit",
                        "reason": "time_exit",
                    })
                    position = 0
                    cooldown_remaining = cooldown_bars

            target_weights[i] = position * position_size_pct

        # Run backtest
        config = BacktestConfig(initial_cash=10000.0, fee_rate=0.0004)
        result = run_backtest(
            data=df,
            signals={
                "entries": entries,
                "exits": exits,
                "target_weights": target_weights,
            },
            interval="1h",
            config=config,
        )

        metrics = result.metrics
        metrics["equity_curve"] = result.equity["equity"].tolist()

        return signals, metrics

    def save_performance_run(
        self,
        db,
        template_id: str,
        symbol: str,
        interval: str,
        metrics: dict[str, Any],
        signals: list[dict[str, Any]],
    ):
        """Save backtest result to database."""
        # Check if run exists for today
        today = datetime.now(timezone.utc).date()
        existing = db.query(TemplatePerformanceRun).filter(
            TemplatePerformanceRun.template_id == template_id,
            TemplatePerformanceRun.symbol == symbol,
            TemplatePerformanceRun.interval == interval,
            TemplatePerformanceRun.run_date >= datetime(today.year, today.month, today.day, tzinfo=timezone.utc),
        ).first()

        if existing:
            # Update existing record
            existing.metrics = metrics
            existing.status = "succeeded"
            print("  Updated existing record")
        else:
            # Create new record
            run = TemplatePerformanceRun(
                id=str(uuid.uuid4()),
                template_id=template_id,
                run_date=datetime.now(timezone.utc),
                exchange="okx",
                symbol=symbol,
                interval=interval,
                metrics=metrics,
                status="succeeded",
            )
            db.add(run)
            print("  Created new record")

        db.commit()


def run_scheduled_backtests():
    """Main function to run scheduled backtests."""
    from app.settings import settings

    print(f"\n{'='*60}")
    print("Scheduled Template Backtest Job")
    print(f"Started at: {datetime.now(timezone.utc)}")
    print(f"{'='*60}\n")

    scheduler = TemplateBacktestScheduler(
        db_url=settings.db_url,
        symbols=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
        intervals=["1h", "4h"],
        days=30,
    )

    results = scheduler.run_all_backtests()

    # Summary
    succeeded = [r for r in results if r.status == "succeeded"]
    failed = [r for r in results if r.status == "failed"]
    no_data = [r for r in results if r.status == "no_data"]

    print(f"\n{'='*60}")
    print("Backtest Job Summary")
    print(f"{'='*60}")
    print(f"Total runs: {len(results)}")
    print(f"  Succeeded: {len(succeeded)}")
    print(f"  Failed: {len(failed)}")
    print(f"  No data: {len(no_data)}")

    if succeeded:
        returns = [
            r.metrics.get("total_return")
            for r in succeeded
            if r.metrics and r.metrics.get("total_return") is not None
        ]
        trades = [
            r.metrics.get("total_trades")
            for r in succeeded
            if r.metrics and r.metrics.get("total_trades") is not None
        ]
        avg_return = float(np.mean(returns)) if returns else 0.0
        avg_trades = float(np.mean(trades)) if trades else 0.0
        print("\nAverage metrics across successful runs:")
        print(f"  Avg Return: {_fmt_percent(avg_return)}")
        print(f"  Avg Trades: {avg_trades:.0f}")

    print(f"\nCompleted at: {datetime.now(timezone.utc)}")
    print(f"{'='*60}\n")

    return results


def generate_current_signals(template_name: str, symbol: str = "BTC-USDT-SWAP", interval: str = "1h"):
    """Generate current trading signals for a template."""
    from control_plane.db import create_session_factory
    from control_plane.models import StrategyTemplate
    from control_plane.enums import StrategyTemplateType
    from app.settings import settings

    engine = create_db_engine(settings.db_url)
    session_factory = create_session_factory(engine)

    with session_factory() as db:
        template = db.query(StrategyTemplate).filter_by(
            name=template_name,
            template_type=StrategyTemplateType.BUILTIN.value,
        ).first()

        if not template:
            print(f"Template '{template_name}' not found")
            return None

        # Fetch latest data
        scheduler = TemplateBacktestScheduler(settings.db_url)
        df = scheduler.fetch_data(symbol, interval)

        if df is None or len(df) == 0:
            print(f"No data available for {symbol}")
            return None

        # Get config
        config = template.config_snapshot or {}
        score_threshold = config.get("score_threshold", 0.3)
        min_confidence = config.get("min_confidence", 0.5)

        # Generate signals
        _, metrics = scheduler.generate_signals_and_backtest(
            df,
            score_threshold=score_threshold,
            min_confidence=min_confidence,
        )

        # Get latest signal
        flow_cols = [c for c in df.columns if "flow" in c.lower() or "imbalance" in c.lower()]
        if flow_cols:
            latest_flow = df[flow_cols[-1]].iloc[-1]
            direction = "long" if latest_flow > 0.3 else ("short" if latest_flow < -0.3 else "neutral")

            return {
                "template_id": template.id,
                "template_name": template_name,
                "symbol": symbol,
                "interval": interval,
                "direction": direction,
                "flow_score": float(latest_flow),
                "timestamp": int(df["timestamp"].iloc[-1]),
                "price": float(df["close"].iloc[-1]),
                "metrics": metrics,
            }

        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scheduled template backtest job")
    parser.add_argument("--generate-signals", type=str, metavar="TEMPLATE_NAME",
                        help="Generate current signals for a template")
    parser.add_argument("--symbol", type=str, default="BTC-USDT-SWAP",
                        help="Symbol for signal generation")

    args = parser.parse_args()

    if args.generate_signals:
        result = generate_current_signals(args.generate_signals, args.symbol)
        if result:
            print(f"\nCurrent Signal for {result['template_name']}:")
            print(f"  Direction: {result['direction']}")
            print(f"  Flow Score: {result['flow_score']:.3f}")
            print(f"  Price: ${result['price']:,.2f}")
    else:
        run_scheduled_backtests()
