"""Extension contract: the protocol gate and the isolated backtest.

These exercise `tau_ext` directly rather than through a Tau session, so they run
without a model. The module reads its dataset, budget and workspace from the
environment at import time, so each test reloads it under the environment it
wants.
"""

from __future__ import annotations

import importlib
import json
import sys

import anyio
import pytest

STRATEGY_SRC = "def generate_signals(data, params):\n    return {'target_weights': []}\n"
OVERVIEW_SRC = "# Summary\n\nDoes things.\n\n```mermaid\ngraph TD;A-->B;\n```\n"

pytest.importorskip("tau_agent", reason="tau-ai is only installed in the agent image")


@pytest.fixture
def ext(tmp_path, monkeypatch):
    """Import `tau_ext` bound to a fresh workspace."""
    monkeypatch.setenv("TAU_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("AGENT_BACKTEST_MAX_RUNS", "2")
    monkeypatch.delitem(sys.modules, "agent.tau_ext", raising=False)
    module = importlib.import_module("agent.tau_ext")
    module.workspace = tmp_path  # type: ignore[attr-defined]
    return module


def _call(coro_fn, **arguments):
    return anyio.run(lambda: coro_fn("call-1", arguments))


def test_task_done_refuses_an_empty_workspace(ext):
    result = _call(ext._task_done)

    assert result.details["complete"] is False
    assert "strategy.py" in result.text
    assert "overview.md" in result.text


def test_task_done_refuses_a_strategy_without_an_entry_point(ext):
    (ext.workspace / "strategy.py").write_text("x = 1\n")
    (ext.workspace / "overview.md").write_text(OVERVIEW_SRC)

    result = _call(ext._task_done)

    assert result.details["complete"] is False
    assert "generate_signals" in result.text


def test_task_done_refuses_an_overview_without_a_diagram(ext):
    (ext.workspace / "strategy.py").write_text(STRATEGY_SRC)
    (ext.workspace / "overview.md").write_text("# Summary\n\nNo diagram.\n")

    result = _call(ext._task_done)

    assert result.details["complete"] is False
    assert "mermaid" in result.text


def test_task_done_accepts_a_complete_workspace(ext):
    (ext.workspace / "strategy.py").write_text(STRATEGY_SRC)
    (ext.workspace / "overview.md").write_text(OVERVIEW_SRC)

    result = _call(ext._task_done, summary="A momentum strategy.")

    assert result.details["complete"] is True
    assert result.details["summary"] == "A momentum strategy."


def test_task_done_never_terminates_the_loop(ext):
    """`terminate` is inert in tau 0.4.1; the driver owns completion instead."""
    (ext.workspace / "strategy.py").write_text(STRATEGY_SRC)
    (ext.workspace / "overview.md").write_text(OVERVIEW_SRC)

    result = _call(ext._task_done, summary="done")

    assert result.terminate is None


def test_backtest_runs_out_of_process(ext, monkeypatch):
    """The backtest must not run inline: its network guard would break the LLM."""
    seen = {}

    async def fake_run_process(command, *, input, check):
        seen["command"] = command
        seen["request"] = json.loads(input.decode())
        payload = {"ok": True, "report": "sharpe 1.4", "metrics": {"sharpe_ratio": 1.4}}
        return type("P", (), {"stdout": json.dumps(payload).encode(), "returncode": 0})()

    monkeypatch.setattr(ext.anyio, "run_process", fake_run_process)

    result = _call(ext._run_backtest)

    assert seen["command"][1:] == ["-m", "agent.backtest_subprocess"]
    assert seen["request"]["max_runs"] == 2
    assert result.details["metrics"] == {"sharpe_ratio": 1.4}


def test_backtest_records_against_the_parent_budget(ext, monkeypatch):
    """A throwaway process cannot accumulate history, so the parent must."""

    async def fake_run_process(command, *, input, check):
        request = json.loads(input.decode())
        payload = {
            "ok": True,
            "report": "ok",
            "metrics": {"sharpe_ratio": 1.0 + request["runs_used"]},
        }
        return type("P", (), {"stdout": json.dumps(payload).encode(), "returncode": 0})()

    monkeypatch.setattr(ext.anyio, "run_process", fake_run_process)

    _call(ext._run_backtest)
    _call(ext._run_backtest)

    assert ext._BUDGET.runs_used == 2
    assert ext._BUDGET.best_score() == 2.0


def test_unreadable_subprocess_output_becomes_a_readable_error(ext, monkeypatch):
    async def fake_run_process(command, *, input, check):
        return type("P", (), {"stdout": b"segfault", "returncode": 139})()

    monkeypatch.setattr(ext.anyio, "run_process", fake_run_process)

    result = _call(ext._run_backtest)

    assert result.details["ok"] is False
    assert "139" in result.text


def test_exhausted_budget_blocks_further_backtests(ext):
    ext._BUDGET.runs_used = ext._BUDGET.max_runs

    outcome = anyio.run(
        lambda: ext._block_exhausted_backtest(
            type("E", (), {"tool_name": "backtest", "arguments": {}})(), None
        )
    )

    assert outcome is not None
    assert outcome.block is True
    assert "exhausted" in (outcome.reason or "")


def test_other_tools_are_not_blocked(ext):
    ext._BUDGET.runs_used = ext._BUDGET.max_runs

    outcome = anyio.run(
        lambda: ext._block_exhausted_backtest(
            type("E", (), {"tool_name": "edit", "arguments": {}})(), None
        )
    )

    assert outcome is None
