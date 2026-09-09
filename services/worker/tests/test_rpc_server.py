from __future__ import annotations


def test_rpc_server_list_strategy_files_include_system_toggle(tmp_path):
    from worker.rpc_server import _list_strategy_files

    strat_dir = tmp_path / "strat"
    strat_dir.mkdir()
    (strat_dir / "strategy.py").write_text("print('code')", encoding="utf-8")
    (strat_dir / "strategy_live.py").write_text("print('live')", encoding="utf-8")
    (strat_dir / "overview.md").write_text("# Overview", encoding="utf-8")
    (strat_dir / "strategy_meta.json").write_text("{}", encoding="utf-8")
    (strat_dir / "params_schema.json").write_text("{}", encoding="utf-8")

    # Default (include_system=False)
    res_default = _list_strategy_files(str(strat_dir), include_system=False)
    names_default = {f["name"] for f in res_default["files"]}
    assert names_default == {"strategy.py", "strategy_live.py"}

    # With include_system=True
    res_system = _list_strategy_files(str(strat_dir), include_system=True)
    names_system = {f["name"] for f in res_system["files"]}
    assert names_system == {"strategy.py", "strategy_live.py", "overview.md", "strategy_meta.json", "params_schema.json"}
