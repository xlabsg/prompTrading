"""Driver contract: what the driver does with the event stream Tau emits.

Every test drives a fake Tau -- a Python process that replays a recorded JSONL
script -- so the whole file runs without a model, a network, or the real
`tau` executable.

Scripts use Tau's own wire names (`toolName`, `isError`): `tau_agent.messages.
WireModel` serialises by camelCase alias, and a fixture in snake_case hid a
driver that read fields Tau never sends.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

from agent import tau_driver

# One settled turn with a single successful tool call.
SIMPLE_SCRIPT = [
    {"type": "response", "command": "prompt", "success": True, "id": 1},
    {"type": "agent_start"},
    {"type": "turn_start"},
    {"type": "tool_execution_start", "toolCallId": "c1", "toolName": "write", "args": {"path": "strategy.py"}},
    {"type": "tool_execution_end", "toolCallId": "c1", "toolName": "write", "result": {}, "isError": False},
    {"type": "turn_end"},
    {"type": "message_end", "message": {"content": [{"type": "text", "text": "Wrote the strategy."}]}},
    {"type": "agent_end", "messages": []},
    {"type": "agent_settled"},
]


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("AGENT_TAU_EVENT_TIMEOUT_S", "AGENT_TAU_MAX_FOLLOW_UPS", "AGENT_MAX_STEPS"):
        monkeypatch.delenv(name, raising=False)


def test_build_command_omits_extension_when_not_given():
    command = tau_driver.build_command(
        workspace="/w", provider="anthropic", model="claude-sonnet-4-6"
    )
    assert "-e" not in command
    assert command[-2:] == ["--model", "claude-sonnet-4-6"]


def test_build_command_always_passes_model_explicitly():
    """Without --model Tau silently uses the provider's own default."""
    command = tau_driver.build_command(
        workspace="/w", provider="deepseek", model="deepseek-chat", extension_path="/e.py"
    )
    assert "--model" in command
    assert command[command.index("--model") + 1] == "deepseek-chat"
    assert command[command.index("-e") + 1] == "/e.py"


def test_build_command_includes_thinking_and_session():
    command = tau_driver.build_command(
        workspace="/w",
        provider="anthropic",
        model="claude-sonnet-4-6",
        thinking_level="high",
        session_id="parent-session-123",
    )
    assert "--thinking" in command
    assert command[command.index("--thinking") + 1] == "high"
    assert "--session" in command
    assert command[command.index("--session") + 1] == "parent-session-123"


def test_session_id_and_trace_html_are_recorded(tmp_path, clean_env, monkeypatch):
    result = _run_with_fake(tmp_path, monkeypatch, SIMPLE_SCRIPT, validate=lambda: [])

    assert result.session_id == "test-session-xyz"
    assert result.trace_html_path is not None
    assert os.path.basename(result.trace_html_path) == "tau_trace.html"


def test_settles_and_records_the_turn(tmp_path, clean_env, monkeypatch):
    result = _run_with_fake(tmp_path, monkeypatch, SIMPLE_SCRIPT, validate=lambda: [])

    assert result.turns == 1
    assert result.follow_ups == 0
    assert result.summary == "Wrote the strategy."
    assert result.tool_calls == {"write": 1}
    assert result.tool_errors == {}


def test_agent_end_with_will_retry_is_not_the_end(tmp_path, clean_env, monkeypatch):
    """`agent_end` fires again on every auto-retry; only `agent_settled` ends a turn."""
    script = [
        {"type": "agent_start"},
        {"type": "agent_end", "messages": [], "will_retry": True},
        {"type": "auto_retry_start"},
        {"type": "auto_retry_end"},
        {"type": "turn_end"},
        {"type": "message_end", "message": {"content": [{"type": "text", "text": "second attempt"}]}},
        {"type": "agent_end", "messages": [], "will_retry": False},
        {"type": "agent_settled"},
    ]
    result = _run_with_fake(tmp_path, monkeypatch, script, validate=lambda: [])

    assert result.auto_retries == 1
    assert result.summary == "second attempt"


def test_incomplete_workspace_triggers_a_follow_up(tmp_path, clean_env, monkeypatch):
    calls = {"n": 0}

    def validate():
        calls["n"] += 1
        return ["- overview.md does not exist."] if calls["n"] == 1 else []

    result = _run_with_fake(tmp_path, monkeypatch, SIMPLE_SCRIPT, validate=validate)

    assert calls["n"] == 2
    assert result.follow_ups == 1
    assert result.turns == 2


def test_gives_up_after_the_follow_up_budget(tmp_path, clean_env, monkeypatch):
    monkeypatch.setenv("AGENT_TAU_MAX_FOLLOW_UPS", "1")

    with pytest.raises(tau_driver.TauSessionError, match="agent_incomplete_after_follow_ups"):
        _run_with_fake(
            tmp_path,
            monkeypatch,
            SIMPLE_SCRIPT,
            validate=lambda: ["- strategy.py does not exist."],
        )


def test_rpc_error_fails_the_session(tmp_path, clean_env, monkeypatch):
    script = [{"type": "rpc_error", "error": "provider exploded"}]

    with pytest.raises(tau_driver.TauSessionError, match="provider exploded"):
        _run_with_fake(tmp_path, monkeypatch, script, validate=lambda: [])


def test_failed_command_response_fails_the_session(tmp_path, clean_env, monkeypatch):
    script = [
        {"type": "response", "command": "prompt", "success": False, "error": "bad model"}
    ]

    with pytest.raises(tau_driver.TauSessionError, match="tau_command_failed"):
        _run_with_fake(tmp_path, monkeypatch, script, validate=lambda: [])


def test_exit_before_settle_fails_the_session(tmp_path, clean_env, monkeypatch):
    """A child that dies mid-turn must not look like a completed session."""
    script = [{"type": "agent_start"}, {"type": "turn_start"}]

    with pytest.raises(tau_driver.TauSessionError, match="tau_exited_before_settle"):
        _run_with_fake(tmp_path, monkeypatch, script, validate=lambda: [])


def test_silence_times_out_and_kills_the_child(tmp_path, clean_env, monkeypatch):
    monkeypatch.setenv("AGENT_TAU_EVENT_TIMEOUT_S", "0.5")
    script: list[dict] = []  # accepts the prompt, then says nothing forever

    with pytest.raises(tau_driver.TauSessionError, match="tau_event_timeout"):
        _run_with_fake(tmp_path, monkeypatch, script, validate=lambda: [], hang=True)


def test_session_cost_is_recorded(tmp_path, clean_env, monkeypatch):
    """Token usage and cost come from Tau, for the run's llm_meta."""
    result = _run_with_fake(tmp_path, monkeypatch, SIMPLE_SCRIPT, validate=lambda: [])

    assert result.tokens == {"input": 100, "output": 20, "total": 120}
    assert result.cost_usd == 0.0031


def test_backtest_metrics_are_collected(tmp_path, clean_env, monkeypatch):
    script = [
        {"type": "turn_start"},
        {
            "type": "tool_execution_end",
            "toolCallId": "c1",
            "toolName": "backtest",
            "result": {"details": {"metrics": {"sharpe_ratio": 1.4}}},
            "isError": False,
        },
        {"type": "turn_end"},
        {"type": "agent_settled"},
    ]
    result = _run_with_fake(tmp_path, monkeypatch, script, validate=lambda: [])

    assert result.backtest_metrics == [{"sharpe_ratio": 1.4}]


def test_tool_errors_are_counted(tmp_path, clean_env, monkeypatch):
    script = [
        {"type": "tool_execution_start", "toolCallId": "c1", "toolName": "edit", "args": {}},
        {"type": "tool_execution_end", "toolCallId": "c1", "toolName": "edit", "result": {}, "isError": True},
        {"type": "agent_settled"},
    ]
    result = _run_with_fake(tmp_path, monkeypatch, script, validate=lambda: [])

    assert result.tool_calls == {"edit": 1}
    assert result.tool_errors == {"edit": 1}


def test_snake_case_tool_events_are_still_read(tmp_path, clean_env, monkeypatch):
    """The fallback in `_wire`, so a change of wire casing is not silent again."""
    script = [
        {"type": "tool_execution_start", "tool_call_id": "c1", "tool_name": "edit", "args": {}},
        {"type": "tool_execution_end", "tool_call_id": "c1", "tool_name": "edit", "result": {}, "is_error": True},
        {"type": "agent_settled"},
    ]
    result = _run_with_fake(tmp_path, monkeypatch, script, validate=lambda: [])

    assert result.tool_calls == {"edit": 1}
    assert result.tool_errors == {"edit": 1}


def test_progress_callback_failure_does_not_fail_the_run(tmp_path, clean_env, monkeypatch):
    def explode(_payload):
        raise RuntimeError("redis is down")

    result = _run_with_fake(
        tmp_path, monkeypatch, SIMPLE_SCRIPT, validate=lambda: [], progress=explode
    )
    assert result.turns == 1


def test_non_json_output_is_skipped(tmp_path, clean_env, monkeypatch):
    """Tau may print a warning line; it must not derail event parsing."""
    result = _run_with_fake(
        tmp_path,
        monkeypatch,
        SIMPLE_SCRIPT,
        validate=lambda: [],
        preamble="warning: something happened",
    )
    assert result.turns == 1


# Three turns in one prompt, so a cap of 2 is reached before the script settles.
THREE_TURN_SCRIPT = [
    {"type": "agent_start"},
    {"type": "turn_end"},
    {"type": "turn_end"},
    {"type": "turn_end"},
    {"type": "message_end", "message": {"content": [{"type": "text", "text": "still going"}]}},
    {"type": "agent_settled"},
]


def test_turn_budget_is_unbounded_by_default(tmp_path, clean_env, monkeypatch):
    result = _run_with_fake(tmp_path, monkeypatch, THREE_TURN_SCRIPT, validate=lambda: [])

    assert result.turns == 3
    assert result.turn_limit_hit is False


def test_turn_budget_stops_the_session(tmp_path, clean_env, monkeypatch):
    """A capped session gives up rather than running until the container is killed."""
    monkeypatch.setenv("AGENT_MAX_STEPS", "2")

    with pytest.raises(tau_driver.TauSessionError, match="agent_turn_limit_reached"):
        _run_with_fake(
            tmp_path, monkeypatch, THREE_TURN_SCRIPT, validate=lambda: ["- strategy.py missing"]
        )


def test_turn_budget_keeps_a_complete_workspace(tmp_path, clean_env, monkeypatch):
    """Hitting the cap is not a failure when the work is already done."""
    monkeypatch.setenv("AGENT_MAX_STEPS", "2")

    result = _run_with_fake(tmp_path, monkeypatch, THREE_TURN_SCRIPT, validate=lambda: [])

    assert result.turn_limit_hit is True
    assert result.follow_ups == 0


def test_turn_budget_suppresses_follow_ups(tmp_path, clean_env, monkeypatch):
    """Without the cap the same script would spend its follow-up budget."""
    monkeypatch.setenv("AGENT_MAX_STEPS", "2")
    monkeypatch.setenv("AGENT_TAU_MAX_FOLLOW_UPS", "2")

    with pytest.raises(tau_driver.TauSessionError) as excinfo:
        _run_with_fake(
            tmp_path, monkeypatch, THREE_TURN_SCRIPT, validate=lambda: ["- strategy.py missing"]
        )

    assert "agent_incomplete_after_follow_ups" not in str(excinfo.value)


# --- fake Tau plumbing -------------------------------------------------------

# Stands in for `tau --mode rpc`: replays a JSONL script for each prompt it is
# given. Kept unindented at module level so the generated file needs no dedent.
_FAKE_TAU_SOURCE = """\
import json, sys, time, os

script = json.loads(sys.argv[1])
hang = sys.argv[2] == "1"
preamble = sys.argv[3]

STATS = {
    "type": "response",
    "command": "get_session_stats",
    "success": True,
    "data": {"tokens": {"input": 100, "output": 20, "total": 120}, "cost": 0.0031},
}

STATE = {
    "type": "response",
    "command": "get_state",
    "success": True,
    "data": {"sessionId": "test-session-xyz"},
}


def emit(payload):
    sys.stdout.write(json.dumps(payload) + "\\n")
    sys.stdout.flush()


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    command = json.loads(line)
    if command.get("type") == "get_session_stats":
        emit(STATS)
        continue
    if command.get("type") == "get_state":
        emit(STATE)
        continue
    if command.get("type") == "export_html":
        out = command.get("outputPath") or "tau_trace.html"
        with open(out, "w") as f:
            f.write("<html><body>Trace</body></html>")
        emit({"type": "response", "command": "export_html", "success": True, "data": {"path": out}})
        continue
    if command.get("type") != "prompt":
        continue
    if preamble:
        sys.stdout.write(preamble + "\\n")
        sys.stdout.flush()
    for event in script:
        emit(event)
    if hang:
        time.sleep(30)
    # A script that never settles stands for a child that died mid-turn: close
    # stdout so the driver sees the stream end instead of waiting out its
    # event timeout.
    if not any(e.get("type") == "agent_settled" for e in script):
        break
"""



def _run_with_fake(
    tmp_path,
    monkeypatch,
    script,
    *,
    validate,
    progress=None,
    hang=False,
    preamble=None,
):
    """Run the driver against a fake Tau that replays `script` for each prompt."""
    fake = tmp_path / "fake_tau.py"
    fake.write_text(_FAKE_TAU_SOURCE)

    # The driver builds `[executable, --mode, rpc, ...]`; a wrapper script lets a
    # plain interpreter stand in for the `tau` binary and ignore those flags.
    wrapper = tmp_path / "tau_wrapper.sh"
    wrapper.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{fake}" '
        f"'{json.dumps(script)}' '{'1' if hang else '0'}' '{preamble or ''}'\n"
    )
    wrapper.chmod(0o755)

    return tau_driver.run_session(
        task="build a strategy",
        workspace=str(tmp_path),
        provider="openai",
        model="gpt-4o-mini",
        validate=validate,
        tau_executable=str(wrapper),
        progress_callback=progress,
    )
