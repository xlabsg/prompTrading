"""Runner contract: the agent drives the workspace, the runner publishes artifacts."""

from __future__ import annotations

import json
import os

import pytest

from agent import runner_v2
from agent.config import StopReason

STRATEGY_SRC = "def generate_signals(data, params):\n    return {'target_weights': []}\n"
OVERVIEW_SRC = "# Summary\n\nDoes things.\n\n# Flow Animation\n\n```mermaid\ngraph TD;A-->B;\n```\n"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_ID", "strat1")
    monkeypatch.setenv("VERSION_ID", "ver1")
    monkeypatch.setenv("WORKSPACES_DIR", str(tmp_path))
    monkeypatch.setenv("PROMPT", "Build a momentum strategy")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    # Never shell out to git or flush telemetry from a test.
    monkeypatch.setattr(runner_v2, "_git_commit", lambda *a, **k: None)
    monkeypatch.setattr(runner_v2, "get_langfuse", lambda: type("L", (), {"flush": lambda self: None})())

    version_dir = tmp_path / "strat1" / "versions" / "ver1"
    strategy_dir = tmp_path / "strat1" / "strategy"
    strategy_dir.mkdir(parents=True, exist_ok=True)
    return {"root": tmp_path, "version_dir": version_dir, "strategy_dir": strategy_dir}


class FakeAgent:
    """Stands in for AutonomousAgent, writing the deliverables it is asked for."""

    instances: list["FakeAgent"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.task = None
        FakeAgent.instances.append(self)

    def run(self, task):
        self.task = task
        root = self.kwargs["workspace_root"]
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "strategy.py"), "w") as f:
            f.write(STRATEGY_SRC)
        with open(os.path.join(root, "overview.md"), "w") as f:
            f.write(OVERVIEW_SRC)
        return type(
            "R",
            (),
            {
                "success": True,
                "summary": "did the thing",
                "stop_reason": StopReason.TASK_DONE,
                "history": [],
                "steps_taken": 3,
            },
        )()


@pytest.fixture(autouse=True)
def _reset_fake():
    FakeAgent.instances = []


def test_agent_runs_in_version_dir_not_strategy_dir(workspace, monkeypatch):
    """Version isolation: a run must not edit the live strategy in place."""
    monkeypatch.setattr(runner_v2, "AutonomousAgent", FakeAgent)
    assert runner_v2.main() == 0

    agent = FakeAgent.instances[0]
    assert agent.kwargs["workspace_root"] == str(workspace["version_dir"])


def test_artifacts_written_to_version_and_published_to_strategy(workspace, monkeypatch):
    monkeypatch.setattr(runner_v2, "AutonomousAgent", FakeAgent)
    assert runner_v2.main() == 0

    for name in (
        "strategy.py",
        "strategy_spec.yaml",
        "strategy_protocol.json",
        "params_schema.json",
        "strategy_meta.json",
        "overview.md",
        "llm_meta.json",
        "backtest_iterations.json",
    ):
        assert (workspace["version_dir"] / name).is_file(), f"missing in version dir: {name}"

    for name in ("strategy.py", "strategy_spec.yaml", "overview.md", "params_schema.json"):
        assert (workspace["strategy_dir"] / name).is_file(), f"not published: {name}"

    assert (workspace["strategy_dir"] / "strategy.py").read_text() == STRATEGY_SRC


def test_existing_strategy_is_seeded_into_version_workspace(workspace, monkeypatch):
    (workspace["strategy_dir"] / "strategy.py").write_text("# existing code\n")
    (workspace["strategy_dir"] / "overview.md").write_text("# Summary\n\nold\n")
    monkeypatch.setattr(runner_v2, "AutonomousAgent", FakeAgent)

    assert runner_v2.main() == 0
    task = FakeAgent.instances[0].task
    assert "Modify the existing trading strategy" in task
    assert "strategy.py" in task


def test_first_generation_uses_create_intent(workspace, monkeypatch):
    monkeypatch.setattr(runner_v2, "AutonomousAgent", FakeAgent)
    assert runner_v2.main() == 0
    assert "Create a new trading strategy" in FakeAgent.instances[0].task


def test_task_states_the_backtest_budget(workspace, monkeypatch):
    monkeypatch.setenv("AGENT_BACKTEST_MAX_RUNS", "3")
    monkeypatch.setattr(runner_v2, "AutonomousAgent", FakeAgent)
    assert runner_v2.main() == 0

    task = FakeAgent.instances[0].task
    assert "at most 3 backtest runs" in task
    assert "skill_backtest" in task
    assert FakeAgent.instances[0].kwargs["backtest_budget"].max_runs == 3


def test_llm_meta_records_agent_and_iterations(workspace, monkeypatch):
    monkeypatch.setattr(runner_v2, "AutonomousAgent", FakeAgent)
    assert runner_v2.main() == 0

    meta = json.loads((workspace["version_dir"] / "llm_meta.json").read_text())
    assert meta["pipeline"] == "autonomous_agent"
    assert meta["agent_summary"] == "did the thing"
    assert meta["stop_reason"] == "task_done"
    assert meta["overview_status"] == "agent_generated"
    assert "backtest_iterations" in meta


def test_agent_failure_propagates_without_fallback(workspace, monkeypatch):
    class Failing(FakeAgent):
        def run(self, task):
            return type(
                "R",
                (),
                {
                    "success": False,
                    "summary": "gave up",
                    "stop_reason": StopReason.MAX_STEPS,
                    "history": [],
                    "steps_taken": 50,
                },
            )()

    monkeypatch.setattr(runner_v2, "AutonomousAgent", Failing)
    monkeypatch.delenv("LLM_FALLBACK_ON_ERROR", raising=False)
    with pytest.raises(RuntimeError, match="agent_failed"):
        runner_v2.main()


def test_agent_failure_uses_fallback_when_enabled(workspace, monkeypatch):
    class Failing(FakeAgent):
        def run(self, task):
            return type(
                "R",
                (),
                {
                    "success": False,
                    "summary": "gave up",
                    "stop_reason": StopReason.MAX_STEPS,
                    "history": [],
                    "steps_taken": 50,
                },
            )()

    monkeypatch.setattr(runner_v2, "AutonomousAgent", Failing)
    monkeypatch.setenv("LLM_FALLBACK_ON_ERROR", "1")

    assert runner_v2.main() == 0
    meta = json.loads((workspace["version_dir"] / "llm_meta.json").read_text())
    assert meta["used_llm"] is False
    assert meta["stop_reason"] == "fallback"
    assert (workspace["version_dir"] / "strategy.py").is_file()


def test_missing_overview_falls_back(workspace, monkeypatch):
    class NoOverview(FakeAgent):
        def run(self, task):
            root = self.kwargs["workspace_root"]
            os.makedirs(root, exist_ok=True)
            with open(os.path.join(root, "strategy.py"), "w") as f:
                f.write(STRATEGY_SRC)
            return type(
                "R",
                (),
                {
                    "success": True,
                    "summary": "no overview",
                    "stop_reason": StopReason.TASK_DONE,
                    "history": [],
                    "steps_taken": 1,
                },
            )()

    monkeypatch.setattr(runner_v2, "AutonomousAgent", NoOverview)
    assert runner_v2.main() == 0
    meta = json.loads((workspace["version_dir"] / "llm_meta.json").read_text())
    assert meta["overview_status"] == "fallback_missing"
    assert (workspace["version_dir"] / "overview.md").is_file()


def test_invalid_generated_code_is_rejected(workspace, monkeypatch):
    class BadCode(FakeAgent):
        def run(self, task):
            root = self.kwargs["workspace_root"]
            os.makedirs(root, exist_ok=True)
            with open(os.path.join(root, "strategy.py"), "w") as f:
                f.write("x = 1\n")  # no generate_signals
            with open(os.path.join(root, "overview.md"), "w") as f:
                f.write(OVERVIEW_SRC)
            return type(
                "R",
                (),
                {
                    "success": True,
                    "summary": "bad",
                    "stop_reason": StopReason.TASK_DONE,
                    "history": [],
                    "steps_taken": 1,
                },
            )()

    monkeypatch.setattr(runner_v2, "AutonomousAgent", BadCode)
    monkeypatch.delenv("LLM_FALLBACK_ON_ERROR", raising=False)
    with pytest.raises(ValueError, match="generate_signals"):
        runner_v2.main()


def test_seed_workspace_does_not_overwrite_agent_output(tmp_path):
    version_dir = tmp_path / "v"
    strategy_dir = tmp_path / "s"
    version_dir.mkdir()
    strategy_dir.mkdir()
    (strategy_dir / "strategy.py").write_text("old\n")
    (version_dir / "strategy.py").write_text("new\n")

    runner_v2._seed_workspace(str(version_dir), str(strategy_dir))
    assert (version_dir / "strategy.py").read_text() == "new\n"


def test_agent_config_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_STEPS", "12")
    monkeypatch.setenv("AGENT_MAX_TOKENS", "5000")
    cfg = runner_v2._agent_config()
    assert cfg.max_steps == 12
    assert cfg.max_tokens == 5000


def test_agent_config_ignores_garbage(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_STEPS", "not-a-number")
    assert runner_v2._agent_config().max_steps == 50
