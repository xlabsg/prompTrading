from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 10_000.0
    fee_rate: float = 0.0004  # 4 bps per rebalance, approximated
    slippage_bps: float = 0.0  # fixed slippage applied on rebalances (bps)


@dataclass(frozen=True)
class BacktestResult:
    equity: pd.DataFrame
    positions: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, Any]


def _interval_to_bars_per_year(interval: str) -> Optional[float]:
    # Binance style: 1m, 5m, 15m, 1h, 4h, 1d...
    if not interval:
        return None
    unit = interval[-1]
    try:
        n = int(interval[:-1])
    except Exception:
        return None
    minutes_per_year = 60 * 24 * 365
    if unit == "m":
        return minutes_per_year / n
    if unit == "h":
        return minutes_per_year / (60 * n)
    if unit == "d":
        return minutes_per_year / (60 * 24 * n)
    if unit == "w":
        return minutes_per_year / (60 * 24 * 7 * n)
    return None


def _safe_float(x: float) -> float:
    if np.isnan(x) or np.isinf(x):
        return 0.0
    return float(x)


def _compute_drawdown(equity: np.ndarray) -> np.ndarray:
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    return dd


def _extract_weights(signals: dict[str, Any], n: int) -> np.ndarray:
    if "target_weights" in signals:
        w = np.asarray(signals["target_weights"], dtype=np.float64)
        if w.shape[0] != n:
            raise ValueError("target_weights length mismatch")
        w = np.clip(w, -1.0, 1.0)
        return w

    raise ValueError("signals must contain target_weights")


def _build_trades_from_weights(ts: np.ndarray, close: np.ndarray, w: np.ndarray) -> pd.DataFrame:
    """Create trade rows for sign transitions across 0."""
    rows: list[dict[str, Any]] = []
    n = len(w)
    current_side: int = 0  # -1 short, 0 flat, 1 long
    entry_i: Optional[int] = None
    entry_side: int = 0

    def side_of(x: float) -> int:
        if x > 0:
            return 1
        if x < 0:
            return -1
        return 0

    for i in range(n):
        side = side_of(w[i])
        if current_side == 0 and side != 0:
            current_side = side
            entry_i = i
            entry_side = side
            continue
        if current_side != 0 and side == 0:
            assert entry_i is not None
            pnl = (close[i] - close[entry_i]) * entry_side
            ret = pnl / close[entry_i] if close[entry_i] != 0 else 0.0
            rows.append(
                {
                    "entry_i": entry_i,
                    "exit_i": i,
                    "entry_ts": int(ts[entry_i]),
                    "exit_ts": int(ts[i]),
                    "side": "long" if entry_side > 0 else "short",
                    "entry_price": float(close[entry_i]),
                    "exit_price": float(close[i]),
                    "pnl": float(pnl),
                    "return": float(ret),
                    "duration_bars": int(i - entry_i),
                }
            )
            current_side = 0
            entry_i = None
            entry_side = 0
            continue
        if current_side != 0 and side != 0 and side != current_side:
            # flip: close and re-open at same bar
            assert entry_i is not None
            pnl = (close[i] - close[entry_i]) * entry_side
            ret = pnl / close[entry_i] if close[entry_i] != 0 else 0.0
            rows.append(
                {
                    "entry_i": entry_i,
                    "exit_i": i,
                    "entry_ts": int(ts[entry_i]),
                    "exit_ts": int(ts[i]),
                    "side": "long" if entry_side > 0 else "short",
                    "entry_price": float(close[entry_i]),
                    "exit_price": float(close[i]),
                    "pnl": float(pnl),
                    "return": float(ret),
                    "duration_bars": int(i - entry_i),
                }
            )
            current_side = side
            entry_i = i
            entry_side = side

    return pd.DataFrame(rows)


def run_backtest(
    data: pd.DataFrame,
    *,
    signals: dict[str, Any],
    interval: str,
    config: Optional[BacktestConfig] = None,
) -> BacktestResult:
    config = config or BacktestConfig()
    if "timestamp" not in data.columns:
        raise ValueError("data must have timestamp column (ms)")
    for col in ("open", "high", "low", "close", "volume"):
        if col not in data.columns:
            raise ValueError(f"data missing column: {col}")

    ts = data["timestamp"].to_numpy(dtype=np.int64)
    close = data["close"].to_numpy(dtype=np.float64)
    n = len(close)
    if n < 3:
        raise ValueError("not_enough_bars")

    w = _extract_weights(signals, n)

    # close-to-close returns
    r = np.zeros(n, dtype=np.float64)
    r[1:] = close[1:] / close[:-1] - 1.0

    fee = float(config.fee_rate)
    slippage_bps = float(config.slippage_bps)
    slippage = max(0.0, slippage_bps / 10_000.0)
    tx_cost = fee + slippage
    equity = np.zeros(n, dtype=np.float64)
    equity[0] = float(config.initial_cash) * (1.0 - tx_cost * abs(w[0] - 0.0))
    for i in range(1, n):
        equity[i] = equity[i - 1] * (1.0 + w[i - 1] * r[i])
        # rebalance at bar i close for next bar
        equity[i] = equity[i] * (1.0 - tx_cost * abs(w[i] - w[i - 1]))

    dd = _compute_drawdown(equity)

    # Benchmark: buy and hold the underlying asset from bar 0 close
    benchmark_equity = float(config.initial_cash) * (close / close[0]) if close[0] > 0 else np.full(n, float(config.initial_cash))
    benchmark_return = (close[-1] / close[0] - 1.0) if close[0] > 0 else 0.0

    # positions (target weights and implied units)
    units = (equity * w) / close
    positions = pd.DataFrame(
        {
            "timestamp": ts,
            "weight": w,
            "units": units,
            "close": close,
        }
    )

    equity_df = pd.DataFrame(
        {
            "timestamp": ts,
            "equity": equity,
            "benchmark_equity": benchmark_equity,
            "returns": r,
            "drawdown": dd,
            "weight": w,
        }
    )

    trades_df = _build_trades_from_weights(ts, close, w)

    total_return = equity[-1] / equity[0] - 1.0 if equity[0] != 0 else 0.0
    max_dd = float(dd.min()) if len(dd) else 0.0

    # Sharpe (approx, assumes bar returns are i.i.d.)
    bars_per_year = _interval_to_bars_per_year(interval)
    sharpe = 0.0
    if bars_per_year and np.std(r[1:]) > 1e-12:
        sharpe = float(np.mean(r[1:]) / np.std(r[1:]) * np.sqrt(bars_per_year))

    win_rate = None
    profit_factor = None
    if len(trades_df) > 0:
        win_rate = float((trades_df["pnl"] > 0).mean())
        # Calculate profit factor: sum(winning trades) / abs(sum(losing trades))
        winning_pnl = trades_df[trades_df["pnl"] > 0]["pnl"].sum()
        losing_pnl = abs(trades_df[trades_df["pnl"] < 0]["pnl"].sum())
        if losing_pnl > 0:
            profit_factor = float(winning_pnl / losing_pnl)

    metrics: dict[str, Any] = {
        "initial_cash": _safe_float(config.initial_cash),
        "final_equity": _safe_float(equity[-1]),
        "total_return": _safe_float(total_return * 100),  # Convert to percentage
        "benchmark_return": _safe_float(benchmark_return * 100),  # Buy and hold return percentage
        "alpha": _safe_float((total_return - benchmark_return) * 100),  # Excess return over benchmark
        "max_drawdown": _safe_float(abs(max_dd) * 100),  # Convert to positive percentage
        "sharpe_ratio": _safe_float(sharpe),  # Renamed from sharpe
        "num_bars": int(n),
        "total_trades": int(len(trades_df)),  # Renamed from num_trades
        "win_rate": _safe_float(win_rate * 100) if win_rate is not None else None,  # Convert to percentage
        "profit_factor": _safe_float(profit_factor) if profit_factor is not None else None,
        "interval": interval,
        "fee_rate": fee,
        "slippage_bps": slippage_bps,
    }

    return BacktestResult(equity=equity_df, positions=positions, trades=trades_df, metrics=metrics)
