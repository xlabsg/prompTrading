"""Run one agent backtest in an isolated process.

Isolation is the point, not performance. `run_agent_backtest` installs a
process-wide network guard (`socket` monkeypatch, install-once) whose allowlist
holds only the exchange host, so it cannot share a process with the agent's own
LLM connection -- the guard would block the next model call. Each backtest
therefore runs in a throwaway process that the guard is free to restrict.

Protocol: a JSON request object on stdin, a JSON result object on stdout.

    request  {strategy_path, entry_function, params, dataset, runs_used, max_runs}
    result   {ok, report, metrics}

Budget state lives in the parent: it passes `runs_used` in and records the
returned metrics itself, so history and stall detection survive across runs.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from agent.backtest_tool import BacktestBudget, BacktestDataset, run_agent_backtest


def run_request(request: dict[str, Any]) -> dict[str, Any]:
    """Execute one backtest described by `request` and return its result."""
    dataset = BacktestDataset(**request["dataset"])
    budget = BacktestBudget(
        max_runs=int(request["max_runs"]),
        runs_used=int(request["runs_used"]),
    )
    ok, report, metrics = run_agent_backtest(
        strategy_path=request["strategy_path"],
        entry_function=request["entry_function"],
        dataset=dataset,
        budget=budget,
        params=request.get("params"),
    )
    return {"ok": ok, "report": report, "metrics": metrics}


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        json.dump(
            {"ok": False, "report": f"Malformed backtest request: {exc}", "metrics": None},
            sys.stdout,
        )
        return 1

    try:
        result = run_request(request)
    except Exception as exc:  # noqa: BLE001 - the agent reads this text and retries
        result = {
            "ok": False,
            "report": f"Backtest failed: {type(exc).__name__}: {exc}",
            "metrics": None,
        }

    json.dump(result, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
