"""
Enhanced runner with new prompt system and observability.

This module demonstrates the refactored approach using:
- PromptBuilder for unified prompt construction
- LLMMiddleware for rule-based decisions (reducing LLM calls)
- SessionMetrics for tracking costs and usage
- Langfuse integration for observability

Usage:
    # Set environment variables:
    # LANGFUSE_ENABLED=true
    # LANGFUSE_PUBLIC_KEY=pk-xxx
    # LANGFUSE_SECRET_KEY=sk-xxx
    # STRATEGY_ID=strategy_123
    # VERSION_ID=version_456
    # PROMPT="Create a moving average crossover strategy"

    python -m agent.runner_v2
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Optional

from agent.llm_openai_compat import (
    ChatCompletionRequest,
    ChatMessage,
    _strip_code_fences,
    chat_completion,
)
from agent.middleware import LLMMiddleware
from agent.observability.langfuse_client import get_langfuse
from agent.observability.metrics import SessionMetrics
from agent.pipeline.base import PipelineConfig
from agent.pipeline.enhanced import EnhancedPipeline
from agent.prompt.builder import PromptBuilder
from agent.templates import (
    DEFAULT_STRATEGY_PROTOCOL,
    DEFAULT_STRATEGY_SPEC_YAML,
    fallback_strategy_py,
)


@dataclass(frozen=True)
class LLMConfig:
    """LLM configuration."""

    api_key: Optional[str]
    base_url: str
    model: str
    temperature: float
    provider: str


@dataclass(frozen=True)
class StrategyResult:
    """Result from strategy generation."""

    code: str
    used_llm: bool
    model: str | None
    metadata: dict[str, Any] | None = None


# ============== Utility Functions ==============

def _env(name: str, default: str | None = None) -> str:
    """Get environment variable or raise."""
    v = os.getenv(name)
    if v is None or v == "":
        if default is None:
            raise RuntimeError(f"missing_env:{name}")
        return default
    return v


def _maybe_env(name: str) -> Optional[str]:
    """Get environment variable or return None."""
    v = os.getenv(name)
    if v is None or v == "":
        return None
    return v


def _ensure_dir(path: str) -> None:
    """Ensure directory exists."""
    os.makedirs(path, exist_ok=True)


def _write_text(path: str, text: str) -> None:
    """Write text to file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _write_json(path: str, payload: Any) -> None:
    """Write JSON to file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)


def _read_text(path: str) -> str:
    """Read text from file."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_json(path: str) -> dict[str, Any] | None:
    """Read JSON from file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _default_params_from_schema(params_schema: dict[str, Any] | None) -> dict[str, Any]:
    """Extract default params from schema."""
    params: dict[str, Any] = {}
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


def _platform_capabilities() -> dict[str, Any]:
    """Get platform capabilities."""
    indicators: list[str] = []
    try:
        from backtest import indicators as bt_indicators

        for name in dir(bt_indicators):
            if name.startswith("_"):
                continue
            value = getattr(bt_indicators, name, None)
            if callable(value):
                indicators.append(name)
        indicators.sort()
    except Exception:
        indicators = [
            "sma",
            "ema",
            "rsi",
            "macd",
            "bollinger_bands",
            "zscore",
            "cross_over",
            "cross_under",
        ]

    return {
        "engine": "vectorized",
        "signal_modes": ["target_weights"],
        "required_function": "generate_signals",
        "data_schema": {
            "columns": ["timestamp", "open", "high", "low", "close", "volume"],
        },
        "indicators": indicators,
        "notes": {
            "indicators": "List is non-exhaustive. Prefer backtest.indicators",
        },
        "validation_tools": ["static_check", "lint(ruff)", "mypy", "pytest", "smoke_backtest"],
        "restrictions": [
            "no_network_access_in_strategy_code",
            "no_file_io_in_strategy_code",
            "deterministic_only",
        ],
    }


def _validate_strategy_code(code: str) -> None:
    """Validate that code has generate_signals function."""
    tree = ast.parse(code)
    has_fn = any(
        isinstance(n, ast.FunctionDef) and n.name == "generate_signals"
        for n in tree.body
    )
    if not has_fn:
        raise ValueError("generated_code_missing_generate_signals")


def _strip_outer_markdown_fence(text: str) -> str:
    """Strip a single outer markdown fence wrapper while preserving inner code blocks."""
    value = (text or "").strip()
    if not value.startswith("```"):
        return value
    lines = value.splitlines()
    if len(lines) < 3:
        return value
    if lines[-1].strip() != "```":
        return value
    return "\n".join(lines[1:-1]).strip()


def _default_overview_markdown(summary: str) -> str:
    """Build a deterministic fallback overview markdown."""
    safe_summary = summary.strip() or "Strategy overview is not available yet."
    return (
        "# Summary\n\n"
        f"{safe_summary}\n\n"
        "# Trading Board\n\n"
        "- Focus: monitor K-line and equity behavior, position bias, and PnL health.\n"
        "- Suggested widgets: Price/Equity Candles, Signal Markers, Net PnL, Max Drawdown.\n"
        "- Risk cue: when drawdown expands while signal density rises, reduce risk.\n\n"
        "# Flow Animation\n\n"
        "```mermaid\n"
        "flowchart TD\n"
        "  A[Market Data Tick] --> B[Feature & Indicator Engine]\n"
        "  B --> C{State Router}\n"
        "  C -->|entry| D[Open Position]\n"
        "  C -->|rebalance| E[Adjust Weights]\n"
        "  D --> F[Risk Monitor]\n"
        "  E --> F\n"
        "  F -->|exit| G[Close Position]\n"
        "  G --> A\n"
        "```\n"
    )


def _ensure_overview_sections(markdown: str, summary: str) -> str:
    """Ensure overview markdown has minimal required sections for UI rendering."""
    value = (markdown or "").strip()
    if not value:
        return _default_overview_markdown(summary)

    lower = value.lower()
    if "summary" not in lower:
        value = f"# Summary\n\n{summary.strip() or 'Strategy summary unavailable.'}\n\n{value}"
        lower = value.lower()

    if "trading board" not in lower:
        value += (
            "\n\n# Trading Board\n\n"
            "- Focus on price structure, equity curve behavior, and risk state.\n"
            "- Watch net PnL, drawdown, and signal density together.\n"
        )
        lower = value.lower()

    if "flow animation" not in lower:
        value += "\n\n# Flow Animation\n"

    if "```mermaid" not in lower:
        value += (
            "\n\n```mermaid\n"
            "flowchart TD\n"
            "  A[Market Data Tick] --> B[Signal Engine]\n"
            "  B --> C{Decision}\n"
            "  C -->|entry| D[Open Position]\n"
            "  C -->|rebalance| E[Adjust Position]\n"
            "  D --> F[Risk Monitor]\n"
            "  E --> F\n"
            "  F -->|exit| G[Close Position]\n"
            "  G --> A\n"
            "```\n"
        )

    return value.strip() + "\n"


def _generate_overview_markdown(
    *,
    llm: LLMConfig,
    summary: str,
    strategy_code: str,
) -> tuple[str, str]:
    """Generate overview markdown via LLM, with deterministic fallback."""
    fallback = _default_overview_markdown(summary)
    if not llm.api_key:
        print("[agent] overview generation skipped: missing API key, using default")
        return fallback, "fallback_missing_api_key"

    code_excerpt = (strategy_code or "").strip()
    if len(code_excerpt) > 12000:
        code_excerpt = code_excerpt[:12000] + "\n# ... code truncated ..."

    system_prompt = (
        "You are a quantitative strategy documentation assistant. "
        "Output concise markdown only. Do not include prose outside markdown."
    )
    user_prompt = (
        "Generate `overview.md` for this strategy.\n\n"
        "Required structure:\n"
        "1. `# Summary`\n"
        "2. `# Trading Board`\n"
        "3. `# Flow Animation` with a `mermaid` flowchart code block.\n"
        "4. Optional: add one `g6` JSON block for state transitions.\n\n"
        "Keep the document concise and practical for dashboard users.\n\n"
        f"Strategy summary:\n{summary.strip() or 'Strategy'}\n\n"
        "Strategy code:\n"
        f"```python\n{code_excerpt}\n```"
    )

    try:
        req = ChatCompletionRequest(
            api_key=llm.api_key,
            base_url=llm.base_url,
            model=llm.model,
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ],
            temperature=min(float(llm.temperature), 0.2),
            timeout_s=180,
        )
        raw = str(chat_completion(req) or "")
        markdown = _strip_outer_markdown_fence(raw)
        return _ensure_overview_sections(markdown, summary), "llm"
    except Exception as exc:
        print(f"[agent] overview generation failed: {exc}")
        return fallback, "fallback_on_error"


def _llm_config() -> LLMConfig:
    """Load LLM config from environment."""
    provider = (_maybe_env("LLM_PROVIDER") or "").strip().lower()
    if not provider:
        provider = "deepseek" if _maybe_env("DEEPSEEK_API_KEY") else "openai"

    api_key = (
        _maybe_env("LLM_API_KEY")
        or _maybe_env("DEEPSEEK_API_KEY")
        or _maybe_env("OPENAI_API_KEY")
    )

    if provider == "deepseek":
        base_url = (
            _maybe_env("LLM_BASE_URL")
            or _maybe_env("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com/v1"
        )
        model = _maybe_env("LLM_MODEL") or _maybe_env("DEEPSEEK_MODEL") or "deepseek-chat"
        temperature = float(
            os.getenv("LLM_TEMPERATURE") or os.getenv("DEEPSEEK_TEMPERATURE") or "0.2"
        )
    else:
        base_url = _maybe_env("LLM_BASE_URL") or "https://api.openai.com/v1"
        model = _maybe_env("LLM_MODEL") or "gpt-4o-mini"
        temperature = float(os.getenv("LLM_TEMPERATURE") or "0.2")

    return LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        provider=provider,
    )


def _git_commit(strategy_dir: str, message: str) -> None:
    """Git commit changes."""
    git_dir = os.path.join(strategy_dir, ".git")
    if not os.path.exists(git_dir):
        return

    try:
        subprocess.run(
            ["git", "add", "."],
            cwd=strategy_dir,
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=strategy_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"[agent] git commit: {message[:60]}...")
    except Exception as e:
        print(f"[agent] git commit failed: {e}")


# ============== Main Runner ==============

def main() -> int:
    """Main entry point."""
    # 1. Initialize
    llm = _llm_config()
    strategy_id = _env("STRATEGY_ID")
    version_id = _env("VERSION_ID")
    prompt = _env("PROMPT", "")
    workspaces_dir = _env("WORKSPACES_DIR", "/workspaces")

    version_dir = os.path.join(workspaces_dir, strategy_id, "versions", version_id)
    strategy_dir = os.path.join(workspaces_dir, strategy_id, "strategy")
    _ensure_dir(version_dir)
    _ensure_dir(strategy_dir)

    # 2. Load current code
    current_code = ""
    try:
        current_path = os.path.join(strategy_dir, "strategy.py")
        if os.path.isfile(current_path):
            with open(current_path, "r", encoding="utf-8") as f:
                current_code = f.read()
    except Exception:
        current_code = ""
    is_first_generation = not bool(current_code.strip())

    # 3. Initialize session metrics
    session_metrics = SessionMetrics(session_id=strategy_id)

    # 4. Build prompt and platform info
    platform_caps = _platform_capabilities()
    prompt_builder = PromptBuilder(
        default_language=LLMMiddleware.detect_language(prompt),
        max_code_length=8000,
    )

    # 5. Configure pipeline
    pipeline_config = PipelineConfig(
        api_key=llm.api_key,
        base_url=llm.base_url,
        model=llm.model,
        temperature=llm.temperature,
        provider=llm.provider,
    )

    pipeline = EnhancedPipeline(
        config=pipeline_config,
        prompt_builder=prompt_builder,
        session_metrics=session_metrics,
    )

    # 6. Generate strategy
    try:
        result = pipeline.run(
            prompt=prompt,
            current_code=current_code,
            platform_capabilities=platform_caps,
        )
        code = result.code
        used_llm = True
    except Exception as exc:
        print(f"[agent] pipeline_failed: {exc}", file=sys.stderr)
        fallback_on_error = (
            (os.getenv("LLM_FALLBACK_ON_ERROR") or "").strip().lower()
            in ("1", "true", "yes")
        )
        if fallback_on_error:
            code = fallback_strategy_py(prompt)
            used_llm = False
        else:
            raise

    # 7. Write artifacts
    _write_text(os.path.join(version_dir, "strategy.py"), code)
    _write_text(
        os.path.join(version_dir, "strategy_spec.yaml"),
        DEFAULT_STRATEGY_SPEC_YAML,
    )
    _write_json(
        os.path.join(version_dir, "strategy_protocol.json"),
        DEFAULT_STRATEGY_PROTOCOL,
    )

    # 8. Also update current strategy
    _write_text(os.path.join(strategy_dir, "strategy.py"), code)
    _write_text(
        os.path.join(strategy_dir, "strategy_spec.yaml"),
        DEFAULT_STRATEGY_SPEC_YAML,
    )
    _write_json(
        os.path.join(strategy_dir, "strategy_protocol.json"),
        DEFAULT_STRATEGY_PROTOCOL,
    )

    # 9. Build params schema
    params_schema = _build_params_schema(code)
    _write_json(os.path.join(version_dir, "params_schema.json"), params_schema)
    _write_json(os.path.join(strategy_dir, "params_schema.json"), params_schema)

    # 10. Build metadata
    summary = prompt.strip().splitlines()[0][:80] if prompt else "Strategy"
    meta_payload = {
        "version": 1,
        "summary": summary,
        "params_schema": params_schema,
        "signal_mode": DEFAULT_STRATEGY_PROTOCOL.get("signal_mode", "target_weights"),
    }
    _write_json(os.path.join(version_dir, "strategy_meta.json"), meta_payload)
    _write_json(os.path.join(strategy_dir, "strategy_meta.json"), meta_payload)

    # 11. Generate overview markdown as a delivery artifact.
    # Only trigger LLM overview generation on first strategy creation.
    overview_status = "reused_existing"
    if is_first_generation:
        overview_md, overview_status = _generate_overview_markdown(
            llm=llm,
            summary=summary,
            strategy_code=code,
        )
    else:
        overview_path = os.path.join(strategy_dir, "overview.md")
        if os.path.isfile(overview_path):
            overview_md = _read_text(overview_path)
        else:
            overview_md = _default_overview_markdown(summary)
            overview_status = "fallback_non_first_generation"
    overview_md = _ensure_overview_sections(overview_md, summary)
    _write_text(os.path.join(version_dir, "overview.md"), overview_md)
    _write_text(os.path.join(strategy_dir, "overview.md"), overview_md)

    # 12. Write LLM metadata
    llm_meta_payload = {
        "used_llm": used_llm,
        "model": llm.model if used_llm else None,
        "base_url": llm.base_url if used_llm else None,
        "temperature": llm.temperature if used_llm else None,
        "pipeline": "enhanced_v2",
        "summary": summary,
        "params_schema": params_schema,
        "signal_mode": DEFAULT_STRATEGY_PROTOCOL.get("signal_mode", "target_weights"),
        "overview_status": overview_status,
    }
    _write_json(os.path.join(version_dir, "llm_meta.json"), llm_meta_payload)

    # 13. Git commit
    commit_msg = f"AI: {prompt[:80]}" if prompt else "AI: strategy update"
    _git_commit(strategy_dir, commit_msg)

    # 14. Print session summary
    print("\n=== Session Summary ===")
    print(json.dumps(session_metrics.summary(), indent=2))

    # 15. Flush Langfuse
    get_langfuse().flush()

    print("[agent] wrote strategy.py, strategy_spec.yaml and overview.md")
    return 0


def _build_params_schema(code: str) -> dict[str, Any]:
    """Build params schema from code."""
    try:
        tree = ast.parse(code)
    except Exception:
        return {"version": 1, "params": []}

    params: list[dict[str, Any]] = []
    seen: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute):
            continue
        if fn.attr != "get":
            continue
        if not isinstance(fn.value, ast.Name) or fn.value.id != "params":
            continue
        if not node.args:
            continue

        key_node = node.args[0]
        if isinstance(key_node, ast.Constant):
            key_val = key_node.value
        else:
            continue

        if not isinstance(key_val, str) or key_val in seen:
            continue
        seen.add(key_val)

        entry: dict[str, Any] = {"name": key_val}

        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            default_val = node.args[1].value
            entry["default"] = default_val

            if isinstance(default_val, bool):
                entry["type"] = "bool"
            elif isinstance(default_val, int):
                entry["type"] = "int"
            elif isinstance(default_val, float):
                entry["type"] = "float"
            elif isinstance(default_val, str):
                entry["type"] = "str"

        params.append(entry)

    return {"version": 1, "params": params}


if __name__ == "__main__":
    raise SystemExit(main())
