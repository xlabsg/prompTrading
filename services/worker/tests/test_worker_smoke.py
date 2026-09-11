from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import MagicMock

# Ensure local test run does not try to write to /var/log/app
if "LOG_DIR" not in os.environ:
    os.environ["LOG_DIR"] = tempfile.gettempdir()

# Provide mocks for worker-specific system dependencies if running outside worker container
for mod_name in [
    "docker",
    "docker.types",
    "apscheduler",
    "apscheduler.schedulers",
    "apscheduler.schedulers.background",
    "apscheduler.triggers",
    "apscheduler.triggers.cron",
]:
    if mod_name not in sys.modules:
        try:
            __import__(mod_name)
        except ImportError:
            mock_mod = MagicMock()
            sys.modules[mod_name] = mock_mod

from control_plane.enums import JobType


def test_worker_main_imports_and_handlers_complete():
    """Verify worker.main imports cleanly and JOB_HANDLERS covers all defined JobTypes."""
    from worker.main import JOB_HANDLERS

    registered_keys = set(JOB_HANDLERS.keys())
    expected_keys = {jt.value for jt in JobType}

    assert registered_keys == expected_keys, (
        f"Mismatch in JOB_HANDLERS: missing {expected_keys - registered_keys}, extra {registered_keys - expected_keys}"
    )

    for job_type, handler in JOB_HANDLERS.items():
        assert callable(handler), f"Handler for {job_type} is not callable: {handler}"


def test_template_backtest_uses_the_shared_template_source():
    """The worker must not reintroduce its own TEMPLATE_STRATEGIES copy."""
    from control_plane.templates import TEMPLATE_STRATEGIES
    from worker.template_backtest_job import TEMPLATE_STRATEGIES as worker_templates

    assert worker_templates is TEMPLATE_STRATEGIES


def test_generate_and_backtest_reuses_agent_metrics(tmp_path, monkeypatch):
    """If metrics.json already exists in run_dir, reuse it and skip _handle_backtest."""
    import json
    from unittest.mock import patch
    from control_plane.enums import BacktestStatus, JobStatus, JobType
    from control_plane.models import BacktestRun, Dataset, Job, Strategy
    from worker.main import _handle_generate_and_backtest

    monkeypatch.setattr("worker.main.settings.app_workspaces_dir", str(tmp_path))
    monkeypatch.setattr("worker.main.settings.worker_workspaces_volume", "vol")

    # Mock docker container execution so agent container succeeds immediately
    monkeypatch.setattr(
        "worker.main._run_container_and_stream_logs",
        lambda *args, **kwargs: (0, ["agent finished"]),
    )
    # Mock strategy naming
    monkeypatch.setattr("worker.main._generate_strategy_name", lambda *args, **kwargs: "Test Strat")
    # Mock git commit
    monkeypatch.setattr("worker.main.git_commit", lambda *args, **kwargs: None)
    monkeypatch.setattr("worker.main._ensure_strategy_repo", lambda *args, **kwargs: None)

    # Set up DB mocks
    db = MagicMock()
    rds = MagicMock()
    docker_client = MagicMock()

    strategy_id = "strat_1"
    version_id = "ver_1"
    run_id = "run_1"
    dataset_id = "ds_1"

    job = Job(
        id="job_1",
        type=JobType.GENERATE_AND_BACKTEST,
        status=JobStatus.RUNNING,
        payload={
            "strategy_id": strategy_id,
            "version_id": version_id,
            "run_id": run_id,
            "dataset_id": dataset_id,
            "prompt": "test prompt",
        },
    )

    run = BacktestRun(
        id=run_id,
        strategy_id=strategy_id,
        strategy_version_id=version_id,
        dataset_id=dataset_id,
        status=BacktestStatus.RUNNING,
        params={},
    )
    ds = Dataset(
        id=dataset_id,
        exchange="okx",
        symbol="BTC-USDT",
        interval="1h",
    )
    strategy = Strategy(
        id=strategy_id,
        name="Old Name",
    )

    def mock_get(model, entity_id):
        if model is BacktestRun and entity_id == run_id:
            return run
        if model is Dataset and entity_id == dataset_id:
            return ds
        if model is Strategy and entity_id == strategy_id:
            return strategy
        return None

    db.get.side_effect = mock_get

    # Pre-populate run_dir with metrics.json (simulating agent backtest tool output)
    run_dir = tmp_path / strategy_id / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    metrics_data = {
        "sharpe_ratio": 1.85,
        "total_return": 25.5,
        "max_drawdown": 8.2,
        "total_trades": 15,
        "win_rate": 60.0,
        "profit_factor": 1.9,
        "num_bars": 1000,
        "final_equity": 12550.0,
        "initial_cash": 10000.0,
    }
    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_data, f)

    with patch("worker.main._handle_backtest") as mock_handle_backtest:
        _handle_generate_and_backtest(db, rds, docker_client, job)
        # _handle_backtest should NOT be called since metrics.json was reused
        mock_handle_backtest.assert_not_called()

    assert run.status == BacktestStatus.SUCCEEDED
    assert run.metrics == metrics_data
    assert run.result_summary["sharpe_ratio"] == 1.85
    assert run.result_summary["symbol"] == "BTC-USDT"

