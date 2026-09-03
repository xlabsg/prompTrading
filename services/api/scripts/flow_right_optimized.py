"""
Flow Right Strategy - Candlestick-based backtest with signal generation.

Uses OHLCV candlestick data to estimate order flow and generate signals.
Implements cooldown to avoid duplicate signals.
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import numpy as np

# Add packages to path
sys.path.insert(0, "/app/packages/data/data")
sys.path.insert(0, "/app/packages/backtest")

from data.okx import CandlesRequest, fetch_candles, interval_to_okx_bar
from backtest.vectorized import BacktestConfig, run_backtest


@dataclass
class BacktestArgs:
    """Arguments for backtest."""
    days: int = 30
    symbol: str = "BTC-USDT-SWAP"
    interval: str = "1h"
    initial_cash: float = 10000.0
    fee_rate: float = 0.0004


@dataclass
class FlowSignal:
    """Flow trading signal."""
    direction: str  # "long" or "short" or "neutral"
    score: float
    confidence: float  # 0-1
    reason: str


class FlowRightBacktest:
    """Flow Right strategy backtest using candlestick data."""

    def __init__(
        self,
        symbol: str = "BTC-USDT-SWAP",
        interval: str = "1h",
        # Optimized parameters
        score_threshold: float = 0.5,  # Higher threshold = fewer signals
        min_confidence: float = 0.6,  # Minimum confidence to enter
        atr_period: int = 14,
        atr_sl_multiplier: float = 2.0,  # Wider stop loss
        cooldown_bars: int = 3,  # Bars to wait after exit
        position_size_pct: float = 0.2,  # 20% position
        # Flow analysis windows (in bars)
        flow_windows: list = None,
        flow_weights: list = None,
    ):
        self.symbol = symbol
        self.interval = interval
        self.score_threshold = score_threshold
        self.min_confidence = min_confidence
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier
        self.cooldown_bars = cooldown_bars
        self.position_size_pct = position_size_pct
        self.flow_windows = flow_windows or [5, 10, 20]
        self.flow_weights = flow_weights or [1.0, 0.6, 0.4]

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all indicators needed for flow analysis."""
        df = df.copy()

        # Price changes
        df["body"] = df["close"] - df["open"]
        df["body_abs"] = df["body"].abs()
        df["upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)
        df["lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]

        # Direction (1=up, -1=down, 0=flat)
        df["direction"] = np.where(df["body"] > 0, 1, np.where(df["body"] < 0, -1, 0))

        # Volume-weighted direction strength
        df["direction_strength"] = df["direction"] * df["body_abs"]

        # EMA for trend
        df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["trend"] = np.where(df["close"] > df["ema_20"], 1, -1)

        # ATR
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["close"].shift() - df["low"]).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.ewm(span=self.atr_period, adjust=False).mean()

        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, 1e-10)
        df["rsi"] = 100 - (100 / (1 + rs))

        # MACD
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema_12 - ema_26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # Calculate flow imbalances for each window
        for i, window in enumerate(self.flow_windows):
            weight = self.flow_weights[i] if i < len(self.flow_weights) else 1.0

            # Rolling sum of direction strength
            df[f"flow_sum_{window}"] = df["direction_strength"].rolling(window=window).sum()
            df[f"flow_total_{window}"] = df["body_abs"].rolling(window=window).sum()

            # Flow imbalance (-1 to 1)
            total = df[f"flow_total_{window}"].replace(0, 1e-10)
            df[f"flow_imbalance_{window}"] = (df[f"flow_sum_{window}"] / total).fillna(0)

            # Weighted flow score
            df[f"flow_score_{window}"] = df[f"flow_imbalance_{window}"] * weight

        # Composite flow score
        flow_cols = [f"flow_score_{w}" for w in self.flow_windows]
        df["composite_flow"] = df[flow_cols].sum(axis=1)
        total_weight = sum(self.flow_weights[:len(self.flow_windows)])
        df["composite_flow"] = df["composite_flow"] / total_weight

        # Velocity (rate of change)
        df["velocity"] = df["close"].pct_change(periods=3).fillna(0) * 100  # % change

        # Momentum confirmation
        df["momentum"] = df["macd_hist"].rolling(window=5).mean().fillna(0)

        return df

    def generate_signals(self, df: pd.DataFrame) -> dict[str, Any]:
        """Generate trading signals with cooldown to avoid duplicates."""
        n = len(df)
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        target_weights = np.zeros(n, dtype=np.float64)

        position = 0  # 0=flat, 1=long, -1=short
        entry_idx = 0
        entry_price = 0.0
        cooldown_remaining = 0

        signals_generated = []

        for i in range(n):
            row = df.iloc[i]

            # Decrement cooldown
            if cooldown_remaining > 0:
                cooldown_remaining -= 1

            # Calculate confidence based on multiple factors
            flow_score = row.get("composite_flow", 0)
            velocity = row.get("velocity", 0)
            momentum = row.get("momentum", 0)
            trend = row.get("trend", 1)
            rsi = row.get("rsi", 50)
            atr = row.get("atr", 0)

            # Confidence calculation
            confidence = 0.0

            # Flow score contribution (up to 0.4)
            confidence += min(abs(flow_score) * 0.4, 0.4)

            # Velocity contribution (up to 0.2)
            confidence += min(abs(velocity) * 0.1, 0.2)

            # Momentum confirmation (up to 0.2)
            momentum_aligned = (flow_score > 0 and momentum > 0) or (flow_score < 0 and momentum < 0)
            if momentum_aligned:
                confidence += 0.2

            # Trend alignment (up to 0.2)
            trend_aligned = (flow_score > 0 and trend > 0) or (flow_score < 0 and trend < 0)
            if trend_aligned:
                confidence += 0.2

            # RSI filter (avoid overbought/oversold)
            if 30 < rsi < 70:
                confidence += 0.1

            confidence = min(confidence, 1.0)

            # Determine direction
            direction = "neutral"
            if cooldown_remaining == 0:
                if flow_score > self.score_threshold and confidence >= self.min_confidence:
                    direction = "long"
                elif flow_score < -self.score_threshold and confidence >= self.min_confidence:
                    direction = "short"

            # Entry logic
            if position == 0 and direction != "neutral":
                if direction == "long":
                    entries[i] = True
                    position = 1
                    entry_idx = i
                    entry_price = row["close"]
                    signals_generated.append({
                        "timestamp": row["timestamp"],
                        "direction": "long",
                        "price": row["close"],
                        "score": flow_score,
                        "confidence": confidence,
                    })
                else:  # short
                    entries[i] = True
                    position = -1
                    entry_idx = i
                    entry_price = row["close"]
                    signals_generated.append({
                        "timestamp": row["timestamp"],
                        "direction": "short",
                        "price": row["close"],
                        "score": flow_score,
                        "confidence": confidence,
                    })

            # Exit logic
            elif position != 0:
                # Time-based exit (max hold 10 bars)
                if i - entry_idx >= 10:
                    exits[i] = True
                    signals_generated.append({
                        "timestamp": row["timestamp"],
                        "direction": "exit",
                        "reason": "time_exit",
                    })
                    position = 0
                    cooldown_remaining = self.cooldown_bars
                # Signal-based exit (flow reversal)
                elif (position == 1 and flow_score < 0 and abs(flow_score) > self.score_threshold * 0.5) or \
                     (position == -1 and flow_score > 0 and abs(flow_score) > self.score_threshold * 0.5):
                    exits[i] = True
                    signals_generated.append({
                        "timestamp": row["timestamp"],
                        "direction": "exit",
                        "reason": "flow_reversal",
                    })
                    position = 0
                    cooldown_remaining = self.cooldown_bars

            # Set target weight
            target_weights[i] = position * self.position_size_pct

        return {
            "entries": entries,
            "exits": exits,
            "target_weights": target_weights,
            "signals": signals_generated,
            "composite_flow": df["composite_flow"].values if "composite_flow" in df.columns else np.zeros(n),
        }

    def run_backtest(self, days: int = 30) -> dict[str, Any]:
        """Run the backtest."""
        print(f"\n{'='*60}")
        print("Flow Right Strategy - Candlestick Backtest")
        print(f"{'='*60}")
        print(f"Symbol: {self.symbol}")
        print(f"Interval: {self.interval}")
        print(f"Days: {days}")
        print("\nParameters:")
        print(f"  Score Threshold: {self.score_threshold}")
        print(f"  Min Confidence: {self.min_confidence}")
        print(f"  ATR Period: {self.atr_period}")
        print(f"  ATR SL Multiplier: {self.atr_sl_multiplier}")
        print(f"  Cooldown Bars: {self.cooldown_bars}")
        print(f"  Position Size: {self.position_size_pct*100:.0f}%")
        print(f"  Flow Windows: {self.flow_windows}")
        print(f"{'='*60}\n")

        # Fetch data
        interval_minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
        mins_per_bar = interval_minutes.get(self.interval, 60)
        bars_needed = days * 24 * 60 // mins_per_bar + 100

        bar = interval_to_okx_bar(self.interval)
        df = fetch_candles(
            CandlesRequest(
                inst_id=self.symbol,
                bar=bar,
                limit=min(bars_needed, 1000),
            )
        )

        if df is None or len(df) == 0:
            print("Error: No data fetched")
            return {"error": "No data"}

        print(f"Fetched {len(df)} bars")
        print(f"Date range: {datetime.fromtimestamp(df['timestamp'].min()/1000, tz=timezone.utc)}")
        print(f"           to {datetime.fromtimestamp(df['timestamp'].max()/1000, tz=timezone.utc)}")

        # Calculate indicators
        print("\nCalculating indicators...")
        df = self.calculate_indicators(df)

        # Generate signals
        print("Generating signals...")
        result = self.generate_signals(df)

        signals = result["signals"]
        print(f"Generated {len(signals)} signals")

        # Count entries and exits
        entries = [s for s in signals if s["direction"] in ["long", "short"]]
        exits = [s for s in signals if s["direction"] == "exit"]
        print(f"  Entries: {len(entries)}")
        print(f"  Exits: {len(exits)}")

        # Run backtest
        print("\nRunning backtest...")
        config = BacktestConfig(
            initial_cash=10000.0,
            fee_rate=0.0004,
        )

        backtest_result = run_backtest(
            data=df,
            signals={
                "entries": result["entries"],
                "exits": result["exits"],
                "target_weights": result["target_weights"],
            },
            interval=self.interval,
            config=config,
        )

        metrics = backtest_result.metrics

        # Print results
        print(f"\n{'='*60}")
        print("Backtest Results")
        print(f"{'='*60}")
        print(f"Total Return: {metrics.get('total_return', 0):.2f}%")
        print(f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
        print(f"Max Drawdown: {metrics.get('max_drawdown', 0):.2f}%")
        print(f"Win Rate: {metrics.get('win_rate', 0):.1f}%")
        print(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
        print(f"Total Trades: {metrics.get('total_trades', 0)}")
        print(f"Final Equity: ${backtest_result.equity['equity'].iloc[-1]:,.2f}")
        print(f"{'='*60}\n")

        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "days": days,
            "metrics": metrics,
            "signals": signals,
            "equity_curve": backtest_result.equity["equity"].tolist(),
            "params": {
                "score_threshold": self.score_threshold,
                "min_confidence": self.min_confidence,
                "atr_period": self.atr_period,
                "atr_sl_multiplier": self.atr_sl_multiplier,
                "cooldown_bars": self.cooldown_bars,
                "position_size_pct": self.position_size_pct,
                "flow_windows": self.flow_windows,
                "flow_weights": self.flow_weights,
            },
        }


def run_optimized_backtest():
    """Run backtest with optimized parameters."""
    backtest = FlowRightBacktest(
        symbol="BTC-USDT-SWAP",
        interval="1h",
        # Optimized parameters
        score_threshold=0.5,  # Higher threshold
        min_confidence=0.6,   # Higher confidence requirement
        atr_period=14,
        atr_sl_multiplier=2.0,
        cooldown_bars=3,
        position_size_pct=0.2,
        flow_windows=[5, 10, 20],
        flow_weights=[1.0, 0.6, 0.4],
    )
    return backtest.run_backtest(days=30)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run Flow Right backtest")
    parser.add_argument("--symbol", type=str, default="BTC-USDT-SWAP")
    parser.add_argument("--interval", type=str, default="1h")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--confidence", type=float, default=0.6)
    parser.add_argument("--cooldown", type=int, default=3)

    args = parser.parse_args()

    backtest = FlowRightBacktest(
        symbol=args.symbol,
        interval=args.interval,
        score_threshold=args.threshold,
        min_confidence=args.confidence,
        cooldown_bars=args.cooldown,
    )

    result = backtest.run_backtest(days=args.days)

    if "error" not in result:
        print("Backtest completed successfully!")
    else:
        print("Backtest failed!")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
