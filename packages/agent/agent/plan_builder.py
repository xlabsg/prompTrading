from __future__ import annotations

import json
import textwrap
from typing import Any

from agent.llm_openai_compat import ChatCompletionRequest, ChatMessage, chat_completion
from agent.middleware import LLMMiddleware
from agent.pipeline.base import extract_json_from_text
from agent.prompt.builder import PromptBuilder
from agent.prompt.context import prepare_code_context


_REQUIRED_TOP_KEYS = {
    "version",
    "goal",
    "targets",
    "interface_constraints",
    "change_spec",
    "deliverables",
    "validation_steps",
    "acceptance_criteria",
    "risks",
}


# Global prompt builder (lazy init)
_prompt_builder: PromptBuilder | None = None


def _get_prompt_builder() -> PromptBuilder:
    """Get or create the global PromptBuilder."""
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = PromptBuilder()
    return _prompt_builder


def _default_params(params_schema: dict[str, Any] | None) -> dict[str, Any]:
    params = {}
    if not params_schema:
        return params
    for item in params_schema.get("params") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            continue
        if "default" in item:
            params[str(name)] = item.get("default")
    return params


def _fallback_plan(*, prompt: str, protocol: dict[str, Any], params_schema: dict[str, Any] | None) -> dict[str, Any]:
    default_params = _default_params(params_schema)
    return {
        "version": 1,
        "goal": {
            "strategy_logic": prompt.strip()[:240],
            "symbol": "BTCUSDT",
            "interval": "1h",
            "signals": "target_weights",
            "risk": "basic risk controls in signal logic",
            "positioning": "bi-directional",
            "cost_model": "fee_rate + slippage_bps",
        },
        "targets": {
            "files": [
                "strategy.py",
                "strategy_spec.yaml",
                "strategy_protocol.json",
                "params_schema.json",
                "strategy_meta.json",
                "plan.json",
                "backtest_config.json",
                "smoke_backtest.py",
                "README.md",
            ],
            "functions": [
                {
                    "file": "strategy.py",
                    "name": "generate_signals",
                    "signature": "(data: pandas.DataFrame, params: dict) -> dict",
                    "behavior": "Return vectorized target_weights with reasons and debug series.",
                }
            ],
        },
        "interface_constraints": {
            "required_function": "generate_signals",
            "input_columns": protocol.get("input", {}).get("data_schema", {}).get("columns", []),
            "output_required_series": protocol.get("output", {}).get("required_series", []),
            "debug_series": protocol.get("output", {}).get("debug_series", {}),
        },
        "change_spec": {
            "version": 1,
            "operations": [],
        },
        "deliverables": {
            "files": [
                "strategy.py",
                "strategy_spec.yaml",
                "strategy_protocol.json",
                "params_schema.json",
                "strategy_meta.json",
                "plan.json",
                "backtest_config.json",
                "smoke_backtest.py",
                "strategy_explain.json",
                "README.md",
            ],
            "default_params": default_params,
            "smoke_test": {
                "type": "synthetic_backtest",
                "n_bars": 200,
                "interval": "1h",
            },
        },
        "validation_steps": [
            "static_check",
            "lint",
            "mypy",
            "pytest",
            "smoke_backtest",
            "real_backtest",
        ],
        "acceptance_criteria": [
            "strategy module imports",
            "generate_signals returns required fields",
            "dry-run backtest completes without error",
        ],
        "risks": [
            "no_live_trading",
            "no_network_access",
            "deterministic_only",
        ],
    }


def should_generate_plan(
    *,
    llm: Any | None,
    prompt: str,
    current_code: str,
) -> bool:
    """Decide whether to generate a structured plan.

    Now uses LLMMiddleware rules instead of LLM call for faster,
    cheaper decision making.

    Args:
        llm: LLM configuration (unused, kept for compatibility).
        prompt: User request prompt.
        current_code: Existing strategy code.

    Returns:
        True if plan generation is recommended.
    """
    # Use rule-based decision from middleware
    should_plan, _reason = LLMMiddleware.should_generate_plan(prompt, current_code)
    return should_plan


def _is_valid_plan(plan: dict[str, Any]) -> bool:
    """Validate plan structure, supporting both V1 and V2 formats."""
    if not isinstance(plan, dict):
        return False
    # Support version 1 and 2
    plan_version = plan.get("version")
    if plan_version not in (1, 2):
        return False
    if not _REQUIRED_TOP_KEYS.issubset(plan.keys()):
        return False
    if not isinstance(plan.get("targets"), dict):
        return False
    if not isinstance(plan.get("change_spec"), dict):
        return False
    if not _is_valid_change_spec(plan.get("change_spec")):
        return False
    if not isinstance(plan.get("validation_steps"), list):
        return False
    if not isinstance(plan.get("acceptance_criteria"), list):
        return False
    if not isinstance(plan.get("risks"), list):
        return False
    return True


def _is_valid_change_spec(change_spec: dict[str, Any] | None) -> bool:
    """Validate change_spec structure, supporting both V1 and V2 operations."""
    if not isinstance(change_spec, dict):
        return False
    operations = change_spec.get("operations")
    if operations is None:
        return True
    if not isinstance(operations, list):
        return False
    if not operations:
        return True  # Empty operations list is valid
    for op in operations:
        if not isinstance(op, dict):
            return False

        op_type = op.get("type")

        # V1: exact_replace operations
        if op_type == "exact_replace":
            file_path = op.get("file_path") or "strategy.py"
            if file_path != "strategy.py":
                return False
            old_text = op.get("old_text")
            new_text = op.get("new_text")
            if not isinstance(old_text, str) or not isinstance(new_text, str):
                return False
            if old_text.strip() == "":
                return False

        # V2: semantic_edit operations
        elif op_type == "semantic_edit":
            function_name = op.get("function_name")
            anchor = op.get("anchor")
            new_code_snippet = op.get("new_code_snippet")
            if not isinstance(function_name, str) or not function_name.strip():
                return False
            if not isinstance(anchor, str) or not anchor.strip():
                return False
            if not isinstance(new_code_snippet, str) or not new_code_snippet.strip():
                return False

        else:
            return False  # Unknown operation type

    return True


def build_plan(
    *,
    llm: Any | None,
    prompt: str,
    current_code: str,
    protocol: dict[str, Any],
    platform_capabilities: dict[str, Any] | None = None,
    params_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured delivery plan.

    Args:
        llm: LLM configuration.
        prompt: User request prompt.
        current_code: Existing strategy code.
        protocol: Strategy protocol dictionary.
        platform_capabilities: Platform capabilities.
        params_schema: Parameter schema.

    Returns:
        Plan dictionary.
    """
    if llm and getattr(llm, "api_key", None):
        # Use PromptBuilder for consistent prompt generation
        builder = _get_prompt_builder()
        system, user, _ = builder.build_plan_generation(
            prompt=prompt,
            current_code=current_code,
            protocol=protocol,
            platform_capabilities=platform_capabilities or {},
            params_schema=params_schema,
        )

        req = ChatCompletionRequest(
            api_key=getattr(llm, "api_key", "") or "",
            base_url=str(getattr(llm, "base_url", "")),
            model=str(getattr(llm, "model", "")),
            messages=[ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)],
            temperature=0.1,
        )

        raw = chat_completion(req)
        try:
            plan = json.loads(extract_json_from_text(raw))
            if _is_valid_plan(plan):
                return plan
        except Exception:
            pass

    return _fallback_plan(prompt=prompt, protocol=protocol, params_schema=params_schema)


__all__ = ["build_plan", "should_generate_plan"]
