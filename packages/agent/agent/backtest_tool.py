"""Real, budgeted backtesting for the autonomous agent.

`BacktestSkill` used to be disabled because it drove an endless edit->backtest
loop. Two things caused that, and both are addressed here:

1. The old tool backtested on freshly generated *random* data, so metrics were
   noise and the agent kept editing to chase them. This module runs against real
   market data through the shared cache, making a given (code, dataset) pair
   deterministic.
2. Nothing bounded the loop. `BacktestBudget` caps the number of runs per
   session and tells the agent, in the tool output, how many remain and whether
   it is still improving.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from backtest.protocol import normalize_signals
from backtest.vectorized import BacktestConfig, run_backtest

# Defaults chosen to match the Stable5 preset so agent-side numbers are
# comparable to the platform's own backtests.
DEFAULT_EXCHANGE = "okx"
DEFAULT_SYMBOL = "BTC-USDT-SWAP"
DEFAULT_INTERVAL = "1h"
DEFAULT_BARS = 2000
DEFAULT_MAX_RUNS = 2
DEFAULT_FEE_RATE = 0.0002
DEFAULT_SLIPPAGE_BPS = 2.0

REPORTED_METRICS = (
    "total_return",
    "sharpe_ratio",
    "deflated_sharpe_ratio",
    "p_value",
    "robustness_score",
    "max_drawdown",
    "win_rate",
    "profit_factor",
    "total_trades",
    "num_bars",
)


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v is not None and v != "" else default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


@dataclass
class BacktestDataset:
    """Which market the agent evaluates against."""

    exchange: str = DEFAULT_EXCHANGE
    symbol: str = DEFAULT_SYMBOL
    interval: str = DEFAULT_INTERVAL
    bars: int = DEFAULT_BARS
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None

    @classmethod
    def from_env(cls) -> "BacktestDataset":
        start = os.getenv("AGENT_BACKTEST_START_MS") or ""
        end = os.getenv("AGENT_BACKTEST_END_MS") or ""
        return cls(
            exchange=_env("AGENT_BACKTEST_EXCHANGE", DEFAULT_EXCHANGE).strip().lower(),
            symbol=_env("AGENT_BACKTEST_SYMBOL", DEFAULT_SYMBOL).strip(),
            interval=_env("AGENT_BACKTEST_INTERVAL", DEFAULT_INTERVAL).strip(),
            bars=_env_int("AGENT_BACKTEST_BARS", DEFAULT_BARS),
            start_ms=int(start) if start.strip().isdigit() else None,
            end_ms=int(end) if end.strip().isdigit() else None,
        )

    def describe(self) -> str:
        return f"{self.exchange}:{self.symbol}:{self.interval}"


@dataclass
class BacktestBudget:
    """Bounds the edit->backtest loop and tracks whether it is still improving.

    `score_key` is the metric the agent is asked to improve; `stall_limit` stops
    it once repeated runs stop moving that metric.
    """

    max_runs: int = DEFAULT_MAX_RUNS
    stall_limit: int = 2
    score_key: str = "sharpe_ratio"
    runs_used: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "BacktestBudget":
        return cls(
            max_runs=max(0, _env_int("AGENT_BACKTEST_MAX_RUNS", DEFAULT_MAX_RUNS)),
            stall_limit=max(1, _env_int("AGENT_BACKTEST_STALL_LIMIT", 2)),
            score_key=_env("AGENT_BACKTEST_SCORE_KEY", "sharpe_ratio"),
        )

    @property
    def exhausted(self) -> bool:
        return self.runs_used >= self.max_runs

    @property
    def remaining(self) -> int:
        return max(0, self.max_runs - self.runs_used)

    def best_score(self) -> float | None:
        scores = [h.get(self.score_key) for h in self.history]
        scores = [s for s in scores if isinstance(s, (int, float))]
        return max(scores) if scores else None

    def record(self, metrics: dict[str, Any]) -> None:
        self.runs_used += 1
        self.history.append(dict(metrics))

    def stalled(self) -> bool:
        """True when the last `stall_limit` runs failed to beat the best before them."""
        if len(self.history) <= self.stall_limit:
            return False
        scored = [
            h.get(self.score_key)
            for h in self.history
            if isinstance(h.get(self.score_key), (int, float))
        ]
        if len(scored) <= self.stall_limit:
            return False
        baseline = max(scored[: -self.stall_limit])
        return all(s <= baseline for s in scored[-self.stall_limit :])


def _install_guard(dataset: BacktestDataset) -> None:
    """Restrict this process to the dataset's exchange before running user code.

    The agent executes generated strategies in-process, so it needs the same
    network restriction the platform's backtest runner applies. The guard is
    process-wide and install-once, so it is set up with the exchange allowlist
    the market-data fetch itself needs.
    """
    try:
        from backtest.network_guard import install_network_guard
        from backtest.runner import build_backtest_allowlist, network_guard_enabled

        extra = [h.strip() for h in (os.getenv("NETWORK_ALLOWLIST") or "").split(",") if h.strip()]
        install_network_guard(
            allowlist=build_backtest_allowlist(dataset.exchange) + extra,
            enabled=network_guard_enabled(),
        )
    except Exception:
        # Never let guard setup break the backtest loop.
        pass


def load_dataset(dataset: BacktestDataset) -> pd.DataFrame:
    """Fetch bars for `dataset`, served from the shared market-data cache."""
    exchange = (dataset.exchange or "").strip().lower()

    if exchange == "binance":
        from data.binance import KlinesRequest, fetch_klines

        return fetch_klines(
            KlinesRequest(
                symbol=dataset.symbol,
                interval=dataset.interval,
                start_ms=dataset.start_ms,
                end_ms=dataset.end_ms,
                limit=dataset.bars,
            )
        )

    if exchange == "okx":
        from data.okx import CandlesRequest, fetch_candles, interval_to_okx_bar

        return fetch_candles(
            CandlesRequest(
                inst_id=dataset.symbol,
                bar=interval_to_okx_bar(dataset.interval),
                start_ms=dataset.start_ms,
                end_ms=dataset.end_ms,
                limit=dataset.bars,
            )
        )

    if exchange == "us_stock":
        from data.us_stock import USStockDailyRequest, fetch_us_stock_daily

        if dataset.interval != "1d":
            raise ValueError("us_stock_only_supports_1d")
        return fetch_us_stock_daily(
            USStockDailyRequest(
                symbol=dataset.symbol,
                start_ms=dataset.start_ms,
                end_ms=dataset.end_ms,
            )
        )

    raise ValueError(f"unsupported_exchange:{exchange}")


def _format_metrics(metrics: dict[str, Any]) -> str:
    lines = []
    for key in REPORTED_METRICS:
        if key in metrics and metrics[key] is not None:
            value = metrics[key]
            lines.append(f"  {key}: {value:.4f}" if isinstance(value, float) else f"  {key}: {value}")
    return "\n".join(lines)


def run_agent_backtest(
    *,
    strategy_path: str,
    entry_function: str,
    dataset: BacktestDataset,
    budget: BacktestBudget,
    params: dict[str, Any] | None = None,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Backtest the strategy at `strategy_path`.

    Returns `(ok, human_readable_report, metrics)`. Errors are returned as text
    rather than raised so the agent can read and act on them.
    """
    if budget.exhausted:
        return (
            False,
            (
                f"Backtest budget exhausted ({budget.max_runs} runs used). "
                "Do not call backtest again — finalise the strategy and call task_done."
            ),
            None,
        )

    if not os.path.isfile(strategy_path):
        return False, f"Strategy file not found: {strategy_path}", None

    import importlib.util

    spec = importlib.util.spec_from_file_location("agent_strategy_module", strategy_path)
    if spec is None or spec.loader is None:
        return False, "Failed to load strategy module.", None

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        return False, f"Strategy import failed: {type(e).__name__}: {e}", None

    fn = getattr(module, entry_function, None)
    if fn is None:
        return False, f"{entry_function}() not found in {os.path.basename(strategy_path)}", None

    _install_guard(dataset)

    try:
        data = load_dataset(dataset)
    except Exception as e:
        return False, f"Market data fetch failed for {dataset.describe()}: {type(e).__name__}: {e}", None

    if data is None or len(data) < 3:
        return False, f"Not enough bars for {dataset.describe()} (got {0 if data is None else len(data)}).", None

    data = data.sort_values("timestamp").reset_index(drop=True)

    try:
        signals = fn(data.copy(), dict(params or {}))
    except Exception as e:
        return False, f"Strategy execution error: {type(e).__name__}: {e}", None

    if not isinstance(signals, dict):
        return False, "Strategy must return a dict of signals.", None

    try:
        signals = normalize_signals(signals, n=len(data), mode="auto", symbol=dataset.symbol)
    except Exception as e:
        return False, f"Signal protocol violation: {type(e).__name__}: {e}", None

    try:
        result = run_backtest(
            data,
            signals=signals,
            interval=dataset.interval,
            config=BacktestConfig(
                fee_rate=_env_float("AGENT_BACKTEST_FEE_RATE", DEFAULT_FEE_RATE),
                slippage_bps=_env_float("AGENT_BACKTEST_SLIPPAGE_BPS", DEFAULT_SLIPPAGE_BPS),
            ),
        )
    except Exception as e:
        return False, f"Backtest engine error: {type(e).__name__}: {e}", None

    metrics = dict(result.metrics)

    robustness_diagnostics = []
    try:
        from backtest.robustness import evaluate_strategy_robustness

        equity_series = result.equity.get("equity") if hasattr(result.equity, "get") else None
        if equity_series is not None and len(equity_series) > 1:
            rets = equity_series.pct_change().dropna().values
            rob = evaluate_strategy_robustness(
                returns=rets,
                observed_sharpe=float(metrics.get("sharpe_ratio", 0.0) or 0.0),
                max_drawdown=float(metrics.get("max_drawdown", 0.0) or 0.0),
                num_trades=int(metrics.get("total_trades", 0) or 0),
                trials_count=1,
            )
            metrics["deflated_sharpe_ratio"] = rob.deflated_sharpe_ratio
            metrics["p_value"] = rob.p_value
            metrics["robustness_score"] = rob.robustness_score
            metrics["is_robust"] = rob.is_robust
            robustness_diagnostics = list(rob.diagnostics)

            # In multi-run sessions, warn the agent about multiple testing degradation
            if budget.runs_used > 0:
                from backtest.robustness import compute_dsr
                multi_dsr, _, _ = compute_dsr(
                    returns=rets,
                    observed_sharpe=float(metrics.get("sharpe_ratio", 0.0) or 0.0),
                    trials_count=budget.runs_used + 1,
                )
                robustness_diagnostics.append(
                    f"Multiple testing warning: across {budget.runs_used + 1} iterations, effective DSR adjusts to {multi_dsr:.4f}."
                )
    except Exception:
        pass

    previous_best = budget.best_score()
    budget.record(metrics)

    score = metrics.get(budget.score_key)
    report = [
        f"Backtest #{budget.runs_used} on {dataset.describe()} ({len(data)} bars):",
        _format_metrics(metrics),
    ]
    if robustness_diagnostics:
        report.append("  Robustness diagnostics:")
        for diag in robustness_diagnostics:
            report.append(f"    * {diag}")

    if isinstance(score, (int, float)) and previous_best is not None:
        delta = score - previous_best
        trend = "improved" if delta > 0 else ("unchanged" if delta == 0 else "regressed")
        report.append(f"  {budget.score_key} {trend} vs best so far ({previous_best:.4f} -> {score:.4f}).")

    if budget.exhausted:
        report.append("Budget exhausted. Finalise the strategy now and call task_done.")
    elif budget.stalled():
        report.append(
            f"No improvement over the last {budget.stall_limit} runs. "
            "Stop tuning and call task_done unless you have a specific fix."
        )
    else:
        report.append(f"{budget.remaining} backtest run(s) remaining.")

    return True, "\n".join(report), metrics


def budget_summary(budget: BacktestBudget, dataset: BacktestDataset) -> dict[str, Any]:
    """Machine-readable iteration record, persisted alongside the version."""
    return {
        "dataset": {
            "exchange": dataset.exchange,
            "symbol": dataset.symbol,
            "interval": dataset.interval,
            "bars": dataset.bars,
        },
        "score_key": budget.score_key,
        "runs_used": budget.runs_used,
        "max_runs": budget.max_runs,
        "best_score": budget.best_score(),
        "history": [
            {k: v for k, v in m.items() if k in REPORTED_METRICS} for m in budget.history
        ],
    }


__all__ = [
    "BacktestBudget",
    "BacktestDataset",
    "run_agent_backtest",
    "budget_summary",
    "load_dataset",
]
