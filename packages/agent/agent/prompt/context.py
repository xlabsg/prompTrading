"""
Context processing utilities for prompt building.

Provides:
- Intelligent code truncation (AST-based, not character count)
- Platform capabilities formatting
- Smart indicator documentation retrieval
"""

from __future__ import annotations

import ast
from typing import Any

from agent.prompt.indicator_docs import build_indicator_docs


def prepare_code_context(
    code: str,
    *,
    max_length: int = 8000,
    include_imports: bool = True,
    include_function_signatures: bool = True,
) -> str:
    """Prepare code context for LLM input with intelligent truncation.

    Instead of naive character truncation, this function:
    1. Keeps imports (critical for context)
    2. Keeps the generate_signals function (most important)
    3. Keeps other important code, space permitting
    4. Falls back to simple truncation if parsing fails

    Args:
        code: The source code to process.
        max_length: Maximum length in characters.
        include_imports: Whether to include import statements.
        include_function_signatures: Whether to include function signatures.

    Returns:
        The processed code context, truncated if necessary.
    """
    if not code:
        return "# Empty"

    if len(code) <= max_length:
        return code

    # Try to parse and intelligently truncate
    try:
        tree = ast.parse(code)
        important_parts: list[str] = []

        # 1. Imports (always important)
        if include_imports:
            imports: list[str] = []
            for node in tree.body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    source = ast.get_source_segment(code, node)
                    if source:
                        imports.append(source)
            if imports:
                important_parts.append("\n".join(imports))

        # 2. generate_signals function (most critical)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "generate_signals":
                source = ast.get_source_segment(code, node)
                if source:
                    important_parts.append(source)
                break

        # 3. Check remaining budget
        current_length = sum(len(p) for p in important_parts)
        remaining = max_length - current_length - 100  # Buffer for separator

        if remaining > 500:
            # Add other classes and functions, space permitting
            for node in tree.body:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    name = node.name if isinstance(node, ast.FunctionDef) else node.name
                    if name == "generate_signals":
                        continue
                    source = ast.get_source_segment(code, node)
                    if not source:
                        continue
                    if len(source) <= remaining:
                        important_parts.append(source)
                        remaining -= len(source)
                    else:
                        break

        result = "\n\n".join(important_parts)

        # If still too long, do final truncation
        if len(result) > max_length:
            result = result[:max_length] + "\n# ... (truncated)"

        # If we got nothing useful, fall back to simple truncation
        if len(result.strip()) < 100:
            return code[:max_length] + "\n# ... (truncated)"

        return result

    except Exception:
        # Parsing failed, fall back to simple truncation
        return code[:max_length] + "\n# ... (truncated)"


def _extract_indicators_list(capabilities: dict[str, Any]) -> list[str]:
    """Extract and format the list of available indicators.

    Args:
        capabilities: Platform capabilities dictionary.

    Returns:
        List of indicator names.
    """
    indicators = capabilities.get("indicators", [])
    if not indicators:
        return [
            "sma",
            "ema",
            "rsi",
            "macd",
            "bollinger_bands",
            "zscore",
            "cross_over",
            "cross_under",
        ]
    # Show first 15 to avoid overwhelming the prompt
    return list(indicators)[:15]


def build_platform_info(
    capabilities: dict[str, Any],
    user_prompt: str = "",
) -> str:
    """Format platform capabilities information for the prompt.

    Smart indicator documentation: Only includes indicators relevant
    to the user's request, keeping prompts concise.

    Args:
        capabilities: Dictionary of platform capabilities.
        user_prompt: User's request text (for smart indicator selection).

    Returns:
        Formatted string describing available platform features.
    """
    from agent.prompt.indicator_docs import build_indicator_docs

    signal_modes = capabilities.get("signal_modes", ["target_weights"])
    signal_mode = signal_modes[0] if signal_modes else "target_weights"

    indicator_docs = build_indicator_docs(user_prompt, max_indicators=8)

    return f"""{indicator_docs}

Required Function:
  generate_signals(data: pd.DataFrame, params: dict) -> dict

Signal Mode: {signal_mode}

Data Schema:
  columns: timestamp, open, high, low, close, volume

Restrictions:
  - No network access
  - No file I/O
  - Deterministic only (no randomness)
  - Use vectorized pandas/numpy operations
"""


__all__ = [
    "prepare_code_context",
    "build_platform_info",
    "build_indicator_docs",
]
