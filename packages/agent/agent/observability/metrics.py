"""
Metrics collection and reporting for LLM calls.

Provides:
- Token usage tracking
- Cost calculation
- Session-level aggregation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Model pricing (2025, USD per 1M tokens)
# Prices are approximate and may change over time
MODEL_PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-coder": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.20},
}


@dataclass
class LLMCallMetrics:
    """Metrics for a single LLM call.

    Attributes:
        prompt_tokens: Number of tokens in the prompt.
        completion_tokens: Number of tokens in the response.
        total_tokens: Total tokens used.
        cost_usd: Estimated cost in USD.
        latency_ms: Request latency in milliseconds.
        model: Model name.
        temperature: Temperature parameter used.
        success: Whether the call succeeded.
        error: Error message if failed.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    model: str = ""
    temperature: float = 0.0
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of metrics.
        """
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": round(self.latency_ms, 2),
            "model": self.model,
            "temperature": self.temperature,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class SessionMetrics:
    """Metrics aggregated across a session.

    A session typically corresponds to one strategy generation request.

    Attributes:
        session_id: Session identifier.
        total_llm_calls: Total number of LLM calls made.
        total_tokens: Total tokens used across all calls.
        total_cost_usd: Total estimated cost in USD.
        total_latency_ms: Total latency across all calls.
        success_count: Number of successful calls.
        failure_count: Number of failed calls.
        by_prompt_version: Metrics grouped by prompt version.
        by_model: Metrics grouped by model name.
    """

    session_id: str
    total_llm_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    by_prompt_version: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add_call(
        self,
        metrics: LLMCallMetrics,
        prompt_version: str | None = None,
    ) -> None:
        """Add metrics from a single LLM call.

        Args:
            metrics: The call metrics to add.
            prompt_version: Optional prompt version for grouping.
        """
        self.total_llm_calls += 1
        self.total_tokens += metrics.total_tokens
        self.total_cost_usd += metrics.cost_usd
        self.total_latency_ms += metrics.latency_ms

        if metrics.success:
            self.success_count += 1
        else:
            self.failure_count += 1

        # Group by prompt version
        if prompt_version:
            if prompt_version not in self.by_prompt_version:
                self.by_prompt_version[prompt_version] = {
                    "calls": 0,
                    "tokens": 0,
                    "cost_usd": 0.0,
                    "success_rate": 0.0,
                }

            stats = self.by_prompt_version[prompt_version]
            stats["calls"] += 1
            stats["tokens"] += metrics.total_tokens
            stats["cost_usd"] += metrics.cost_usd
            stats["success_rate"] = (
                (stats["calls"] - (0 if metrics.success else 1)) / stats["calls"]
                if stats["calls"] > 0
                else 0.0
            )

        # Group by model
        model = metrics.model or "unknown"
        if model not in self.by_model:
            self.by_model[model] = {
                "calls": 0,
                "tokens": 0,
                "cost_usd": 0.0,
            }

        model_stats = self.by_model[model]
        model_stats["calls"] += 1
        model_stats["tokens"] += metrics.total_tokens
        model_stats["cost_usd"] += metrics.cost_usd

    def summary(self) -> dict[str, Any]:
        """Generate a summary of session metrics.

        Returns:
            Dictionary with aggregated metrics.
        """
        return {
            "session_id": self.session_id,
            "total_llm_calls": self.total_llm_calls,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "avg_latency_ms": round(
                self.total_latency_ms / max(self.total_llm_calls, 1),
                2,
            ),
            "success_rate": round(
                self.success_count / max(self.total_llm_calls, 1),
                2,
            ),
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "by_prompt_version": {
                k: {
                    **v,
                    "cost_usd": round(v["cost_usd"], 4),
                    "success_rate": round(v["success_rate"], 2),
                }
                for k, v in self.by_prompt_version.items()
            },
            "by_model": {
                k: {
                    **v,
                    "cost_usd": round(v["cost_usd"], 4),
                }
                for k, v in self.by_model.items()
            },
        }


def calculate_cost(
    model: str,
    usage: dict[str, int],
) -> float:
    """Calculate the cost of an LLM call.

    Args:
        model: Model name (e.g., "gpt-4o", "deepseek-chat").
        usage: Dictionary with "prompt_tokens" and "completion_tokens" keys.

    Returns:
        Estimated cost in USD.
    """
    pricing = MODEL_PRICING.get(model, {})
    if not pricing:
        return 0.0

    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    input_cost = (prompt_tokens / 1_000_000) * pricing.get("input", 0)
    output_cost = (completion_tokens / 1_000_000) * pricing.get("output", 0)

    return input_cost + output_cost


def estimate_tokens(text: str) -> int:
    """Estimate token count from text.

    This is a rough estimate. For accurate counts, use tiktoken.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count (~3 characters per token).
    """
    return len(text) // 3


__all__ = [
    "MODEL_PRICING",
    "LLMCallMetrics",
    "SessionMetrics",
    "calculate_cost",
    "estimate_tokens",
]
