"""Regression tests for refine prompt symbol decoupling."""

from agent.prompt.builder import PromptBuilder
from agent.prompt.templates import STRATEGY_GENERATION_REFINE


def test_refine_template_has_no_symbol_placeholder() -> None:
    """Refine prompt must not require symbol-level context."""
    assert "{symbol}" not in STRATEGY_GENERATION_REFINE.system_template
    assert "{symbol}" not in STRATEGY_GENERATION_REFINE.user_template


def test_refine_prompt_build_does_not_require_symbol() -> None:
    """Building refine prompt should succeed with strategy-only context."""
    builder = PromptBuilder()
    current_code = (
        "def generate_signals(data, params):\n"
        "    return {\n"
        "        'target_weights': [0.0],\n"
        "        'weight_reason': ['hold'],\n"
        "        'debug_a': [0.0],\n"
        "        'debug_b': [0.0],\n"
        "    }\n"
    )
    platform_capabilities = {
        "indicators": ["sma", "rsi"],
        "signal_modes": ["target_weights"],
        "required_function": "generate_signals",
    }

    _, _, meta = builder.build_strategy_generation(
        prompt="add short logic",
        current_code=current_code,
        platform_capabilities=platform_capabilities,
    )

    assert meta["template"] == "strategy_generation_refine"
