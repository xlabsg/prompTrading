import ast
import os
import tempfile
from dataclasses import dataclass
from typing import Any

from control_plane.templates import (
    TEMPLATE_STRATEGIES,
    get_template_strategy_code,
    instantiate_strategy_from_template,
)


@dataclass
class MockTemplate:
    id: str
    name: str
    prompt: str = ""
    config_snapshot: dict[str, Any] = None


def test_get_template_strategy_code():
    code_div = get_template_strategy_code("tmpl-divergence")
    assert "Divergence-style mean reversion" in code_div
    ast.parse(code_div)

    code_fallback = get_template_strategy_code("unknown-template-xyz")
    assert "Moving Average Crossover Strategy" in code_fallback
    ast.parse(code_fallback)


def test_instantiate_strategy_from_template():
    with tempfile.TemporaryDirectory() as tmp_workspaces:
        strategy_id = "strat-test-123"
        version_id = "ver-test-456"
        tmpl = MockTemplate(
            id="tmpl-divergence",
            name="divergence",
            prompt="Divergence prompt test",
            config_snapshot={"ema_fast_window": 15, "ema_slow_window": 45},
        )

        paths = instantiate_strategy_from_template(
            workspaces_dir=tmp_workspaces,
            strategy_id=strategy_id,
            version_id=version_id,
            template=tmpl,
        )

        strategy_py = os.path.join(paths.strategy_dir, "strategy.py")
        assert os.path.exists(strategy_py)
        with open(strategy_py) as f:
            content = f.read()
            assert "Divergence-style mean reversion" in content
            ast.parse(content)

        spec_file = os.path.join(paths.strategy_dir, "strategy_spec.yaml")
        assert os.path.exists(spec_file)

        protocol_file = os.path.join(paths.strategy_dir, "strategy_protocol.json")
        assert os.path.exists(protocol_file)

        git_dir = os.path.join(paths.strategy_dir, ".git")
        assert os.path.exists(git_dir)

        # Check version snapshot
        version_strategy_py = os.path.join(paths.versions_dir, version_id, "strategy.py")
        assert os.path.exists(version_strategy_py)
        with open(version_strategy_py) as f:
            v_content = f.read()
            assert "Divergence-style mean reversion" in v_content


def test_every_builtin_template_compiles_and_defines_generate_signals():
    """Every entry must be executable, since it is written straight to strategy.py."""
    assert TEMPLATE_STRATEGIES, "no builtin templates registered"
    for template_id, code in TEMPLATE_STRATEGIES.items():
        tree = ast.parse(code, filename=template_id)
        names = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert "generate_signals" in names, f"{template_id} defines no generate_signals"


if __name__ == "__main__":
    test_get_template_strategy_code()
    print("test_get_template_strategy_code passed!")
    test_instantiate_strategy_from_template()
    print("test_instantiate_strategy_from_template passed!")
