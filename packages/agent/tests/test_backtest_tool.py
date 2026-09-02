"""Tests for the agent's bounded backtest loop.

These cover the two failures that caused BacktestSkill to be disabled
previously: unbounded iteration, and non-deterministic (synthetic) data.
"""

from __future__ import annotations

import textwrap

import pandas as pd
import pytest

from agent import backtest_tool
from agent.backtest_tool import (
    BacktestBudget,
    BacktestDataset,
    budget_summary,
    run_agent_backtest,
)

HOUR_MS = 3_600_000

# Captured before the autouse fixture stubs it out.
_REAL_LOAD_DATASET = backtest_tool.load_dataset

STRATEGY_OK = textwrap.dedent(
    """
    import numpy as np

    def generate_signals(data, params):
        n = len(data)
        close = data["close"].to_numpy()
        fast = pd.Series(close).rolling(3).mean().to_numpy()
        weights = np.where(close > np.nan_to_num(fast, nan=close[0]), 1.0, -1.0)
        return {
            "target_weights": weights.astype(float),
            "weight_reason": ["trend"] * n,
            "close_dbg": close,
        }

    import pandas as pd
    """
)

STRATEGY_RAISES = "def generate_signals(data, params):\n    raise ValueError('boom')\n"
STRATEGY_BAD_RETURN = "def generate_signals(data, params):\n    return 42\n"
STRATEGY_NO_FN = "x = 1\n"


@pytest.fixture
def bars():
    ts = list(range(1_000 * HOUR_MS, 1_200 * HOUR_MS, HOUR_MS))
    close = [100 + (i % 17) - (i % 5) for i in range(len(ts))]
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "volume": [10.0] * len(ts),
        }
    )


@pytest.fixture(autouse=True)
def _stub_market_data(monkeypatch, bars):
    """Never touch the network; dataset loading is covered separately."""
    monkeypatch.setattr(backtest_tool, "load_dataset", lambda ds: bars.copy())


def write_strategy(tmp_path, source: str) -> str:
    p = tmp_path / "strategy.py"
    p.write_text(source)
    return str(p)


def run(tmp_path, source=STRATEGY_OK, budget=None, dataset=None):
    return run_agent_backtest(
        strategy_path=write_strategy(tmp_path, source),
        entry_function="generate_signals",
        dataset=dataset or BacktestDataset(),
        budget=budget if budget is not None else BacktestBudget(max_runs=5),
    )


def test_successful_backtest_reports_metrics(tmp_path):
    budget = BacktestBudget(max_runs=3)
    ok, report, metrics = run(tmp_path, budget=budget)
    assert ok, report
    assert metrics is not None
    assert "sharpe_ratio" in metrics
    assert "Backtest #1" in report
    assert budget.runs_used == 1


def test_budget_blocks_further_runs(tmp_path):
    """The loop must be hard-bounded, not merely discouraged by the prompt."""
    budget = BacktestBudget(max_runs=2)
    assert run(tmp_path, budget=budget)[0]
    assert run(tmp_path, budget=budget)[0]

    ok, report, metrics = run(tmp_path, budget=budget)
    assert not ok
    assert metrics is None
    assert "budget exhausted" in report.lower()
    assert "task_done" in report
    assert budget.runs_used == 2, "a rejected run must not consume budget"


def test_remaining_runs_are_reported(tmp_path):
    budget = BacktestBudget(max_runs=3)
    _, report, _ = run(tmp_path, budget=budget)
    assert "2 backtest run(s) remaining" in report


def test_repeated_identical_runs_are_deterministic(tmp_path):
    """Same code + same data must give identical metrics, or the agent chases noise."""
    budget = BacktestBudget(max_runs=4)
    _, _, m1 = run(tmp_path, budget=budget)
    _, _, m2 = run(tmp_path, budget=budget)
    assert m1 == m2


def test_stall_detection_tells_agent_to_stop(tmp_path):
    budget = BacktestBudget(max_runs=10, stall_limit=2)
    for _ in range(3):
        ok, report, _ = run(tmp_path, budget=budget)
        assert ok
    assert budget.stalled()
    assert "No improvement" in report


def test_stall_not_triggered_while_improving():
    budget = BacktestBudget(max_runs=10, stall_limit=2, score_key="sharpe_ratio")
    for score in (0.1, 0.5, 0.9):
        budget.record({"sharpe_ratio": score})
    assert not budget.stalled()


def test_stall_triggered_after_regression():
    budget = BacktestBudget(max_runs=10, stall_limit=2, score_key="sharpe_ratio")
    for score in (0.1, 0.9, 0.4, 0.3):
        budget.record({"sharpe_ratio": score})
    assert budget.stalled()


def test_strategy_exception_is_returned_not_raised(tmp_path):
    ok, report, metrics = run(tmp_path, STRATEGY_RAISES)
    assert not ok and metrics is None
    assert "Strategy execution error" in report
    assert "boom" in report


def test_missing_entry_function_reported(tmp_path):
    ok, report, _ = run(tmp_path, STRATEGY_NO_FN)
    assert not ok
    assert "generate_signals() not found" in report


def test_non_dict_return_reported(tmp_path):
    ok, report, _ = run(tmp_path, STRATEGY_BAD_RETURN)
    assert not ok
    assert "must return a dict" in report


def test_missing_file_reported(tmp_path):
    ok, report, _ = run_agent_backtest(
        strategy_path=str(tmp_path / "nope.py"),
        entry_function="generate_signals",
        dataset=BacktestDataset(),
        budget=BacktestBudget(),
    )
    assert not ok
    assert "not found" in report


def test_failed_runs_do_not_consume_budget(tmp_path):
    budget = BacktestBudget(max_runs=2)
    run(tmp_path, STRATEGY_RAISES, budget=budget)
    assert budget.runs_used == 0, "only completed backtests should count"


def test_budget_summary_is_serialisable(tmp_path):
    budget = BacktestBudget(max_runs=3)
    run(tmp_path, budget=budget)
    summary = budget_summary(budget, BacktestDataset())
    assert summary["runs_used"] == 1
    assert summary["max_runs"] == 3
    assert summary["dataset"]["exchange"] == "okx"
    assert len(summary["history"]) == 1
    import json

    json.dumps(summary)


def test_dataset_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_BACKTEST_EXCHANGE", "binance")
    monkeypatch.setenv("AGENT_BACKTEST_SYMBOL", "ETHUSDT")
    monkeypatch.setenv("AGENT_BACKTEST_INTERVAL", "4h")
    monkeypatch.setenv("AGENT_BACKTEST_BARS", "500")
    ds = BacktestDataset.from_env()
    assert (ds.exchange, ds.symbol, ds.interval, ds.bars) == ("binance", "ETHUSDT", "4h", 500)
    assert ds.describe() == "binance:ETHUSDT:4h"


def test_budget_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_BACKTEST_MAX_RUNS", "9")
    monkeypatch.setenv("AGENT_BACKTEST_STALL_LIMIT", "4")
    b = BacktestBudget.from_env()
    assert b.max_runs == 9 and b.stall_limit == 4


def test_zero_budget_disables_backtesting(tmp_path):
    ok, report, _ = run(tmp_path, budget=BacktestBudget(max_runs=0))
    assert not ok
    assert "budget exhausted" in report.lower()


def test_unsupported_exchange_rejected():
    # _REAL_LOAD_DATASET is captured at import time, before the autouse stub.
    with pytest.raises(ValueError, match="unsupported_exchange"):
        _REAL_LOAD_DATASET(BacktestDataset(exchange="mtgox"))


def test_us_stock_rejects_non_daily_interval():
    with pytest.raises(ValueError, match="us_stock_only_supports_1d"):
        _REAL_LOAD_DATASET(BacktestDataset(exchange="us_stock", symbol="AAPL", interval="1h"))
