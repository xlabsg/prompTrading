"""Tau extension carrying this platform's strategy-authoring domain layer.

Tau supplies the coding agent: the loop, the model providers, `read` / `write` /
`edit` / `bash`, context compaction and session persistence. This module adds
what only this platform knows about -- backtesting a generated strategy against
real market data, and the file protocol a finished strategy has to satisfy.

Loaded in the agent container with `tau -e /app/agent/tau_ext.py`.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from collections.abc import Mapping

import anyio

from tau_agent.messages import TextContent
from tau_agent.tools import (
    AgentTool,
    AgentToolResult,
    ToolCancellationToken,
    ToolUpdateCallback,
)
from tau_agent.types import JSONValue
from tau_coding.extensions import (
    ExtensionAPI,
    ToolCallHookEvent,
    ToolCallHookResult,
    ToolResultHookEvent,
    ToolResultHookResult,
)

from agent.backtest_tool import BacktestBudget, BacktestDataset
from agent.protocol import OVERVIEW_FILE, PROTOCOL, STRATEGY_FILE

# Reference to the active ExtensionAPI for logging custom entries.
_TAU_API: ExtensionAPI | None = None

# One tau process is one agent session, so a module-level dataset and budget are
# that session's dataset and budget. The budget must live here rather than in the
# backtest subprocess: a throwaway process cannot accumulate run history.
_DATASET = BacktestDataset.from_env()
_BUDGET = BacktestBudget.from_env()
_WORKSPACE = os.environ.get("TAU_WORKSPACE") or os.getcwd()


def _workspace_problems(workspace: str) -> list[str]:
    """Return the reasons this workspace is not a finishable strategy, if any."""
    problems: list[str] = []

    strategy_path = os.path.join(workspace, STRATEGY_FILE)
    if not os.path.isfile(strategy_path):
        problems.append(f"- {STRATEGY_FILE} does not exist yet.")
    else:
        source = _read(strategy_path)
        if f"def {PROTOCOL.entry_function}" not in source:
            problems.append(
                f"- {STRATEGY_FILE} has no {PROTOCOL.entry_function}() entry point."
            )
        else:
            try:
                from agent.strategy_lint import lint_and_heal_strategy_code, dry_run_strategy
                healed, fixes = lint_and_heal_strategy_code(source)
                if fixes:
                    with open(strategy_path, "w", encoding="utf-8") as f:
                        f.write(healed)
                    source = healed
                ok, err = dry_run_strategy(source)
                if not ok:
                    problems.append(
                        f"- {STRATEGY_FILE} failed dry-run execution: {err}. "
                        f"Ensure {PROTOCOL.entry_function}(data, params) runs cleanly without errors and returns valid target_weights."
                    )
            except Exception as e:
                problems.append(f"- {STRATEGY_FILE} validation error: {e}")

    overview_path = os.path.join(workspace, OVERVIEW_FILE)
    if not os.path.isfile(overview_path):
        problems.append(f"- {OVERVIEW_FILE} does not exist yet.")
    elif PROTOCOL.overview_required_marker not in _read(overview_path):
        problems.append(
            f"- {OVERVIEW_FILE} has no {PROTOCOL.overview_required_marker} diagram block."
        )

    return problems


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


async def _run_backtest(
    tool_call_id: str,
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
    on_update: ToolUpdateCallback | None = None,
) -> AgentToolResult:
    """Backtest the current strategy in a throwaway process.

    The subprocess is required, not an optimisation. `run_agent_backtest`
    installs a process-wide network guard that only allows the exchange host, so
    running it here would block tau's own next call to the model provider.
    """
    del tool_call_id, signal, on_update

    request = {
        "strategy_path": os.path.join(_WORKSPACE, STRATEGY_FILE),
        "entry_function": str(
            arguments.get("entry_function") or PROTOCOL.entry_function
        ),
        "params": arguments.get("params"),
        "dataset": dataclasses.asdict(_DATASET),
        "runs_used": _BUDGET.runs_used,
        "max_runs": _BUDGET.max_runs,
    }

    completed = await anyio.run_process(
        [sys.executable, "-m", "agent.backtest_subprocess"],
        input=json.dumps(request).encode("utf-8"),
        check=False,
    )

    result = _decode_result(completed.stdout, completed.returncode)
    metrics = result.get("metrics")
    if isinstance(metrics, dict):
        _BUDGET.record(metrics)

    report = str(result.get("report") or "")
    if _BUDGET.stalled():
        report += (
            f"\n\nThe last {_BUDGET.stall_limit} runs did not improve "
            f"{_BUDGET.score_key}. Prefer finalising over another parameter tweak."
        )

    if _TAU_API is not None and isinstance(metrics, dict):
        try:
            params_dict = (
                dict(arguments.get("params"))
                if isinstance(arguments.get("params"), Mapping)
                else {}
            )
            await _TAU_API.append_entry(
                "promptrading.backtest",
                {
                    "run": _BUDGET.runs_used,
                    "max_runs": _BUDGET.max_runs,
                    "params": params_dict,
                    "metrics": metrics,
                    "ok": bool(result.get("ok")),
                },
            )
        except Exception as exc:
            print(f"[agent] tau append_entry failed: {exc}", file=sys.stderr)

    return AgentToolResult(
        content=[TextContent(text=report)],
        details={"metrics": metrics, "ok": bool(result.get("ok"))},
    )


def _decode_result(stdout: bytes, returncode: int) -> dict[str, object]:
    try:
        decoded = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        decoded = None
    if isinstance(decoded, dict):
        return decoded
    return {
        "ok": False,
        "report": f"Backtest process exited with code {returncode} and no readable result.",
        "metrics": None,
    }


async def _task_done(
    tool_call_id: str,
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
    on_update: ToolUpdateCallback | None = None,
) -> AgentToolResult:
    """Declare the strategy finished, or explain why it is not.

    This tool cannot end the loop: `AgentToolResult.terminate` is declared in tau
    0.4.1 but never read. The driver decides when the session is done, by
    validating the workspace after the agent settles. What this tool buys is
    telling the model about a missing artifact while it is still working, rather
    than after the driver has to send it back for another round.
    """
    del tool_call_id, signal, on_update

    problems = _workspace_problems(_WORKSPACE)
    if problems:
        return AgentToolResult(
            content=[
                TextContent(
                    text="Cannot finish yet:\n" + "\n".join(problems),
                )
            ],
            details={"complete": False, "problems": problems},
        )

    summary = str(arguments.get("summary") or "").strip()
    return AgentToolResult(
        content=[TextContent(text=f"Task complete. {summary}".strip())],
        details={"complete": True, "summary": summary},
    )


async def _block_exhausted_backtest(
    event: ToolCallHookEvent,
    context: object,
) -> ToolCallHookResult | None:
    """Stop the model from spending turns on a backtest budget that is gone."""
    del context
    if event.tool_name != "backtest" or not _BUDGET.exhausted:
        return None
    return ToolCallHookResult(
        block=True,
        reason=(
            f"Backtest budget exhausted ({_BUDGET.max_runs} runs used). "
            "Finalise the strategy and call task_done."
        ),
    )


_BACKTEST_TOOL = AgentTool(
    name="backtest",
    label="backtest",
    description=(
        f"Backtest {STRATEGY_FILE} against real cached market data and return its "
        "performance metrics. Use it to check that a strategy actually works, and "
        "to compare a change against the previous run."
    ),
    parameters={
        "type": "object",
        "properties": {
            "entry_function": {
                "type": "string",
                "description": (
                    f"Entry point to backtest. Defaults to {PROTOCOL.entry_function}."
                ),
            },
            "params": {
                "type": "object",
                "description": "Strategy parameters to override for this run.",
            },
        },
    },
    execute_fn=_run_backtest,
    prompt_snippet="Backtest the strategy against real market data.",
)

_TASK_DONE_TOOL = AgentTool(
    name="task_done",
    label="task_done",
    description=(
        "Declare the strategy finished. Refuses while a required artifact is "
        "missing and tells you which one."
    ),
    parameters={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One or two sentences on what the strategy does.",
            },
        },
    },
    execute_fn=_task_done,
    prompt_snippet="Declare the strategy finished once both artifacts exist.",
)


def _protocol_section() -> str:
    return (
        f"A finished strategy is two files in the working directory.\n\n"
        f"- `{STRATEGY_FILE}` defines `{PROTOCOL.entry_function}()`, the entry point "
        f"the platform calls.\n"
        f"- `{OVERVIEW_FILE}` explains the strategy and contains a "
        f"`{PROTOCOL.overview_required_marker}` diagram of its decision flow.\n\n"
        f"The platform also writes `{PROTOCOL.spec_file}`, "
        f"`{PROTOCOL.params_schema_file}` and `{PROTOCOL.meta_file}` itself; leave "
        f"those alone."
    )


def _budget_section() -> str:
    return (
        f"`backtest` runs against {_DATASET.describe()} "
        f"({_DATASET.bars} bars) and is capped at {_BUDGET.max_runs} runs for this "
        f"session. The metric to improve is `{_BUDGET.score_key}`.\n\n"
        f"Spend the budget on changes you have a reason to believe in. When "
        f"repeated runs stop moving `{_BUDGET.score_key}`, finalise instead of "
        f"tweaking further."
    )


def _quant_toolkit_section() -> str:
    return (
        "The CLI utility `pt-quant` is installed and available in bash:\n"
        "- `pt-quant inspect-data`: View dataset time range, frequency, volatility, and ATR before designing logic.\n"
        "- `pt-quant check strategy.py`: Statically verify syntax, imports, and scan for lookahead leaks.\n"
        "- `pt-quant dry-run strategy.py`: Fast in-memory execution to verify target_weights output contract.\n"
        "- `pt-quant indicators [name]`: Inspect platform built-in vectorized indicators and their parameter signatures.\n\n"
        "Domain guidance skills are available in `.tau/skills/` (e.g. `data-exploration`, `quant-indicators`, `alpha-patterns`, `risk-management`, `backtest-optimization`). Read them with `read` when needed."
    )


def setup(tau: ExtensionAPI) -> None:
    """Register this platform's tools, protocol and budget with the session."""
    global _TAU_API
    _TAU_API = tau
    tau.register_tool(_BACKTEST_TOOL)
    tau.register_tool(_TASK_DONE_TOOL)
    tau.add_prompt_section("Strategy Protocol", _protocol_section())
    tau.add_prompt_section("Backtest Budget", _budget_section())
    tau.add_prompt_section("Quant Toolkit & Skills", _quant_toolkit_section())
    tau.add_prompt_guideline(
        f"Write both {STRATEGY_FILE} and {OVERVIEW_FILE}, then call task_done."
    )
    tau.on("tool_call", _block_exhausted_backtest)
    if os.getenv("AGENT_TAU_LINT_HOOK", "1") != "0":
        tau.on("tool_result", _audit_code_tool_result)


async def _audit_code_tool_result(
    event: ToolResultHookEvent,
    context: object,
) -> ToolResultHookResult | None:
    """Inspect strategy.py changes on write/edit to provide immediate static feedback."""
    del context
    if event.tool_name not in ("write", "edit"):
        return None

    path_arg = str(event.arguments.get("path") or "")
    if not (path_arg == STRATEGY_FILE or path_arg.endswith("/" + STRATEGY_FILE)):
        return None

    strategy_path = os.path.join(_WORKSPACE, STRATEGY_FILE)
    if not os.path.isfile(strategy_path):
        return None

    source = _read(strategy_path)
    if not source:
        return None

    issues: list[str] = []
    if f"def {PROTOCOL.entry_function}" not in source:
        issues.append(
            f"Missing required entry point: `def {PROTOCOL.entry_function}(data, params)`."
        )

    try:
        from agent.strategy_lint import dry_run_strategy, lint_and_heal_strategy_code

        healed, fixes = lint_and_heal_strategy_code(source)
        if fixes:
            with open(strategy_path, "w", encoding="utf-8") as handle:
                handle.write(healed)
            source = healed
        ok, dry_err = dry_run_strategy(source)
        if not ok:
            issues.append(f"Dry-run execution failed: {dry_err}")
    except SyntaxError as exc:
        issues.append(f"Syntax error: {exc}")
    except Exception as exc:
        issues.append(f"Validation error: {exc}")

    if not issues:
        return None

    existing_text = event.result.text or ""
    warning_block = (
        "\n\n[WARNING - STRATEGY CODE VALIDATION ISSUE DETECTED]\n"
        + "\n".join(f"- {issue}" for issue in issues)
        + f"\nPlease fix the above issue(s) in {STRATEGY_FILE} immediately before calling backtest or task_done."
    )
    return ToolResultHookResult(content=existing_text + warning_block)
