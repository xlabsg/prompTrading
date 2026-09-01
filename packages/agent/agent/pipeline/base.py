"""
Base classes and utilities for pipeline operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineConfig:
    """Configuration for pipeline execution.

    Attributes:
        api_key: LLM provider API key.
        base_url: LLM provider base URL.
        model: Model name.
        temperature: Sampling temperature.
        provider: Provider name ("openai", "deepseek", etc.).
    """

    api_key: str | None
    base_url: str
    model: str
    temperature: float
    provider: str = "openai"


@dataclass
class PipelineResult:
    """Result from a pipeline execution.

    Attributes:
        code: The generated/modified strategy code.
        metadata: Additional metadata about the generation.
        metrics: LLM call metrics if available.
    """

    code: str
    metadata: dict[str, Any] = field(default_factory=dict)
    metrics: Any = None  # LLMCallMetrics | None


def extract_json_from_text(text: str) -> str:
    """Extract JSON object from text.

    Handles:
    - Plain JSON
    - Markdown code fences
    - JSON preceded/followed by text

    Args:
        text: Text containing JSON.

    Returns:
        Extracted JSON string, or original text if no JSON found.
    """
    # Try to find JSON in markdown code fences
    if "```json" in text:
        start = text.find("```json")
        after_fence = text[start + 7:]
        end = after_fence.find("```")
        if end != -1:
            return after_fence[:end].strip()

    if "```" in text:
        start = text.find("```")
        after_fence = text[start + 3:]
        end = after_fence.find("```")
        if end != -1:
            candidate = after_fence[:end].strip()
            if candidate.startswith("{"):
                return candidate

    # Find outermost braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]

    return text


__all__ = ["PipelineConfig", "PipelineResult", "extract_json_from_text"]
