from __future__ import annotations

import os
import tempfile
import pytest

from app.routers.strategies import (
    _build_strategy_agent_task,
    _snapshot_workspace_fingerprint,
    _strategy_code_problems,
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


def test_strategy_code_problems():
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. strategy.py missing
        assert len(_strategy_code_problems(tmpdir)) > 0

        # 2. strategy.py empty
        strat_py = os.path.join(tmpdir, "strategy.py")
        with open(strat_py, "w", encoding="utf-8") as f:
            f.write("")
        assert len(_strategy_code_problems(tmpdir)) > 0

        # 3. strategy.py syntax error
        with open(strat_py, "w", encoding="utf-8") as f:
            f.write("def broken(:")
        assert any("syntax" in p.lower() or "parse" in p.lower() for p in _strategy_code_problems(tmpdir))

        # 4. strategy.py valid
        with open(strat_py, "w", encoding="utf-8") as f:
            f.write("def generate_signals(data, params):\n    return {}\n")
        assert _strategy_code_problems(tmpdir) == []


def test_run_autonomous_refine_detects_files_changed(monkeypatch):
    from app.routers import strategies
    from app.routers.strategies import _run_autonomous_refine

    with tempfile.TemporaryDirectory() as tmpdir:
        strat_id = "test-strat-1"
        strat_dir = os.path.join(tmpdir, strat_id, "strategy")
        os.makedirs(strat_dir, exist_ok=True)
        strat_py = os.path.join(strat_dir, "strategy.py")
        with open(strat_py, "w", encoding="utf-8") as f:
            f.write("def generate_signals(data, params):\n    return {}\n")

        monkeypatch.setattr(strategies.settings, "workspaces_dir", tmpdir)

        class DummySession:
            def __init__(self, summary):
                self.summary = summary
                self.actions = []

        # Case 1: Agent modifies strategy.py
        def fake_run_session_modify(*args, **kwargs):
            with open(strat_py, "w", encoding="utf-8") as f:
                f.write("def generate_signals(data, params):\n    # modified\n    return {'ETH/USDT': 1.0}\n")
            return DummySession("已将仓位调整为全仓做多。")

        monkeypatch.setattr("agent.tau_driver.run_session", fake_run_session_modify)
        res_mod = _run_autonomous_refine(strat_id, "修改仓位为全仓做多")
        assert res_mod["files_changed"] is True
        assert res_mod["agent_summary"] == "已将仓位调整为全仓做多。"

        # Case 2: Agent purely answers question without modifying any files
        def fake_run_session_qa(*args, **kwargs):
            return DummySession("该策略的核心逻辑是基于均线金叉死叉入场。")

        monkeypatch.setattr("agent.tau_driver.run_session", fake_run_session_qa)
        res_qa = _run_autonomous_refine(strat_id, "给我描述一下这个策略的逻辑")
        assert res_qa["files_changed"] is False
        assert res_qa["agent_summary"] == "该策略的核心逻辑是基于均线金叉死叉入场。"


def test_chat_with_strategy_qa_vs_refine(monkeypatch):
    from unittest.mock import MagicMock
    from control_plane.db import create_db_engine, create_session_factory, session_scope
    from control_plane.models import Base, Strategy, StrategyVersion
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
        strat_dir = os.path.join(tmpdir, strat_id, "strategy")
        os.makedirs(strat_dir, exist_ok=True)
        strat_py = os.path.join(strat_dir, "strategy.py")
        with open(strat_py, "w", encoding="utf-8") as f:
            f.write("def generate_signals(data, params):\n    return {}\n")

        with session_scope(session_factory) as db:
            s = Strategy(
                id=strat_id,
                name="Test Strat",
                chat_status=ChatStatus.DONE,
                chat_history=[],
            )
            db.add(s)

        # 1. Q&A scenario: Fast LLM answer without running autonomous refine
        with session_scope(session_factory) as db:
            monkeypatch.setattr(
                "app.routers.strategies._call_chat_llm",
                lambda *args, **kwargs: "这是一个布林带均值回归策略。",
            )
            req = ChatRequest(message="解释一下这个策略")
            dummy_request = MagicMock()
            resp = chat_with_strategy(strat_id, req, dummy_request, db=db, rds=None)

            assert resp.reply == "这是一个布林带均值回归策略。"
            assert "Agent 已完成本次修改" not in resp.reply
            # Verify no StrategyVersion was created
            versions = db.execute(select(StrategyVersion).where(StrategyVersion.strategy_id == strat_id)).scalars().all()
            assert len(versions) == 0
            # Verify chat history updated
            assert len(resp.chat_history) == 2
            assert resp.chat_history[-1]["content"] == "这是一个布林带均值回归策略。"

        # 2. Refine scenario: Tau changes files
        with session_scope(session_factory) as db:
            monkeypatch.setattr(
                "app.routers.strategies._run_autonomous_refine",
                lambda *args, **kwargs: {
                    "agent_summary": "已将 RSI 阈值调整为 30/70。",
                    "files_changed": True,
                },
            )
            req = ChatRequest(message="把 RSI 阈值改成 30 和 70")
            dummy_request = MagicMock()
            resp = chat_with_strategy(strat_id, req, dummy_request, db=db, rds=None)

            assert "Agent 已完成本次修改，并已写入策略工作区。" in resp.reply
            assert "已将 RSI 阈值调整为 30/70。" in resp.reply
            # Verify StrategyVersion was created
            versions = db.execute(select(StrategyVersion).where(StrategyVersion.strategy_id == strat_id)).scalars().all()
            assert len(versions) == 1


@pytest.mark.anyio
async def test_chat_with_strategy_stream_qa_vs_refine(monkeypatch):
    import json
    from unittest.mock import MagicMock
    from control_plane.db import create_db_engine, create_session_factory, session_scope
    from control_plane.models import Base, Strategy, StrategyVersion
    from control_plane.enums import ChatStatus
    from sqlalchemy import select
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
        strat_dir = os.path.join(tmpdir, strat_id, "strategy")
        os.makedirs(strat_dir, exist_ok=True)
        strat_py = os.path.join(strat_dir, "strategy.py")
        with open(strat_py, "w", encoding="utf-8") as f:
            f.write("def generate_signals(data, params):\n    return {}\n")

        with session_scope(session_factory) as db:
            s = Strategy(
                id=strat_id,
                name="Test Strat Stream",
                chat_status=ChatStatus.DONE,
                chat_history=[],
            )
            db.add(s)

        # 1. Q&A streaming: Fast LLM answer without running autonomous refine
        with session_scope(session_factory) as db:
            monkeypatch.setattr(
                "app.routers.strategies._call_chat_llm",
                lambda *args, **kwargs: "该策略使用了RSI指标。",
            )

            req = ChatRequest(message="使用了什么指标？")
            dummy_request = MagicMock()
            resp = chat_with_strategy_stream(
                strat_id, req, dummy_request, db=db, rds=None, session_factory=session_factory
            )

            events = [chunk async for chunk in resp.body_iterator]
            joined = "".join(events)
            assert "该策略使用了RSI指标。" in joined
            assert "Agent 已完成本次修改" not in joined

            # Check done event
            done_line = [line for line in events if '"type": "done"' in line][0]
            done_payload = json.loads(done_line.replace("data: ", "").strip())
            assert done_payload["clean_reply"] == "该策略使用了RSI指标。"

            # Verify no version was saved
            versions = db.execute(select(StrategyVersion).where(StrategyVersion.strategy_id == strat_id)).scalars().all()
            assert len(versions) == 0

        # 2. Refine streaming: files changed
        with session_scope(session_factory) as db:
            def fake_run_mod(*args, **kwargs):
                on_progress = kwargs.get("on_progress")
                if on_progress:
                    on_progress({"tool": "write", "path": "strategy.py", "phase": "executing"})
                return {
                    "agent_summary": "已将 RSI 周期修改为 21。",
                    "files_changed": True,
                }
            monkeypatch.setattr("app.routers.strategies._run_autonomous_refine", fake_run_mod)

            req = ChatRequest(message="把 RSI 周期改成 21")
            dummy_request = MagicMock()
            resp = chat_with_strategy_stream(
                strat_id, req, dummy_request, db=db, rds=None, session_factory=session_factory
            )

            events = [chunk async for chunk in resp.body_iterator]
            joined = "".join(events)
            assert "Agent 已完成本次修改，并已写入策略工作区。" in joined
            assert "已将 RSI 周期修改为 21。" in joined

            # Check done event
            done_line = [line for line in events if '"type": "done"' in line][0]
            done_payload = json.loads(done_line.replace("data: ", "").strip())
            assert "Agent 已完成本次修改，并已写入策略工作区。" in done_payload["clean_reply"]

            # Verify version was saved
            versions = db.execute(select(StrategyVersion).where(StrategyVersion.strategy_id == strat_id)).scalars().all()
            assert len(versions) == 1


def test_classify_done_chat_intent_qa():
    from app.routers.strategies import _classify_done_chat_intent

    assert _classify_done_chat_intent("给我描述一下这个策略的逻辑") == "chat"
    assert _classify_done_chat_intent("解释一下这个策略") == "chat"
    assert _classify_done_chat_intent("讲讲这个策略的核心逻辑") == "chat"
    assert _classify_done_chat_intent("说明一下这个策略是怎么产生信号的") == "chat"
    assert _classify_done_chat_intent("分析一下回测表现") == "chat"
    assert _classify_done_chat_intent("这个策略的原理是什么？") == "chat"
    assert _classify_done_chat_intent("为什么最近一笔交易止损了？") == "chat"
    assert _classify_done_chat_intent("用了什么指标？") == "chat"
    assert _classify_done_chat_intent("解释一下为什么把均线改成20？") == "chat"
    assert _classify_done_chat_intent("可以把止损改成3%吗？") == "chat"
    assert _classify_done_chat_intent("你好") == "chat"
    assert _classify_done_chat_intent("") == "chat"


def test_classify_done_chat_intent_refine():
    from app.routers.strategies import _classify_done_chat_intent

    assert _classify_done_chat_intent("把止损改成3%") == "refine"
    assert _classify_done_chat_intent("将周期调整为 4h") == "refine"
    assert _classify_done_chat_intent("改成双均线策略") == "refine"
    assert _classify_done_chat_intent("增加一个 14 周期的 RSI 过滤条件") == "refine"
    assert _classify_done_chat_intent("去掉做空逻辑，只保留做多") == "refine"
    assert _classify_done_chat_intent("修改入场信号：金叉且在零轴之上") == "refine"
    assert _classify_done_chat_intent("优化代码，加入移动止盈") == "refine"
    assert _classify_done_chat_intent("remove short trading logic") == "refine"
    assert _classify_done_chat_intent("change stop loss to 3%") == "refine"
    assert _classify_done_chat_intent("add an RSI filter") == "refine"






