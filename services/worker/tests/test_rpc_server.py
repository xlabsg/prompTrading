from __future__ import annotations


def test_rpc_server_list_strategy_files_only_returns_code_files(tmp_path):
    from worker.rpc_server import _list_strategy_files

    strat_dir = tmp_path / "strat"
    strat_dir.mkdir()
    (strat_dir / "strategy.py").write_text("print('code')", encoding="utf-8")
    (strat_dir / "strategy_live.py").write_text("print('live')", encoding="utf-8")
    (strat_dir / "overview.md").write_text("# Overview", encoding="utf-8")
    (strat_dir / "strategy_meta.json").write_text("{}", encoding="utf-8")
    (strat_dir / "params_schema.json").write_text("{}", encoding="utf-8")
    (strat_dir / "strategy_spec.yaml").write_text("spec", encoding="utf-8")
    (strat_dir / "strategy_protocol.json").write_text("{}", encoding="utf-8")

    res = _list_strategy_files(str(strat_dir))
    names = {f["name"] for f in res["files"]}
    assert names == {"strategy.py", "strategy_live.py"}
