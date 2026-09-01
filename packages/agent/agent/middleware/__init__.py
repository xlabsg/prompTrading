"""
Middleware for reducing redundant LLM calls.

Provides rule-based decision making to replace simple LLM calls:
- Plan generation decision
- Smoke settings decision
"""

import re
from typing import Any


class LLMMiddleware:
    """Middleware for rule-based LLM call reduction.

    Uses heuristics and patterns to make decisions that would
    otherwise require LLM calls.
    """

    # Patterns for scenarios that don't need a plan
    _NO_PLAN_PATTERNS = [
        # Simple parameter changes
        r"调整.*参数为?\s*\d+",
        r"change.*param(to)?\s*\d+",
        r"把.*改成?\s*\d+",
        r"set.*param(to)?\s*\d+",
        r"参数.*改为?\s*\d+",
        # Very short prompts
        r"^.{{1,30}}$",
    ]

    _COMPILED_NO_PLAN = [re.compile(p, re.IGNORECASE) for p in _NO_PLAN_PATTERNS]

    @classmethod
    def should_generate_plan(
        cls,
        prompt: str,
        current_code: str,
    ) -> tuple[bool, str | None]:
        """Decide whether to generate a structured plan.

        Uses rules instead of LLM for common scenarios.

        Rules:
        1. Empty code → no plan needed (will generate full strategy)
        2. Simple parameter change → no plan needed
        3. Short prompt + long code → likely small edit, no plan needed
        4. Otherwise → generate plan

        Args:
            prompt: The user's request prompt.
            current_code: Existing strategy code.

        Returns:
            A tuple of (should_plan, reason).
            - should_plan: True if plan generation is recommended
            - reason: String explaining the decision, or None
        """
        # Rule 1: Empty code doesn't need a plan
        if not current_code.strip():
            return False, "empty_code"

        # Rule 2: Check for simple parameter change patterns
        for pattern in cls._COMPILED_NO_PLAN:
            if pattern.search(prompt):
                return False, "simple_param_change"

        # Rule 3: Short prompt with long code = small edit
        prompt_len = len(prompt.strip())
        code_len = len(current_code)
        if prompt_len < 100 and code_len > 2000:
            return False, "short_prompt_long_code"

        # Rule 4: Explicit request for simple change
        simple_keywords = [
            "简单",
            "simple",
            "minor",
            "小改",
            "微调",
        ]
        prompt_lower = prompt.lower()
        for kw in simple_keywords:
            if kw in prompt_lower:
                return False, "explicit_simple_change"

        # Default: generate plan for complex scenarios
        return True, None

    @classmethod
    def decide_smoke_settings(
        cls,
        prompt: str,
        current_code: str,
    ) -> dict[str, Any]:
        """Decide smoke test settings using rules.

        Instead of calling LLM, uses heuristics:
        - Always run smoke test for new code
        - Use default n_bars and interval
        - Max attempts based on code complexity

        Args:
            prompt: The user's request prompt.
            current_code: The generated/modified code.

        Returns:
            Dictionary with smoke test settings.
        """
        # Default settings
        settings = {
            "run": True,
            "max_attempts": 2,
            "n_bars": 200,
            "interval": "1h",
        }

        # Adjust based on code complexity (rough heuristic)
        if current_code:
            line_count = len(current_code.splitlines())
            if line_count > 100:
                settings["max_attempts"] = 3
            elif line_count < 30:
                settings["max_attempts"] = 1

        # Check for keywords suggesting more rigorous testing
        rigorous_keywords = [
            "回测",
            "backtest",
            "验证",
            "validate",
            "确认",
            "ensure",
        ]
        if any(kw in prompt.lower() for kw in rigorous_keywords):
            settings["max_attempts"] = max(settings["max_attempts"], 3)
            settings["n_bars"] = 500

        return settings

    @classmethod
    def detect_language(cls, text: str) -> str:
        """Quick language detection using patterns.

        This is a fast path for language detection when we don't
        need the full accuracy of the context module.

        Args:
            text: The text to analyze.

        Returns:
            "zh" for Chinese, "en" for English.
        """
        if not text:
            return "en"

        # Count CJK characters
        zh_chars = sum(1 for ch in text if 0x4E00 <= ord(ch) <= 0x9FFF)
        total_chars = sum(1 for ch in text if ch.isalpha())

        if total_chars == 0:
            return "en"

        # If more than 30% CJK, assume Chinese
        if zh_chars / total_chars > 0.3:
            return "zh"

        return "en"


__all__ = ["LLMMiddleware"]
