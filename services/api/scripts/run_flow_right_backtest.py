#!/usr/bin/env python3
"""
Backtest script for flow_right strategy.

Usage:
    python run_flow_right_backtest.py --days 30 --symbol BTC-USDT-SWAP --interval 1h
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
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
    days: int = 30
    symbol: str = "BTC-USDT-SWAP"
    interval: str = "1h"
    initial_cash: float = 10000.0
    fee_rate: float = 0.0004


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=span, adjust=False).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Average True Range."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def calculate_flow_imbalance(
    df: pd.DataFrame,
    window_bars: int,
) -> pd.Series:
    """Calculate flow imbalance from bar data."""
    body = df["close"] - df["open"]
    body_size = body.abs()
    total_size = body_size.rolling(window=window_bars).sum()
    total_size = total_size.replace(0, 1e-10)
    imbalance = (body.rolling(window=window_bars).sum()) / total_size
    return imbalance.fillna(0)


def generate_flow_signals(
    df: pd.DataFrame,
    windows: list[int] = [10, 30, 60],
    window_weights: list[float] = [1.0, 0.7, 0.5],
    score_threshold: float = 0.3,
    atr_period: int = 14,
    atr_sl_multiplier: float = 1.5,
) -> dict[str, Any]:
    """
    Generate trading signals for flow_right strategy.

    Returns:
        Dictionary with entries, exits, and target_weights
    """
    n = len(df)
    entries = np.zeros(n, dtype=bool)
    exits = np.zeros(n, dtype=bool)
    target_weights = np.zeros(n, dtype=np.float64)

    # Calculate ATR
    df["atr"] = atr(df["high"], df["low"], df["close"], atr_period)

    # Calculate imbalances for each window
    imbalances = {}
    for i, window in enumerate(windows):
        window_bars = window // int(df["timestamp"].diff().median() / 60000) if i > 0 else window
        if window_bars < 1:
            window_bars = 1
        if window_bars < len(df):
            imbalances[window] = calculate_flow_imbalance(df, window_bars)

    # Calculate velocity
    close = df["close"]
    price_change = close.pct_change() * 10000  # bps
    velocity = price_change.rolling(window=10).mean().fillna(0)

    # Calculate composite score
    weighted_sum = 0.0
    total_weight = sum(window_weights)
    for i, window in enumerate(windows):
        if window in imbalances:
            weight = window_weights[i] if i < len(window_weights) else 1.0
            weighted_sum += imbalances[window] * weight
    composite = weighted_sum / total_weight

    # Add velocity component
    velocity_component = velocity * 0.1
    composite = composite + velocity_component
    composite = composite.clip(-1, 1)

    # Generate signals
    position = 0  # 0=flat, 1=long, -1=short
    entry_price = 0.0
    entry_idx = 0
    atr_value = 0.0

    for i in range(n):
        score = float(composite.iloc[i]) if i < len(composite) else 0.0
        current_atr = float(df["atr"].iloc[i]) if i < len(df) else 0.0

        # Entry logic
        if position == 0:
            if score > score_threshold:
                position = 1  # Enter long
                entries[i] = True
                entry_price = float(df["close"].iloc[i])
                entry_idx = i
                atr_value = current_atr
                target_weights[i] = 1.0
            elif score < -score_threshold:
                position = -1  # Enter short
                entries[i] = True
                entry_price = float(df["close"].iloc[i])
                entry_idx = i
                atr_value = current_atr
                target_weights[i] = -1.0
            else:
                target_weights[i] = 0.0

        # Exit logic
        else:
            # Time-based exit (5 bars max)
            if i - entry_idx >= 5:
                exits[i] = True
                position = 0
                target_weights[i] = 0.0
            # Signal-based exit
            elif (position == 1 and score < 0) or (position == -1 and score > 0):
                exits[i] = True
                position = 0
                target_weights[i] = 0.0
            else:
                # Hold position
                target_weights[i] = 1.0 if position == 1 else -1.0

    return {
        "entries": entries,
        "exits": exits,
        "target_weights": target_weights,
        "composite_score": composite.values if len(composite) == n else np.zeros(n),
    }


def run_flow_right_backtest(args: BacktestArgs) -> dict[str, Any]:
    """Run backtest for flow_right strategy."""
    print(f"\n{'='*60}")
    print("Flow Right Strategy Backtest")
    print(f"{'='*60}")
    print(f"Symbol: {args.symbol}")
    print(f"Interval: {args.interval}")
    print(f"Days: {args.days}")
    print(f"Initial Cash: ${args.initial_cash:,.2f}")
    print(f"{'='*60}\n")

    # Fetch data from OKX (get recent data, no date filtering)
    print(f"Fetching {args.days} days of {args.symbol} data...")
    bar = interval_to_okx_bar(args.interval)

    # Calculate approximate number of bars needed
    interval_minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
    mins_per_bar = interval_minutes.get(args.interval, 60)
    bars_needed = args.days * 24 * 60 // mins_per_bar + 100  # Add buffer

    df = fetch_candles(
        CandlesRequest(
            inst_id=args.symbol,
            bar=bar,
            limit=min(bars_needed, 1000),  # Max 1000 from OKX
        )
    )

    if df is None or len(df) == 0:
        print("Error: No data fetched")
        return {}

    print(f"Fetched {len(df)} bars")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print()

    # Generate signals
    print("Generating flow signals...")
    signals = generate_flow_signals(
        df,
        windows=[10, 30, 60],
        window_weights=[1.0, 0.7, 0.5],
        score_threshold=0.3,
        atr_period=14,
        atr_sl_multiplier=1.5,
    )

    # Run backtest
    config = BacktestConfig(
        initial_cash=args.initial_cash,
        fee_rate=args.fee_rate,
    )

    print("Running backtest...")
    result = run_backtest(
        data=df,
        signals=signals,
        interval=args.interval,
        config=config,
    )

    # Print results
    print(f"\n{'='*60}")
    print("Backtest Results")
    print(f"{'='*60}")

    metrics = result.metrics
    print(f"Total Return: {metrics.get('total_return', 0):.2f}%")
    print(f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
    print(f"Max Drawdown: {metrics.get('max_drawdown', 0):.2f}%")
    print(f"Win Rate: {metrics.get('win_rate', 0):.1f}%")
    print(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
    print(f"Total Trades: {metrics.get('total_trades', 0)}")
    print(f"Final Equity: ${result.equity['equity'].iloc[-1]:,.2f}")
    print(f"{'='*60}\n")

    return {
        "args": {
            "symbol": args.symbol,
            "interval": args.interval,
            "days": args.days,
            "initial_cash": args.initial_cash,
        },
        "metrics": metrics,
        "trades_count": result.trades.shape[0] if hasattr(result.trades, 'shape') else len(result.trades),
    }


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run flow_right backtest")
    parser.add_argument("--days", type=int, default=30, help="Number of days to backtest")
    parser.add_argument("--symbol", type=str, default="BTC-USDT-SWAP", help="Trading symbol")
    parser.add_argument("--interval", type=str, default="1h", help="Candle interval")
    parser.add_argument("--cash", type=float, default=10000.0, help="Initial capital")

    args = parser.parse_args()

    backtest_args = BacktestArgs(
        days=args.days,
        symbol=args.symbol,
        interval=args.interval,
        initial_cash=args.cash,
    )

    result = run_flow_right_backtest(backtest_args)

    if result:
        print("Backtest completed successfully!")
        return 0
    else:
        print("Backtest failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
