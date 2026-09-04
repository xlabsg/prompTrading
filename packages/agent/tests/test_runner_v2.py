"""Runner contract: the agent drives the workspace, the runner publishes artifacts."""

from __future__ import annotations

import json
import os

import pytest

from agent import runner_v2
from agent import tau_driver

STRATEGY_SRC = (
    "def generate_signals(data, params):\n"
    "    return {'target_weights': [0.0] * len(data), 'weight_reason': ['hold'] * len(data)}\n"
)
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
    """Stands in for a Tau session, writing the deliverables it is asked for."""

    instances: list["FakeAgent"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.task = kwargs.get("task")
        FakeAgent.instances.append(self)

    @classmethod
    def as_run_session(cls, **kwargs):
        instance = cls(**kwargs)
        return instance.run()

    def run(self):
        root = self.kwargs["workspace"]
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "strategy.py"), "w") as f:
            f.write(STRATEGY_SRC)
        with open(os.path.join(root, "overview.md"), "w") as f:
            f.write(OVERVIEW_SRC)
        return tau_driver.TauSessionResult(
            summary="did the thing",
            turns=3,
            tool_calls={"write": 2},
            tokens={"total": 1234},
        )


@pytest.fixture(autouse=True)
def _reset_fake():
    FakeAgent.instances = []


def test_agent_runs_in_version_dir_not_strategy_dir(workspace, monkeypatch):
    """Version isolation: a run must not edit the live strategy in place."""
    monkeypatch.setattr(runner_v2.tau_driver, "run_session", FakeAgent.as_run_session)
    assert runner_v2.main() == 0

    agent = FakeAgent.instances[0]
    assert agent.kwargs["workspace"] == str(workspace["version_dir"])


def test_artifacts_written_to_version_and_published_to_strategy(workspace, monkeypatch):
    monkeypatch.setattr(runner_v2.tau_driver, "run_session", FakeAgent.as_run_session)
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
    monkeypatch.setattr(runner_v2.tau_driver, "run_session", FakeAgent.as_run_session)

    assert runner_v2.main() == 0
    task = FakeAgent.instances[0].task
    assert "Modify the existing trading strategy" in task
    assert "strategy.py" in task


def test_first_generation_uses_create_intent(workspace, monkeypatch):
    monkeypatch.setattr(runner_v2.tau_driver, "run_session", FakeAgent.as_run_session)
    assert runner_v2.main() == 0
    assert "Create a new trading strategy" in FakeAgent.instances[0].task


def test_task_states_the_backtest_budget(workspace, monkeypatch):
    monkeypatch.setenv("AGENT_BACKTEST_MAX_RUNS", "3")
    monkeypatch.setattr(runner_v2.tau_driver, "run_session", FakeAgent.as_run_session)
    assert runner_v2.main() == 0

    task = FakeAgent.instances[0].task
    assert "at most 3 backtest runs" in task
    assert "`backtest`" in task


def test_llm_meta_records_agent_and_iterations(workspace, monkeypatch):
    monkeypatch.setattr(runner_v2.tau_driver, "run_session", FakeAgent.as_run_session)
    assert runner_v2.main() == 0

    meta = json.loads((workspace["version_dir"] / "llm_meta.json").read_text())
    assert meta["pipeline"] == "tau"
    assert meta["agent_summary"] == "did the thing"
    assert meta["stop_reason"] == "task_done"
    assert meta["overview_status"] == "agent_generated"
    assert "backtest_iterations" in meta


def test_session_error_propagates_without_fallback(workspace, monkeypatch):
    """A session the driver could not complete must not publish anything."""

    def failing(**kwargs):
        raise tau_driver.TauSessionError(
            "agent_incomplete_after_follow_ups: - strategy.py does not exist."
        )

    monkeypatch.setattr(runner_v2.tau_driver, "run_session", failing)
    monkeypatch.delenv("LLM_FALLBACK_ON_ERROR", raising=False)
    with pytest.raises(tau_driver.TauSessionError, match="agent_incomplete"):
        runner_v2.main()


def test_session_error_fallback_fails_the_job_without_publishing(workspace, monkeypatch):
    """The error fallback is a generic MA crossover, not the requested strategy.

    It stays in the version dir for inspection, but publishing it would silently
    replace a working live strategy with a stub, so the run must still fail.
    """

    def failing(**kwargs):
        raise tau_driver.TauSessionError("agent_incomplete_after_follow_ups")

    monkeypatch.setattr(runner_v2.tau_driver, "run_session", failing)
    monkeypatch.setenv("LLM_FALLBACK_ON_ERROR", "1")

    strategy_dir = workspace["strategy_dir"]
    before = (strategy_dir / "strategy.py").read_text() if (strategy_dir / "strategy.py").is_file() else None

    with pytest.raises(RuntimeError, match="agent_error_fallback"):
        runner_v2.main()

    meta = json.loads((workspace["version_dir"] / "llm_meta.json").read_text())
    assert meta["used_llm"] is False
    assert meta["stop_reason"] == "error_fallback"
    assert meta["degraded"] is True
    assert meta["agent_error"]
    assert (workspace["version_dir"] / "strategy.py").is_file()

    after = (strategy_dir / "strategy.py").read_text() if (strategy_dir / "strategy.py").is_file() else None
    assert after == before, "the live strategy dir must be untouched by an error fallback"


def test_unreachable_provider_is_not_a_successful_refine(workspace, monkeypatch):
    """Tau settles even when every model call failed, echoing the task back.

    Refine seeds the workspace from the live strategy, so it already validates;
    without the no-progress gate this published an unchanged strategy, reported
    success, and showed the task prompt to the user as the agent's answer.
    """
    strategy_dir = workspace["strategy_dir"]
    (strategy_dir / "strategy.py").write_text(STRATEGY_SRC)
    (strategy_dir / "overview.md").write_text(OVERVIEW_SRC)
    monkeypatch.setenv("JOB_TYPE", "refine_strategy")
    monkeypatch.delenv("LLM_FALLBACK_ON_ERROR", raising=False)

    def settled_without_reaching_the_model(**kwargs):
        # No tokens, no tool calls, and the task echoed back as the summary.
        return tau_driver.TauSessionResult(summary=kwargs["task"], turns=1)

    monkeypatch.setattr(runner_v2.tau_driver, "run_session", settled_without_reaching_the_model)

    with pytest.raises(tau_driver.TauSessionError, match="agent_made_no_model_progress"):
        runner_v2.main()


def test_fallback_path_still_supplies_an_overview(workspace, monkeypatch):
    """The template fallback writes no overview, so the runner must add one."""

    monkeypatch.setenv("FORCE_FALLBACK", "1")

    assert runner_v2.main() == 0
    meta = json.loads((workspace["version_dir"] / "llm_meta.json").read_text())
    assert meta["stop_reason"] == "forced_fallback"
    assert meta["overview_status"] == "fallback_missing"
    assert "```mermaid" in (workspace["version_dir"] / "overview.md").read_text()


def test_invalid_generated_code_is_rejected(workspace, monkeypatch):
    """The runner re-validates even code a session claimed was finished."""

    class BadCode(FakeAgent):
        def run(self):
            root = self.kwargs["workspace"]
            os.makedirs(root, exist_ok=True)
            with open(os.path.join(root, "strategy.py"), "w") as f:
                f.write("x = 1\n")  # no generate_signals
            with open(os.path.join(root, "overview.md"), "w") as f:
                f.write(OVERVIEW_SRC)
            return tau_driver.TauSessionResult(
                summary="bad", turns=1, tool_calls={"write": 1}, tokens={"total": 99}
            )

    monkeypatch.setattr(runner_v2.tau_driver, "run_session", BadCode.as_run_session)
    monkeypatch.delenv("LLM_FALLBACK_ON_ERROR", raising=False)
    with pytest.raises(ValueError, match="generate_signals"):
        runner_v2.main()


def test_session_stats_land_in_llm_meta(workspace, monkeypatch):
    monkeypatch.setattr(runner_v2.tau_driver, "run_session", FakeAgent.as_run_session)
    assert runner_v2.main() == 0

    meta = json.loads((workspace["version_dir"] / "llm_meta.json").read_text())
    assert meta["pipeline"] == "tau"
    assert meta["tau_session"]["turns"] == 3


def test_seed_workspace_does_not_overwrite_agent_output(tmp_path):
    version_dir = tmp_path / "v"
    strategy_dir = tmp_path / "s"
    version_dir.mkdir()
    strategy_dir.mkdir()
    (strategy_dir / "strategy.py").write_text("old\n")
    (version_dir / "strategy.py").write_text("new\n")

    runner_v2._seed_workspace(str(version_dir), str(strategy_dir))
    assert (version_dir / "strategy.py").read_text() == "new\n"


def test_workspace_problems_names_missing_strategy(tmp_path):
    problems = runner_v2._workspace_problems(str(tmp_path))
    assert any("strategy.py" in p for p in problems)

    (tmp_path / "strategy.py").write_text(STRATEGY_SRC)
    (tmp_path / "overview.md").write_text(OVERVIEW_SRC)
    assert runner_v2._workspace_problems(str(tmp_path)) == []


def test_workspace_problems_overview_is_non_blocking(tmp_path):
    (tmp_path / "strategy.py").write_text(STRATEGY_SRC)
    # overview.md is non-blocking because runner_v2 auto-generates it if absent
    assert runner_v2._workspace_problems(str(tmp_path)) == []
