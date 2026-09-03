"""
Context processing utilities for prompt building.

Provides:
- Improved language detection (keywords + Unicode)
- Intelligent code truncation (AST-based, not character count)
- Platform capabilities formatting
- Smart indicator documentation retrieval
"""

from __future__ import annotations

import ast
import re
from typing import Any

from agent.prompt.indicator_docs import build_indicator_docs


# Language-specific keywords for improved detection
_ZH_KEYWORDS = [
    "策略",
    "交易",
    "均线",
    "入场",
    "出场",
    "回测",
    "参数",
    "止损",
    "止盈",
    "趋势",
    "突破",
    "回调",
    "震荡",
    "做多",
    "做空",
    "信号",
    "指标",
    "布林",
    " MACD ",
]

_EN_KEYWORDS = [
    "strategy",
    "trading",
    "moving average",
    "entry",
    "exit",
    "backtest",
    "parameter",
    "stop loss",
    "take profit",
    "trend",
    "breakout",
    "pullback",
    "range",
    "long",
    "short",
    "signal",
    "indicator",
    "bollinger",
    "macd",
]


def detect_language(text: str) -> str:
    """Detect the primary language of the input text.

    Uses a combination of:
    1. Keyword matching (domain-specific terms)
    2. Unicode range detection (CJK characters)

    Args:
        text: The text to analyze.

    Returns:
        "zh" for Chinese, "en" for English (default).
    """
    if not text:
        return "en"

    # Count keyword matches
    text_lower = text.lower()
    zh_count = sum(1 for kw in _ZH_KEYWORDS if kw in text)
    en_count = sum(1 for kw in _EN_KEYWORDS if kw in text_lower)

    # Count CJK characters
    zh_char_count = sum(1 for ch in text if 0x4E00 <= ord(ch) <= 0x9FFF)
    total_alpha = sum(1 for ch in text if ch.isalpha())

    # Decision: keywords win, then character ratio
    if zh_count > en_count:
        return "zh"
    if en_count > zh_count:
        return "en"

    # Fallback to character ratio
    if total_alpha == 0:
        return "en"
    if zh_char_count / total_alpha > 0.3:
        return "zh"
    return "en"


def build_language_directive(text: str) -> str:
    """Build a language directive for the LLM.

    Args:
        text: The text to detect language from.

    Returns:
        A string instructing the LLM which language to use.
    """
    lang = detect_language(text)
    if lang == "zh":
        return "请使用中文回复（仅影响摘要/解释，不改变代码或 JSON 字段）。"
    return "Please respond in English (natural-language only; do not change code or JSON keys)."


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
    "detect_language",
    "build_language_directive",
    "prepare_code_context",
    "build_platform_info",
    "build_indicator_docs",
]
