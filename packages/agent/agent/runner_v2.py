"""Container entry point for strategy generation and refinement.

Drives a Tau coding session inside the version workspace: the agent reads
existing code, edits files with exact-match replacement, backtests against real
cached market data under a bounded run budget, and finishes by calling
task_done. This module owns everything around that session -- seeding the
workspace, validating what came out of it, and publishing to the live strategy
directory -- while Tau owns the agent loop itself.

Usage:
    # STRATEGY_ID=strategy_123
    # VERSION_ID=version_456
    # PROMPT="Create a moving average crossover strategy"
    python -m agent.runner_v2
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional

from agent import tau_driver
from agent.backtest_tool import BacktestBudget, BacktestDataset, budget_summary
from agent.observability.langfuse_client import get_langfuse
from agent.observability.metrics import SessionMetrics
from agent.protocol import OVERVIEW_FILE, STRATEGY_FILE
from agent.tau_config import ensure_catalog_entry, resolve_provider
from agent.templates import (
    DEFAULT_STRATEGY_PROTOCOL,
    DEFAULT_STRATEGY_SPEC_YAML,
    fallback_strategy_py,
)

# Path the extension is mounted at inside the agent image.
TAU_EXTENSION_PATH = os.getenv("AGENT_TAU_EXTENSION") or "/app/agent/tau_ext.py"


@dataclass(frozen=True)
class StrategyResult:
    """Result from strategy generation."""

    code: str
    used_llm: bool
    model: str | None
    metadata: dict[str, Any] | None = None


# ============== Utility Functions ==============

def _env(name: str, default: str | None = None) -> str:
    """Get environment variable or raise."""
    v = os.getenv(name)
    if v is None or v == "":
        if default is None:
            raise RuntimeError(f"missing_env:{name}")
        return default
    return v


def _maybe_env(name: str) -> Optional[str]:
    """Get environment variable or return None."""
    v = os.getenv(name)
    if v is None or v == "":
        return None
    return v


def _ensure_dir(path: str) -> None:
    """Ensure directory exists."""
    os.makedirs(path, exist_ok=True)


def _write_text(path: str, text: str) -> None:
    """Write text to file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _write_json(path: str, payload: Any) -> None:
    """Write JSON to file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)


def _read_text(path: str) -> str:
    """Read text from file."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_json(path: str) -> dict[str, Any] | None:
    """Read JSON from file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _platform_capabilities() -> dict[str, Any]:
    """Get platform capabilities."""
    indicators: list[str] = []
    excluded_names = {
        "SeriesLike", "Union", "wraps", "wrapped_func", "chain", "get_compatibility",
        "get_function_groups", "get_functions", "get_unstable_period", "set_compatibility",
        "set_unstable_period", "ceil", "floor", "exp", "ln", "log10", "cos", "cosh",
        "sin", "sinh", "tan", "tanh", "sqrt", "add", "sub", "mult", "div"
    }
    try:
        from backtest import indicators as bt_indicators

        for name in dir(bt_indicators):
            if name.startswith("_") or name in excluded_names:
                continue
            value = getattr(bt_indicators, name, None)
            if callable(value):
                indicators.append(name)
        indicators.sort()
    except Exception:
        indicators = [
            "sma",
            "ema",
            "rsi",
            "macd",
            "bbands",
            "atr",
            "zscore",
            "cross_over",
            "cross_under",
        ]

    # Core indicator signatures for direct reference
    common_indicator_signatures = {
        "sma": "sma(x: Series, window: int = 10) -> pd.Series",
        "ema": "ema(x: Series, window: int = 10) -> pd.Series",
        "rsi": "rsi(close: Series, window: int = 14) -> pd.Series",
        "atr": "atr(high: Series, low: Series, close: Series, window: int = 14) -> pd.Series",
        "bbands": "bbands(close: Series, timeperiod: int = 20, nbdevup: float = 2.0, nbdevdn: float = 2.0) -> (upper, middle, lower)",
        "macd": "macd(close: Series, fastperiod: int = 12, slowperiod: int = 26, signalperiod: int = 9) -> (macd, signal, hist)",
        "cross_over": "cross_over(a: Series, b: Series) -> pd.Series (bool)",
        "cross_under": "cross_under(a: Series, b: Series) -> pd.Series (bool)",
        "zscore": "zscore(x: Series, window: int) -> pd.Series",
    }

    return {
        "engine": "vectorized",
        "signal_modes": ["target_weights"],
        "required_function": "generate_signals",
        "data_schema": {
            "columns": ["timestamp", "open", "high", "low", "close", "volume"],
        },
        "common_indicator_signatures": common_indicator_signatures,
        "available_indicators": indicators,
        "notes": {
            "import": "Import built-in indicators via: from backtest.indicators import sma, rsi, ...",
            "inspection": "Run `pt-quant indicators <name>` in bash to see full docstring and parameter signatures.",
        },
        "validation_tools": ["pt-quant check strategy.py", "pt-quant dry-run strategy.py"],
        "restrictions": [
            "no_network_access_in_strategy_code",
            "no_file_io_in_strategy_code",
            "deterministic_only",
        ],
    }


def _validate_strategy_code(code: str) -> None:
    """Validate that code has generate_signals function."""
    tree = ast.parse(code)
    has_fn = any(
        isinstance(n, ast.FunctionDef) and n.name == "generate_signals"
        for n in tree.body
    )
    if not has_fn:
        raise ValueError("generated_code_missing_generate_signals")


def _default_overview_markdown(summary: str) -> str:
    """Build a deterministic fallback overview markdown."""
    safe_summary = summary.strip() or "Strategy overview is not available yet."
    return (
        "# Summary\n\n"
        f"{safe_summary}\n\n"
        "# Trading Board\n\n"
        "- Focus: monitor K-line and equity behavior, position bias, and PnL health.\n"
        "- Suggested widgets: Price/Equity Candles, Signal Markers, Net PnL, Max Drawdown.\n"
        "- Risk cue: when drawdown expands while signal density rises, reduce risk.\n\n"
        "# Flow Animation\n\n"
        "```mermaid\n"
        "flowchart TD\n"
        "  A[Market Data Tick] --> B[Feature & Indicator Engine]\n"
        "  B --> C{State Router}\n"
        "  C -->|entry| D[Open Position]\n"
        "  C -->|rebalance| E[Adjust Weights]\n"
        "  D --> F[Risk Monitor]\n"
        "  E --> F\n"
        "  F -->|exit| G[Close Position]\n"
        "  G --> A\n"
        "```\n"
    )


def _ensure_overview_sections(markdown: str, summary: str) -> str:
    """Ensure overview markdown has minimal required sections for UI rendering."""
    value = (markdown or "").strip()
    if not value:
        return _default_overview_markdown(summary)

    lower = value.lower()
    if "summary" not in lower:
        value = f"# Summary\n\n{summary.strip() or 'Strategy summary unavailable.'}\n\n{value}"
        lower = value.lower()

    if "trading board" not in lower:
        value += (
            "\n\n# Trading Board\n\n"
            "- Focus on price structure, equity curve behavior, and risk state.\n"
            "- Watch net PnL, drawdown, and signal density together.\n"
        )
        lower = value.lower()

    if "flow animation" not in lower:
        value += "\n\n# Flow Animation\n"

    if "```mermaid" not in lower:
        value += (
            "\n\n```mermaid\n"
            "flowchart TD\n"
            "  A[Market Data Tick] --> B[Signal Engine]\n"
            "  B --> C{Decision}\n"
            "  C -->|entry| D[Open Position]\n"
            "  C -->|rebalance| E[Adjust Position]\n"
            "  D --> F[Risk Monitor]\n"
            "  E --> F\n"
            "  F -->|exit| G[Close Position]\n"
            "  G --> A\n"
            "```\n"
        )

    return value.strip() + "\n"


def _git_commit(strategy_dir: str, message: str) -> None:
    """Git commit changes."""
    git_dir = os.path.join(strategy_dir, ".git")
    if not os.path.exists(git_dir):
        return

    try:
        subprocess.run(
            ["git", "add", "."],
            cwd=strategy_dir,
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=strategy_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"[agent] git commit: {message[:60]}...")
    except Exception as e:
        print(f"[agent] git commit failed: {e}")


# ============== Main Runner ==============

AGENT_TASK_TEMPLATE = """{intent}

## Request
{prompt}

## Workspace
You are working inside the strategy version workspace. Files present: {files}

## Deliverables (both required before `task_done`)
1. `{strategy_file}` exposing `generate_signals(data, params) -> dict`.
2. `{overview_file}` containing a `# Summary` section and a ```mermaid diagram.

## Contract for `generate_signals`
- `data` is a pandas DataFrame with columns: timestamp, open, high, low, close, volume.
- Return a dict containing:
  - `target_weights`: float array of length n, each in [-1, 1]
  - `weight_reason`: list of n short strings (e.g. 'regime_long', 'reduce_risk')
  - 2-6 bar-aligned debug arrays (indicator or condition values)
- Signal logic best practice:
  - DO NOT use chained slice assignment like `data['signal'][...] = ...` or `data['reason'][mask] = ...` (pandas 2+ Copy-on-Write causes silent zeros and ChainedAssignmentError).
  - Use `np.where(condition, 1.0, np.where(short_condition, -1.0, 0.0))` or `.loc[mask, 'col'] = ...` instead.
- Use `.to_numpy()` on pandas Series, never pass raw Series.
- No network access, no file I/O, deterministic only.

## Platform capabilities
{capabilities}

## How to work
- **Priority Action**: Write `{strategy_file}` immediately using `write` in your first turn! Do not spend rounds reading documentation before writing the code.
- Always use tools (`write`, `edit`) directly to modify files. Do not output raw tool calls like `functions.write(...)` as code blocks in text.
- Read before you edit. `edit` matches text exactly, so read the file first and
  reproduce the target text verbatim.
- After writing `{strategy_file}`, call `backtest` to evaluate it on real market
  data, then use the reported metrics to improve the strategy.
- You have at most {max_runs} backtest runs. Spend them deliberately: change
  something specific each time and check whether {score_key} improves.
- Stop tuning when the budget is spent or the metrics stop improving, then
  write `{overview_file}` and call `task_done`.
- You can run `pt-quant inspect-data`, `pt-quant check strategy.py`, `pt-quant dry-run strategy.py`, or `pt-quant indicators` using `bash`.
- On-demand quant skills (indicators, patterns, risk, optimization) are available under `.tau/skills/`. Read them with `read` if you need formula or convention guidance.
"""


def _seed_skills(version_dir: str) -> None:
    """Ensure built-in .tau/skills are populated in the workspace for on-demand inspection."""
    if os.getenv("AGENT_TAU_SKILLS", "1") == "0":
        return
    import shutil

    target_skills_dir = os.path.join(version_dir, ".tau", "skills")
    os.makedirs(target_skills_dir, exist_ok=True)
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "skills"),  # local dev / git repo
        "/app/skills",  # container runtime
        "/root/.tau/skills",  # container home
    ]
    for src_dir in candidates:
        if os.path.isdir(src_dir):
            for entry in os.listdir(src_dir):
                skill_dir = os.path.join(src_dir, entry)
                dst_skill_dir = os.path.join(target_skills_dir, entry)
                if os.path.isdir(skill_dir) and not os.path.exists(dst_skill_dir):
                    try:
                        shutil.copytree(skill_dir, dst_skill_dir)
                    except Exception:
                        pass
            break


def _seed_workspace(version_dir: str, strategy_dir: str) -> list[str]:
    """Copy the current strategy into the version workspace the agent edits.

    The agent works on the version directory so a run is reproducible and never
    corrupts the live strategy; `strategy_dir` is only updated after success.
    """
    _seed_skills(version_dir)
    seeded: list[str] = []
    for name in (
        "strategy.py",
        "strategy_spec.yaml",
        "strategy_protocol.json",
        "params_schema.json",
        "strategy_meta.json",
        "overview.md",
    ):
        src = os.path.join(strategy_dir, name)
        dst = os.path.join(version_dir, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            try:
                with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                    fdst.write(fsrc.read())
                seeded.append(name)
            except OSError:
                continue
    return seeded


def _build_agent_task(
    *,
    prompt: str,
    is_first_generation: bool,
    files: list[str],
    capabilities: dict[str, Any],
    budget: BacktestBudget,
) -> str:
    intent = (
        "Create a new trading strategy from scratch."
        if is_first_generation
        else "Modify the existing trading strategy in this workspace."
    )
    return AGENT_TASK_TEMPLATE.format(
        intent=intent,
        prompt=prompt.strip() or "Improve the strategy.",
        files=", ".join(sorted(files)) or "(empty workspace)",
        strategy_file=STRATEGY_FILE,
        overview_file=OVERVIEW_FILE,
        capabilities=json.dumps(capabilities, ensure_ascii=False, indent=2),
        max_runs=budget.max_runs,
        score_key=budget.score_key,
    )


def _require_model_progress(session: "tau_driver.TauSessionResult") -> None:
    """Fail a session that never reached the model.

    Tau settles whenever the model stops calling tools -- including when every
    model call failed, in which case it echoes the task straight back as the
    summary. Refine seeds the version workspace from the live strategy, so the
    workspace already validates and such a run would otherwise publish an
    unchanged strategy, report success, and show the task prompt to the user as
    the agent's answer. A session that reached the provider always spends
    tokens, so zero tokens with no tool calls means nothing ran.
    """
    tokens = session.tokens if isinstance(session.tokens, dict) else {}
    if int(tokens.get("total") or 0) > 0 or session.tool_calls:
        return
    raise tau_driver.TauSessionError(
        "agent_made_no_model_progress: the session spent 0 tokens and called no "
        "tools, so the model provider was never reached"
    )


def _session_stats(session: "tau_driver.TauSessionResult | None") -> dict[str, Any]:
    """Flatten a Tau session into the shape `llm_meta.json` records."""
    if session is None:
        return {}
    return {
        "session_id": session.session_id,
        "trace_html_path": session.trace_html_path,
        "turns": session.turns,
        "follow_ups": session.follow_ups,
        "tool_calls": session.tool_calls,
        "tool_errors": session.tool_errors,
        "compactions": session.compactions,
        "auto_retries": session.auto_retries,
        "turn_limit_hit": session.turn_limit_hit,
        "tokens": session.tokens,
        "cost_usd": session.cost_usd,
    }


def _heal_from_message_text(version_dir: str, text: str) -> None:
    """If the LLM outputted tool calls or markdown blocks in text, extract and write to disk."""
    if not text:
        return
    import re

    # Check for functions.write({"path": "...", "content": "..."})
    write_pattern = re.compile(r'functions\.write\(\s*(\{.*?\})\s*\)', re.DOTALL)
    for match in write_pattern.finditer(text):
        try:
            payload = json.loads(match.group(1))
            path = payload.get("path")
            content = payload.get("content")
            if path and content:
                dest = os.path.join(version_dir, path)
                _write_text(dest, content)
                print(f"[agent] auto-healed {path} from model text function call")
        except Exception:
            pass

    # Check for markdown python code block with generate_signals if strategy.py missing or invalid
    strat_path = os.path.join(version_dir, STRATEGY_FILE)
    needs_strat = True
    if os.path.isfile(strat_path):
        try:
            _validate_strategy_code(_read_text(strat_path))
            needs_strat = False
        except Exception:
            needs_strat = True

    if needs_strat:
        py_pattern = re.compile(r'```python\s*(.*?def generate_signals.*?)\s*```', re.DOTALL)
        py_match = py_pattern.search(text)
        if py_match:
            try:
                candidate = py_match.group(1).strip() + "\n"
                _validate_strategy_code(candidate)
                _write_text(strat_path, candidate)
                print("[agent] auto-healed strategy.py from markdown codeblock in text")
            except Exception:
                pass


def _print_progress(event: dict[str, Any]) -> None:
    """Echo one driver event to the container log.

    The worker kills a container that has produced no output for
    `AGENT_IDLE_TIMEOUT_S`. Without this the whole Tau session is silent on
    stdout, so a healthy agent looked identical to a hung one.

    The `path=` field is the only channel the API has for telling the user which
    file the agent is touching: chat refine reads these lines back off the job
    log, so keep the shape parseable.
    """
    phase = event.get("phase")
    if phase == "thinking":
        msg = str(event.get("message") or "大模型思考与策略逻辑推演中...")
        print(f"[agent] {msg}", flush=True)
        evt = {
            "type": "progress",
            "stage": "thinking",
            "phase": "thinking",
            "message": msg,
            "ts": time.time(),
        }
        print(f"[agent:event] {json.dumps(evt, ensure_ascii=False)}", flush=True)
    elif phase == "tool_start":
        args = event.get("args")
        path = str(args.get("path") or "") if isinstance(args, dict) else ""
        suffix = f" path={os.path.basename(path)}" if path else ""
        tool_name = str(event.get("tool") or "")
        fname = os.path.basename(path) if path else ""
        print(f"[agent] tool {tool_name}{suffix} ...", flush=True)
        if tool_name == "backtest":
            msg = "正在进行历史数据回测计算..."
        elif tool_name == "bash":
            msg = "正在执行沙箱语法与未来函数审计..."
        elif tool_name == "task_done":
            msg = "策略生成完毕，正在发布交付物..."
        elif fname:
            action_text = "修改" if tool_name in {"edit_file", "write_file", "edit", "write"} else "阅读"
            msg = f"正在{action_text} {fname}..."
        else:
            msg = f"正在执行 {tool_name}..."
        evt = {
            "type": "tool_start",
            "tool": tool_name,
            "path": fname,
            "phase": "tool_start",
            "message": msg,
            "ts": time.time(),
        }
        print(f"[agent:event] {json.dumps(evt, ensure_ascii=False)}", flush=True)
    elif phase == "tool_end":
        outcome = "error" if event.get("is_error") else "ok"
        tool_name = str(event.get("tool") or "")
        print(f"[agent] tool {tool_name} {outcome}", flush=True)
        end_msg = None
        if tool_name == "backtest":
            end_msg = "回测计算完成，正在评估指标..." if outcome == "ok" else "回测执行失败"
        evt = {
            "type": "tool_end",
            "tool": tool_name,
            "success": not bool(event.get("is_error")),
            "message": end_msg,
            "ts": time.time(),
        }
        print(f"[agent:event] {json.dumps(evt, ensure_ascii=False)}", flush=True)
    elif phase == "message":
        text = " ".join(str(event.get("text") or "").split())
        if text:
            print(f"[agent] {text[:200]}", flush=True)
            evt = {
                "type": "token",
                "content": text[:200],
                "ts": time.time(),
            }
            print(f"[agent:event] {json.dumps(evt, ensure_ascii=False)}", flush=True)


def _workspace_problems(version_dir: str, message_text: str | None = None) -> list[str]:
    """Report why `version_dir` is not yet a publishable strategy.

    This is the session's completion test. Tau's loop ends whenever the model
    stops calling tools, so the driver -- not the model -- decides whether the
    work is done, and sends the model back with this list when it is not.
    """
    if message_text:
        _heal_from_message_text(version_dir, message_text)

    problems: list[str] = []

    strategy_path = os.path.join(version_dir, STRATEGY_FILE)
    if not os.path.isfile(strategy_path):
        problems.append(f"- {STRATEGY_FILE} does not exist.")
    else:
        try:
            code = _read_text(strategy_path)
            _validate_strategy_code(code)
            from agent.strategy_lint import lint_and_heal_strategy_code, dry_run_strategy
            healed, fixes = lint_and_heal_strategy_code(code)
            if fixes:
                _write_text(strategy_path, healed)
                print(f"[agent] Auto-healed strategy.py imports: {fixes}")
                code = healed
            ok, dry_err = dry_run_strategy(code)
            if not ok:
                problems.append(
                    f"- {STRATEGY_FILE} failed dry-run execution: {dry_err}. "
                    "Ensure generate_signals(data, params) runs cleanly without errors and returns valid target_weights."
                )
        except SyntaxError as exc:
            problems.append(f"- {STRATEGY_FILE} does not parse: {exc}")
        except ValueError:
            problems.append(
                f"- {STRATEGY_FILE} has no generate_signals() entry point."
            )
        except OSError as exc:
            problems.append(f"- {STRATEGY_FILE} could not be read: {exc}")

    # Note: overview.md is non-blocking. If absent or missing mermaid block,
    # _ensure_overview_sections will auto-generate it from strategy metadata.
    return problems


def main() -> int:
    """Run the coding agent for one generate/refine job."""
    strategy_id = _env("STRATEGY_ID")
    version_id = _env("VERSION_ID")
    prompt = _env("PROMPT", "")
    workspaces_dir = _env("WORKSPACES_DIR", "/workspaces")

    version_dir = os.path.join(workspaces_dir, strategy_id, "versions", version_id)
    strategy_dir = os.path.join(workspaces_dir, strategy_id, "strategy")
    _ensure_dir(version_dir)
    _ensure_dir(strategy_dir)

    # Load current code to decide between first generation and refinement.
    job_type = os.getenv("JOB_TYPE", "")
    current_code = ""
    current_path = os.path.join(strategy_dir, "strategy.py")
    if os.path.isfile(current_path):
        try:
            current_code = _read_text(current_path)
        except OSError:
            current_code = ""

    if job_type in ("generate_strategy", "generate_and_backtest"):
        is_first_generation = True
    elif job_type == "refine_strategy":
        is_first_generation = False
    else:
        # Fallback check: default scaffold or fallback code means first generation
        is_first_generation = (
            not bool(current_code.strip())
            or "fast = close.rolling(fast_n).mean()" in current_code
            or "Auto-generated strategy (fallback)" in current_code
        )

    if is_first_generation:
        # For first generation, seed specs/protocols, but ensure strategy.py starts clean
        # so the model writes a fresh strategy matching user's requirements
        seeded = [
            name for name in _seed_workspace(version_dir, strategy_dir)
            if name != "strategy.py"
        ]
        strat_target = os.path.join(version_dir, "strategy.py")
        if os.path.isfile(strat_target):
            try:
                os.remove(strat_target)
            except OSError:
                pass
    else:
        seeded = _seed_workspace(version_dir, strategy_dir)
    print(f"[agent] seeded workspace with: {seeded or '(nothing)'} (is_first_generation={is_first_generation})")

    session_metrics = SessionMetrics(session_id=strategy_id)
    platform_caps = _platform_capabilities()

    dataset = BacktestDataset.from_env()
    budget = BacktestBudget.from_env()
    print(f"[agent] backtest dataset={dataset.describe()} budget={budget.max_runs}")

    tau_target = resolve_provider()
    ensure_catalog_entry(tau_target)
    print(f"[agent] tau provider={tau_target.provider} model={tau_target.model}")

    task = _build_agent_task(
        prompt=prompt,
        is_first_generation=is_first_generation,
        files=seeded,
        capabilities=platform_caps,
        budget=budget,
    )

    used_llm = True
    agent_summary = ""
    stop_reason = "task_done"
    agent_error = ""
    session: tau_driver.TauSessionResult | None = None
    force_fallback = (
        (os.getenv("FORCE_FALLBACK") or "").strip().lower() in ("1", "true", "yes")
        or (os.getenv("MOCK_LLM") or "").strip().lower() in ("1", "true", "yes")
    )
    if force_fallback:
        print("[agent] FORCE_FALLBACK enabled: skipping LLM session and writing fallback strategy.")
        code = fallback_strategy_py(prompt)
        used_llm = False
        stop_reason = "forced_fallback"
        _write_text(os.path.join(version_dir, "strategy.py"), code)
    else:
        thinking_level = os.getenv("AGENT_TAU_THINKING_LEVEL")
        parent_session_id = os.getenv("PARENT_TAU_SESSION_ID")
        print(f"[agent:event] {json.dumps({'type': 'step', 'step': 'initializing_agent', 'detail': f'Starting Tau agent with {tau_target.provider}/{tau_target.model}', 'ts': time.time()}, ensure_ascii=False)}", flush=True)
        try:
            session = tau_driver.run_session(
                task=task,
                workspace=version_dir,
                progress_callback=_print_progress,
                provider=tau_target.provider,
                model=tau_target.model,
                extension_path=TAU_EXTENSION_PATH,
                thinking_level=thinking_level,
                session_id=parent_session_id,
                validate=lambda text=None: _workspace_problems(version_dir, text),
                env=tau_target.credential_env(),
            )
            agent_summary = session.summary
            _heal_from_message_text(version_dir, session.summary)
            strat_file = os.path.join(version_dir, "strategy.py")
            code = _read_text(strat_file)
            _validate_strategy_code(code)

            print(f"[agent:event] {json.dumps({'type': 'step', 'step': 'auditing_code', 'detail': 'Validating strategy syntax and imports', 'ts': time.time()}, ensure_ascii=False)}", flush=True)
            # Post-generation static lint & sandbox dry-run
            from agent.strategy_lint import lint_and_heal_strategy_code, dry_run_strategy
            healed, fixes = lint_and_heal_strategy_code(code)
            if fixes:
                _write_text(strat_file, healed)
                print(f"[agent] Post-generation auto-healed imports: {fixes}")
                code = healed
            ok, dry_err = dry_run_strategy(code)
            if not ok:
                print(f"[agent] Post-generation dry-run warning: {dry_err}")
            else:
                print("[agent] Post-generation dry-run smoke test passed (100 synthetic bars evaluated successfully)")

            # Post-generation AST safety and lookahead bias audit
            try:
                from agent.tools import init_default_tools
                tools = init_default_tools()
                auditor = tools.require("ast_auditor")
                audit_res = asyncio.run(auditor.run(code=code))
                if audit_res.success and audit_res.data:
                    issues = audit_res.data.get("issues", [])
                    if issues:
                        print(f"[agent] AST audit detected {len(issues)} issue(s): {issues}")
                    else:
                        print("[agent] AST audit passed (0 lookahead bias or unsafe imports)")
            except Exception as e:
                print(f"[agent] AST audit warning: {e}")

        except Exception as exc:
            print(f"[agent] agent_failed: {exc}", file=sys.stderr)
            strat_path = os.path.join(version_dir, "strategy.py")
            recovered = False
            if session and session.summary:
                _heal_from_message_text(version_dir, session.summary)
            if os.path.isfile(strat_path):
                try:
                    code = _read_text(strat_path)
                    _validate_strategy_code(code)
                    recovered = True
                    stop_reason = "recovered_after_error"
                    agent_error = f"{type(exc).__name__}: {exc}"
                    print("[agent] recovered: strategy.py is valid despite session exception")
                except Exception:
                    recovered = False

            if not recovered:
                fallback_on_error = (
                    (os.getenv("LLM_FALLBACK_ON_ERROR") or "").strip().lower()
                    in ("1", "true", "yes")
                )
                if not fallback_on_error:
                    raise
                # The fallback is a generic MA crossover that has nothing to do
                # with the user's prompt. It is written into the version dir so
                # the failed attempt stays inspectable, but it must never reach
                # the live strategy dir and the job must still report failure --
                # publishing it silently replaced working strategies with a stub.
                code = fallback_strategy_py(prompt)
                used_llm = False
                stop_reason = "error_fallback"
                agent_error = f"{type(exc).__name__}: {exc}"
                _write_text(os.path.join(version_dir, "strategy.py"), code)

    # Checked outside the try above: the recovery branch there would otherwise
    # "recover" a session that never ran, because refine seeds a workspace that
    # already validates.
    if session is not None and stop_reason == "task_done":
        _require_model_progress(session)

    # Spec and protocol are platform-owned; write them if the agent did not.
    for name, payload, writer in (
        ("strategy_spec.yaml", DEFAULT_STRATEGY_SPEC_YAML, _write_text),
        ("strategy_protocol.json", DEFAULT_STRATEGY_PROTOCOL, _write_json),
    ):
        target = os.path.join(version_dir, name)
        if not os.path.isfile(target):
            writer(target, payload)

    params_schema = _build_params_schema(code)
    _write_json(os.path.join(version_dir, "params_schema.json"), params_schema)

    summary = prompt.strip().splitlines()[0][:80] if prompt else "Strategy"
    meta_payload = {
        "version": 1,
        "summary": summary,
        "params_schema": params_schema,
        "signal_mode": DEFAULT_STRATEGY_PROTOCOL.get("signal_mode", "target_weights"),
    }
    _write_json(os.path.join(version_dir, "strategy_meta.json"), meta_payload)

    # The agent is required to produce overview.md; fall back only if it did not.
    overview_path = os.path.join(version_dir, OVERVIEW_FILE)
    if os.path.isfile(overview_path):
        overview_md = _read_text(overview_path)
        overview_status = "agent_generated"
    else:
        overview_md = _default_overview_markdown(summary)
        overview_status = "fallback_missing"
    overview_md = _ensure_overview_sections(overview_md, summary)
    _write_text(overview_path, overview_md)

    # The budget lives in the Tau child (the extension owns it), so replay the
    # metrics the driver collected into this process's budget before recording.
    for metrics in session.backtest_metrics if session else ():
        budget.record(metrics)
    iteration = budget_summary(budget, dataset)
    _write_json(os.path.join(version_dir, "backtest_iterations.json"), iteration)

    llm_meta_payload = {
        "used_llm": used_llm,
        "model": tau_target.model if used_llm else None,
        "provider": tau_target.provider if used_llm else None,
        "base_url": tau_target.base_url if used_llm else None,
        "pipeline": "tau",
        "tau_session_id": session.session_id if session else None,
        "tau_session": _session_stats(session),
        "summary": summary,
        "params_schema": params_schema,
        "signal_mode": DEFAULT_STRATEGY_PROTOCOL.get("signal_mode", "target_weights"),
        "overview_status": overview_status,
        "agent_summary": agent_summary,
        "stop_reason": stop_reason,
        "degraded": stop_reason in ("error_fallback", "recovered_after_error"),
        "agent_error": agent_error,
        "backtest_iterations": iteration,
    }
    _write_json(os.path.join(version_dir, "llm_meta.json"), llm_meta_payload)

    if stop_reason == "error_fallback":
        get_langfuse().flush()
        print(
            f"[agent] error_fallback: keeping {strategy_dir} untouched; "
            f"the fallback strategy is in {version_dir} for inspection.",
            file=sys.stderr,
        )
        raise RuntimeError(f"agent_error_fallback: {agent_error}")

    print(f"[agent:event] {json.dumps({'type': 'step', 'step': 'finalizing_strategy', 'detail': 'Publishing strategy to workspace', 'ts': time.time()}, ensure_ascii=False)}", flush=True)
    # Publish to the live strategy dir only once the version is complete.
    for name in (
        "strategy.py",
        "strategy_spec.yaml",
        "strategy_protocol.json",
        "params_schema.json",
        "strategy_meta.json",
        "tau_trace.html",
        OVERVIEW_FILE,
    ):
        src = os.path.join(version_dir, name)
        if os.path.isfile(src):
            _write_text(os.path.join(strategy_dir, name), _read_text(src))

    commit_msg = f"AI: {prompt[:80]}" if prompt else "AI: strategy update"
    _git_commit(strategy_dir, commit_msg)

    print("\n=== Session Summary ===")
    print(json.dumps(session_metrics.summary(), indent=2))
    print(json.dumps({"backtest_iterations": iteration}, indent=2))
    get_langfuse().flush()

    print(f"[agent:event] {json.dumps({'type': 'done', 'status': 'succeeded', 'summary': agent_summary or summary, 'files_changed': True, 'ts': time.time()}, ensure_ascii=False)}", flush=True)
    print(f"[agent] wrote {STRATEGY_FILE}, strategy_spec.yaml and {OVERVIEW_FILE}")
    return 0


def _build_params_schema(code: str) -> dict[str, Any]:
    """Build params schema from code with inferred bounds."""
    try:
        tree = ast.parse(code)
    except Exception:
        return {"version": 1, "params": []}

    params: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _enrich_entry(entry: dict[str, Any], default_val: Any) -> None:
        entry["default"] = default_val
        if isinstance(default_val, bool):
            entry["type"] = "bool"
        elif isinstance(default_val, int) and not isinstance(default_val, bool):
            entry["type"] = "int"
            entry["min"] = 1 if default_val <= 5 else max(1, int(default_val * 0.2))
            entry["max"] = max(20, int(default_val * 4))
            entry["step"] = 1
        elif isinstance(default_val, float):
            entry["type"] = "float"
            entry["min"] = round(max(0.01, default_val * 0.2), 3)
            entry["max"] = round(max(1.0, default_val * 3.0), 3)
            entry["step"] = 0.01 if default_val < 1.0 else 0.1
        elif isinstance(default_val, str):
            entry["type"] = "str"
        entry["description"] = f"参数 {entry['name']}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr == "get" and isinstance(fn.value, ast.Name) and fn.value.id == "params":
                if node.args and isinstance(node.args[0], ast.Constant):
                    key_val = node.args[0].value
                    if isinstance(key_val, str) and key_val not in seen:
                        seen.add(key_val)
                        entry: dict[str, Any] = {"name": key_val}
                        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                            _enrich_entry(entry, node.args[1].value)
                        params.append(entry)
        elif isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id == "params":
                slice_node = node.slice
                if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                    key_val = slice_node.value
                    if key_val not in seen:
                        seen.add(key_val)
                        params.append({"name": key_val, "type": "float", "description": f"参数 {key_val}"})

    return {"version": 1, "params": params}


if __name__ == "__main__":
    raise SystemExit(main())
