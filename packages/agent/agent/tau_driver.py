"""Drive a Tau coding session over its JSONL RPC frontend.

Tau runs as a child process (`tau --mode rpc`) that reads commands from stdin
and streams events to stdout, one JSON object per line. This module speaks that
protocol from synchronous code, so `runner_v2` keeps its straight-line shape
while the agent itself is asynchronous inside the child.

The session ends when the workspace holds a valid strategy, not when the model
says so. Tau's loop stops whenever the model stops calling tools, and
`AgentToolResult.terminate` -- which would let `task_done` stop it deliberately --
is declared but never read in tau 0.4.1. So the driver validates the workspace
after the agent settles and sends the model back to work if something is missing.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

# Emitted once the agent has stopped and its message queue has drained. Not to be
# confused with `agent_end`, which carries `will_retry` and fires again for every
# automatic retry.
_SETTLED = "agent_settled"

_DEFAULT_EVENT_TIMEOUT_S = 300.0
_DEFAULT_MAX_FOLLOW_UPS = 2
_SHUTDOWN_GRACE_S = 10.0


class TauSessionError(RuntimeError):
    """The Tau session could not be driven to a usable result."""


@dataclass
class TauSessionResult:
    """What one driven Tau session produced."""

    summary: str = ""
    turns: int = 0
    follow_ups: int = 0
    tool_calls: dict[str, int] = field(default_factory=dict)
    tool_errors: dict[str, int] = field(default_factory=dict)
    backtest_metrics: list[dict[str, Any]] = field(default_factory=list)
    compactions: int = 0
    auto_retries: int = 0
    tokens: dict[str, Any] = field(default_factory=dict)
    cost_usd: float | None = None


ProgressCallback = Callable[[dict[str, Any]], None]
Validator = Callable[[], list[str]]


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


class _EventReader:
    """Read child stdout on a thread so the driver can time out waiting on it."""

    def __init__(self, stream: Any) -> None:
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread = threading.Thread(target=self._pump, args=(stream,), daemon=True)
        self._thread.start()

    def _pump(self, stream: Any) -> None:
        try:
            for line in stream:
                self._queue.put(line)
        except (ValueError, OSError):
            # The stream was closed underneath us; treat it as end of output.
            pass
        finally:
            self._queue.put(None)

    def next_line(self, timeout_s: float) -> str | None:
        """Return the next line, or None once the child closes stdout.

        Raises `queue.Empty` when nothing arrives within `timeout_s`.
        """
        return self._queue.get(timeout=timeout_s)


def build_command(
    *,
    workspace: str,
    provider: str,
    model: str,
    extension_path: str | None = None,
    tau_executable: str | None = None,
) -> list[str]:
    """Build the argv for the Tau child process.

    `--model` is always passed explicitly: without it Tau falls back to the
    provider's `default_model`, which is not necessarily the model configured for
    this platform even when the base URL points elsewhere.
    """
    executable = tau_executable or os.getenv("TAU_EXECUTABLE") or "tau"
    command = [
        executable,
        "--mode",
        "rpc",
        "--cwd",
        workspace,
        "--provider",
        provider,
        "--model",
        model,
    ]
    if extension_path:
        command += ["-e", extension_path]
    return command


def run_session(
    *,
    task: str,
    workspace: str,
    provider: str,
    model: str,
    validate: Validator,
    extension_path: str | None = None,
    progress_callback: ProgressCallback | None = None,
    tau_executable: str | None = None,
    env: dict[str, str] | None = None,
) -> TauSessionResult:
    """Run `task` in a Tau session until `validate` reports no problems.

    `validate` returns a list of human-readable problems with the workspace; an
    empty list means the session succeeded. Each non-empty result is sent back to
    the model as a follow-up message, up to `AGENT_TAU_MAX_FOLLOW_UPS` times.
    """
    command = build_command(
        workspace=workspace,
        provider=provider,
        model=model,
        extension_path=extension_path,
        tau_executable=tau_executable,
    )
    child_env = {**os.environ, "TAU_WORKSPACE": workspace}
    if env:
        child_env.update(env)

    event_timeout_s = _env_float("AGENT_TAU_EVENT_TIMEOUT_S", _DEFAULT_EVENT_TIMEOUT_S)
    max_follow_ups = _env_int("AGENT_TAU_MAX_FOLLOW_UPS", _DEFAULT_MAX_FOLLOW_UPS)

    print(f"[agent] starting tau: {' '.join(command)}", flush=True)

    proc = subprocess.Popen(  # noqa: S603 - argv is built from configuration, not user text
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,  # tau's own diagnostics go straight to the container log
        text=True,
        bufsize=1,
        cwd=workspace,
        env=child_env,
    )

    result = TauSessionResult()
    try:
        _drive(
            proc=proc,
            task=task,
            validate=validate,
            result=result,
            progress_callback=progress_callback,
            event_timeout_s=event_timeout_s,
            max_follow_ups=max_follow_ups,
        )
    finally:
        _shutdown(proc)

    return result


def _drive(
    *,
    proc: subprocess.Popen[str],
    task: str,
    validate: Validator,
    result: TauSessionResult,
    progress_callback: ProgressCallback | None,
    event_timeout_s: float,
    max_follow_ups: int,
) -> None:
    assert proc.stdout is not None
    reader = _EventReader(proc.stdout)

    message = task
    behavior: str | None = None
    problems: list[str] = []

    for attempt in range(max_follow_ups + 1):
        _send(proc, _prompt_command(attempt + 1, message, behavior))
        _consume_until_settled(
            reader=reader,
            result=result,
            progress_callback=progress_callback,
            event_timeout_s=event_timeout_s,
            proc=proc,
        )

        problems = validate()
        if not problems:
            _collect_stats(proc, reader, result, event_timeout_s)
            return

        result.follow_ups += 1
        if attempt == max_follow_ups:
            break

        print(
            f"[agent] workspace incomplete after settle, sending follow-up "
            f"({attempt + 1}/{max_follow_ups}): {problems}",
            flush=True,
        )
        message = (
            "The work is not finished. The following are still missing or wrong:\n"
            + "\n".join(problems)
            + "\nFix them, then call task_done."
        )
        behavior = "followUp"

    raise TauSessionError(
        "agent_incomplete_after_follow_ups: " + "; ".join(problems)
    )


def _collect_stats(
    proc: subprocess.Popen[str],
    reader: _EventReader,
    result: TauSessionResult,
    event_timeout_s: float,
) -> None:
    """Record what the session cost, for the run's `llm_meta`.

    Best effort: a session that produced good artifacts is not a failure just
    because its accounting could not be read.
    """
    try:
        _send(proc, {"id": 9000, "type": "get_session_stats"})
        for event in _events(reader, event_timeout_s, proc):
            if event.get("type") != "response" or event.get("command") != "get_session_stats":
                continue
            data = event.get("data")
            if isinstance(data, dict):
                tokens = data.get("tokens")
                if isinstance(tokens, dict):
                    result.tokens = tokens
                cost = data.get("cost")
                if isinstance(cost, (int, float)):
                    result.cost_usd = float(cost)
            return
    except (TauSessionError, OSError, ValueError) as exc:
        print(f"[agent] could not read session stats: {exc}", file=sys.stderr)


def _prompt_command(request_id: int, message: str, behavior: str | None) -> dict[str, Any]:
    command: dict[str, Any] = {"id": request_id, "type": "prompt", "message": message}
    if behavior is not None:
        command["streamingBehavior"] = behavior
    return command


def _send(proc: subprocess.Popen[str], command: dict[str, Any]) -> None:
    if proc.stdin is None or proc.stdin.closed:
        raise TauSessionError("tau_stdin_closed")
    proc.stdin.write(json.dumps(command, ensure_ascii=False) + "\n")
    proc.stdin.flush()


def _consume_until_settled(
    *,
    reader: _EventReader,
    result: TauSessionResult,
    progress_callback: ProgressCallback | None,
    event_timeout_s: float,
    proc: subprocess.Popen[str],
) -> None:
    for event in _events(reader, event_timeout_s, proc):
        kind = event.get("type")

        if kind == "rpc_error":
            raise TauSessionError(f"tau_rpc_error: {event.get('error')}")

        if kind == "response" and event.get("success") is False:
            raise TauSessionError(
                f"tau_command_failed: {event.get('command')}: {event.get('error')}"
            )

        _record(event, kind, result, progress_callback)

        if kind == _SETTLED:
            return

    raise TauSessionError("tau_exited_before_settle")


def _events(
    reader: _EventReader,
    event_timeout_s: float,
    proc: subprocess.Popen[str],
) -> Iterator[dict[str, Any]]:
    """Yield decoded events until the child closes stdout."""
    while True:
        try:
            line = reader.next_line(event_timeout_s)
        except queue.Empty:
            _abort(proc)
            raise TauSessionError(
                f"tau_event_timeout: no event for {event_timeout_s:.0f}s"
            ) from None

        if line is None:
            return

        line = line.strip()
        if not line:
            continue

        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            print(f"[agent] tau emitted a non-JSON line: {line[:200]}", file=sys.stderr)
            continue

        if isinstance(decoded, dict):
            yield decoded


def _record(
    event: dict[str, Any],
    kind: str | None,
    result: TauSessionResult,
    progress_callback: ProgressCallback | None,
) -> None:
    """Fold one event into the session result and report it upstream."""
    if kind == "turn_end":
        result.turns += 1
    elif kind == "compaction_start":
        result.compactions += 1
    elif kind == "auto_retry_start":
        result.auto_retries += 1
    elif kind == "tool_execution_start":
        name = str(event.get("tool_name") or "")
        result.tool_calls[name] = result.tool_calls.get(name, 0) + 1
        _report(progress_callback, {"phase": "tool_start", "tool": name, "args": event.get("args")})
    elif kind == "tool_execution_end":
        name = str(event.get("tool_name") or "")
        if event.get("is_error"):
            result.tool_errors[name] = result.tool_errors.get(name, 0) + 1
        _absorb_tool_result(name, event.get("result"), result)
        _report(
            progress_callback,
            {"phase": "tool_end", "tool": name, "is_error": bool(event.get("is_error"))},
        )
    elif kind == "message_end":
        text = _message_text(event.get("message"))
        if text:
            result.summary = text
        _report(progress_callback, {"phase": "message", "text": text})


def _absorb_tool_result(name: str, payload: Any, result: TauSessionResult) -> None:
    """Keep the metrics the backtest tool reports, for `backtest_iterations.json`."""
    if name != "backtest" or not isinstance(payload, dict):
        return
    details = payload.get("details")
    if not isinstance(details, dict):
        return
    metrics = details.get("metrics")
    if isinstance(metrics, dict):
        result.backtest_metrics.append(metrics)


def _message_text(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = [
        str(block.get("text") or "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "".join(parts).strip()


def _report(progress_callback: ProgressCallback | None, payload: dict[str, Any]) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(payload)
    except Exception as exc:  # noqa: BLE001 - progress reporting must not fail the run
        print(f"[agent] progress callback failed: {exc}", file=sys.stderr)


def _abort(proc: subprocess.Popen[str]) -> None:
    try:
        _send(proc, {"type": "abort"})
    except (TauSessionError, OSError, ValueError):
        pass


def _shutdown(proc: subprocess.Popen[str]) -> None:
    """Close stdin so Tau exits on its own, then make sure it is gone."""
    try:
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
    except OSError:
        pass

    try:
        proc.wait(timeout=_SHUTDOWN_GRACE_S)
        return
    except subprocess.TimeoutExpired:
        pass

    proc.kill()
    try:
        proc.wait(timeout=_SHUTDOWN_GRACE_S)
    except subprocess.TimeoutExpired:
        print("[agent] tau did not exit after kill", file=sys.stderr)
