from __future__ import annotations

import json
import os
import tempfile
import pytest

from app.routers.strategies import (
    _agent_progress_event,
    _build_strategy_agent_task,
    _format_agent_backtest_comparison,
    _snapshot_workspace_fingerprint,
)


def test_build_strategy_agent_task_contains_instructions_and_safety():
    task = _build_strategy_agent_task(
        "这个策略的 RSI 参数是多少？",
        history_context="[user] 你好\n[assistant] 你好！",
        backtest_context="Status: completed, Total trades: 15",
    )
    assert "User message:\n这个策略的 RSI 参数是多少？" in task
    assert "Recent context:" in task
    assert "Latest backtest context:" in task
    assert "Do NOT modify any files" in task
    assert "Safety constraints:" in task
    assert "generate_signals(data, params)" in task


def test_build_strategy_agent_task_minimal():
    task = _build_strategy_agent_task("将周期改为 4h")
    assert "User message:\n将周期改为 4h" in task
    assert "Recent context:" not in task
    assert "Latest backtest context:" not in task
    assert "modify strategy.py accordingly" in task


def test_snapshot_workspace_fingerprint_detects_changes():
    with tempfile.TemporaryDirectory() as tmpdir:
        strat_py = os.path.join(tmpdir, "strategy.py")
        with open(strat_py, "w", encoding="utf-8") as f:
            f.write("# initial code")

        fp1 = _snapshot_workspace_fingerprint(tmpdir)
        assert "strategy.py" in fp1

        # No changes
        fp2 = _snapshot_workspace_fingerprint(tmpdir)
        assert fp1 == fp2

        # Modify file
        with open(strat_py, "w", encoding="utf-8") as f:
            f.write("# modified code")

        fp3 = _snapshot_workspace_fingerprint(tmpdir)
        assert fp1 != fp3

        # Add file
        overview = os.path.join(tmpdir, "overview.md")
        with open(overview, "w", encoding="utf-8") as f:
            f.write("# Overview")

        fp4 = _snapshot_workspace_fingerprint(tmpdir)
        assert fp3 != fp4
        assert "overview.md" in fp4

        # The agent republishes its session trace on every run, including runs
        # that only answered a question, so it must not read as a change.
        with open(os.path.join(tmpdir, "tau_trace.html"), "w", encoding="utf-8") as f:
            f.write("<html>session 1</html>")
        fp5 = _snapshot_workspace_fingerprint(tmpdir)
        assert fp5 == fp4
        with open(os.path.join(tmpdir, "tau_trace.html"), "w", encoding="utf-8") as f:
            f.write("<html>session 2 - different</html>")
        assert _snapshot_workspace_fingerprint(tmpdir) == fp4


def test_agent_progress_event_parses_tool_log_lines():
    event = _agent_progress_event("[agent] tool edit path=strategy.py ...")
    assert event == {
        "type": "progress",
        "tool": "edit",
        "path": "strategy.py",
        "message": "正在修改 strategy.py...",
        "phase": "tool_start",
    }

    read_event = _agent_progress_event("[agent] tool read path=overview.md ...")
    assert read_event is not None
    assert read_event["message"] == "正在阅读 overview.md..."

    # Lines without a path, other tools, and ordinary output carry no progress.
    assert _agent_progress_event("[agent] tool bash ...") is None
    assert _agent_progress_event("[agent] tool edit ok") is None
    assert _agent_progress_event("[agent] seeded workspace with: strategy.py") is None


def test_format_agent_backtest_comparison_uses_first_and_last_run():
    block = _format_agent_backtest_comparison(
        {
            "backtest_iterations": {
                "dataset": {"exchange": "okx", "symbol": "BTC-USDT-SWAP", "interval": "1h"},
                "history": [
                    {"sharpe_ratio": 0.4, "total_return": 3.0},
                    {"sharpe_ratio": 0.9, "total_return": 8.0},
                    {"sharpe_ratio": 1.1, "total_return": 12.0},
                ],
            }
        }
    )
    assert "```action:metrics_comparison" in block
    payload = json.loads(block.split("```action:metrics_comparison\n")[1].split("\n```")[0])
    assert payload["benchmark"]["symbol"] == "BTC-USDT-SWAP"
    assert payload["before"]["sharpe_ratio"] == 0.4
    assert payload["after"]["sharpe_ratio"] == 1.1

    # No agent backtests means no card rather than an empty one.
    assert _format_agent_backtest_comparison({}) == ""
    assert _format_agent_backtest_comparison({"backtest_iterations": {"history": []}}) == ""


def _install_fake_worker(monkeypatch, strategies, session_factory, *, summary, modify_path=None):
    """Stand in for the worker running the agent container.

    Marks the queued job succeeded, writes the `llm_meta.json` that
    `agent.runner_v2` would have left in the version dir, and optionally
    publishes a change to the live strategy dir.
    """
    from control_plane.models import Job

    def fake_terminal_state(_session_factory, job_id):
        with session_factory() as session:
            job = session.get(Job, job_id)
            version_id = job.payload["version_id"]
            strategy_id = job.payload["strategy_id"]
            job.status = "succeeded"
            session.commit()

        version_dir = os.path.join(
            strategies.settings.workspaces_dir, strategy_id, "versions", version_id
        )
        os.makedirs(version_dir, exist_ok=True)
        with open(os.path.join(version_dir, "llm_meta.json"), "w", encoding="utf-8") as f:
            json.dump({"agent_summary": summary, "stop_reason": "task_done", "used_llm": True}, f)

        if modify_path is not None:
            with open(modify_path, "w", encoding="utf-8") as f:
                f.write("def generate_signals(data, params):\n    # refined\n    return {}\n")

        return "succeeded", ""

    monkeypatch.setattr(strategies, "_job_terminal_state", fake_terminal_state)
    monkeypatch.setattr(strategies, "enqueue_job", lambda *a, **k: None)


def _make_workspace(tmpdir, strat_id):
    strat_dir = os.path.join(tmpdir, strat_id, "strategy")
    os.makedirs(strat_dir, exist_ok=True)
    strat_py = os.path.join(strat_dir, "strategy.py")
    with open(strat_py, "w", encoding="utf-8") as f:
        f.write("def generate_signals(data, params):\n    return {}\n")
    return strat_dir, strat_py


def test_chat_with_strategy_qa_vs_refine(monkeypatch):
    from unittest.mock import MagicMock
    from control_plane.db import create_db_engine, create_session_factory, session_scope
    from control_plane.models import Base, Job, Strategy
    from control_plane.enums import ChatStatus
    from sqlalchemy import select
    from app.routers import strategies
    from app.routers.strategies import chat_with_strategy, ChatRequest

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = create_db_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        session_factory = create_session_factory(engine)

        monkeypatch.setattr(strategies.settings, "workspaces_dir", tmpdir)
        monkeypatch.setattr("app.routers.strategies.require_strategy_member", lambda *args, **kwargs: None)

        strat_id = "test-strat-qa"
        _strat_dir, strat_py = _make_workspace(tmpdir, strat_id)

        with session_scope(session_factory) as db:
            db.add(Strategy(id=strat_id, name="Test Strat", chat_status=ChatStatus.DONE, chat_history=[]))

        # 1. Q&A: the agent answers without touching the live strategy dir.
        _install_fake_worker(
            monkeypatch, strategies, session_factory, summary="这是一个布林带均值回归策略。"
        )
        with session_scope(session_factory) as db:
            resp = chat_with_strategy(
                strat_id,
                ChatRequest(message="解释一下这个策略"),
                MagicMock(),
                db=db,
                rds=None,
                session_factory=session_factory,
            )

            assert resp.reply == "这是一个布林带均值回归策略。"
            assert "Agent 已完成本次修改" not in resp.reply
            assert len(resp.chat_history) == 2
            assert resp.chat_history[-1]["content"] == "这是一个布林带均值回归策略。"

        # 2. Refine: the agent publishes a change, so the reply says so.
        _install_fake_worker(
            monkeypatch,
            strategies,
            session_factory,
            summary="已将 RSI 阈值调整为 30/70。",
            modify_path=strat_py,
        )
        with session_scope(session_factory) as db:
            resp = chat_with_strategy(
                strat_id,
                ChatRequest(message="把 RSI 阈值改成 30 和 70"),
                MagicMock(),
                db=db,
                rds=None,
                session_factory=session_factory,
            )

            assert "Agent 已完成本次修改，并已写入策略工作区。" in resp.reply
            assert "已将 RSI 阈值调整为 30/70。" in resp.reply

        # Every agent turn runs in a container, which needs a version workspace to
        # work in, so both turns are dispatched as REFINE_STRATEGY jobs.
        with session_scope(session_factory) as db:
            jobs = db.execute(select(Job)).scalars().all()
            assert len(jobs) == 2
            assert {j.payload["mode"] for j in jobs} == {"autonomous_chat_refine"}


def test_chat_with_strategy_reports_a_failed_agent_job(monkeypatch):
    from unittest.mock import MagicMock
    from control_plane.db import create_db_engine, create_session_factory, session_scope
    from control_plane.models import Base, Strategy
    from control_plane.enums import ChatStatus
    from app.routers import strategies
    from app.routers.strategies import chat_with_strategy, ChatRequest

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = create_db_engine(f"sqlite:///{os.path.join(tmpdir, 'fail.db')}")
        Base.metadata.create_all(engine)
        session_factory = create_session_factory(engine)

        monkeypatch.setattr(strategies.settings, "workspaces_dir", tmpdir)
        monkeypatch.setattr("app.routers.strategies.require_strategy_member", lambda *a, **k: None)
        monkeypatch.setattr(strategies, "enqueue_job", lambda *a, **k: None)
        monkeypatch.setattr(
            strategies,
            "_job_terminal_state",
            lambda _sf, _job_id: ("failed", "agent_container_exit_code=1"),
        )

        strat_id = "test-strat-fail"
        _make_workspace(tmpdir, strat_id)
        with session_scope(session_factory) as db:
            db.add(Strategy(id=strat_id, name="S", chat_status=ChatStatus.DONE, chat_history=[]))

        with session_scope(session_factory) as db:
            resp = chat_with_strategy(
                strat_id,
                ChatRequest(message="把周期改成 4h"),
                MagicMock(),
                db=db,
                rds=None,
                session_factory=session_factory,
            )

        assert "Agent 处理失败" in resp.reply
        assert "agent_container_exit_code=1" in resp.reply


@pytest.mark.anyio
async def test_chat_with_strategy_stream_qa_vs_refine(monkeypatch):
    from unittest.mock import MagicMock
    from control_plane.db import create_db_engine, create_session_factory, session_scope
    from control_plane.models import Base, Strategy
    from control_plane.enums import ChatStatus
    from app.routers import strategies
    from app.routers.strategies import chat_with_strategy_stream, ChatRequest

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_stream.db")
        engine = create_db_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        session_factory = create_session_factory(engine)

        monkeypatch.setattr(strategies.settings, "workspaces_dir", tmpdir)
        monkeypatch.setattr("app.routers.strategies.require_strategy_member", lambda *args, **kwargs: None)

        strat_id = "test-strat-stream"
        _strat_dir, strat_py = _make_workspace(tmpdir, strat_id)

        with session_scope(session_factory) as db:
            db.add(Strategy(id=strat_id, name="Test Strat Stream", chat_status=ChatStatus.DONE, chat_history=[]))

        # 1. Q&A streaming: no change published.
        _install_fake_worker(monkeypatch, strategies, session_factory, summary="该策略使用了RSI指标。")
        with session_scope(session_factory) as db:
            resp = chat_with_strategy_stream(
                strat_id,
                ChatRequest(message="使用了什么指标？"),
                MagicMock(),
                db=db,
                rds=None,
                session_factory=session_factory,
            )
            events = [chunk async for chunk in resp.body_iterator]

        joined = "".join(events)
        assert "该策略使用了RSI指标。" in joined
        assert "Agent 已完成本次修改" not in joined
        done_line = [line for line in events if '"type": "done"' in line][0]
        done_payload = json.loads(done_line.replace("data: ", "").strip())
        assert done_payload["clean_reply"] == "该策略使用了RSI指标。"

        # 2. Refine streaming: files changed.
        _install_fake_worker(
            monkeypatch,
            strategies,
            session_factory,
            summary="已将 RSI 周期修改为 21。",
            modify_path=strat_py,
        )
        with session_scope(session_factory) as db:
            resp = chat_with_strategy_stream(
                strat_id,
                ChatRequest(message="把 RSI 周期改成 21"),
                MagicMock(),
                db=db,
                rds=None,
                session_factory=session_factory,
            )
            events = [chunk async for chunk in resp.body_iterator]

        joined = "".join(events)
        assert "Agent 已完成本次修改，并已写入策略工作区。" in joined
        assert "已将 RSI 周期修改为 21。" in joined
        done_line = [line for line in events if '"type": "done"' in line][0]
        done_payload = json.loads(done_line.replace("data: ", "").strip())
        assert "Agent 已完成本次修改，并已写入策略工作区。" in done_payload["clean_reply"]
