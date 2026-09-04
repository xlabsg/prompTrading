"""
LLM call tracer for observability.

Provides:
- Trace creation for grouping related operations
- Span creation for individual LLM calls
- Automatic metric collection
- Langfuse integration
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from agent.observability.langfuse_client import get_langfuse
from agent.observability.metrics import LLMCallMetrics, calculate_cost


@dataclass
class PromptTraceInfo:
    """Information about a prompt for tracing.

    Attributes:
        template_name: Name of the prompt template used.
        template_version: Version of the prompt template.
        language: Detected language of the prompt.
        is_new_strategy: Whether this is a new strategy or a refinement.
        code_length: Length of the code context.
        estimated_tokens: Estimated token count.
    """

    template_name: str
    template_version: str
    language: str
    is_new_strategy: bool
    code_length: int
    estimated_tokens: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "template_name": self.template_name,
            "template_version": self.template_version,
            "language": self.language,
            "is_new_strategy": self.is_new_strategy,
            "code_length": self.code_length,
            "estimated_tokens": self.estimated_tokens,
        }


class LLMTracer:
    """Tracer for LLM operations.

    Creates a trace that groups related spans (LLM calls).
    """

    def __init__(
        self,
        trace_name: str,
        trace_metadata: dict[str, Any],
    ) -> None:
        """Initialize a new trace.

        Args:
            trace_name: Name for the trace.
            trace_metadata: Metadata to attach to the trace.
        """
        self.langfuse = get_langfuse()
        self.trace = None

        if self.langfuse.enabled:
            self.trace = self.langfuse.create_trace(
                name=trace_name,
                metadata=trace_metadata,
            )

    def create_span(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> LLMSpan:
        """Create a new span within this trace.

        Args:
            name: Name for the span.
            metadata: Optional metadata for the span.

        Returns:
            An LLMSpan instance.
        """
        return LLMSpan(
            tracer=self,
            name=name,
            metadata=metadata or {},
        )

    def finish(self) -> None:
        """Finish the trace.

        Langfuse handles this automatically, but this method
        exists for explicit cleanup if needed.
        """
        pass


@dataclass
class LLMSpan:
    """Span representing a single LLM call.

    Automatically records:
    - Input/output
    - Token usage
    - Latency
    - Cost
    """

    tracer: LLMTracer
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    _span: Any = field(default=None, init=False)
    _start_time: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        """Initialize the span after creation."""
        if self.tracer.trace:
            self._span = self.tracer.trace.span(name=self.name)
            self._span.update(metadata=self.metadata)
        self._start_time = time.time()

    def log_llm_call(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        response: str,
        usage: dict[str, int] | None = None,
        prompt_info: PromptTraceInfo | None = None,
        error: str | None = None,
    ) -> LLMCallMetrics:
        """Record an LLM call.

        Args:
            model: Model name.
            messages: List of message dicts with 'role' and 'content'.
            temperature: Temperature parameter.
            response: The response text.
            usage: Token usage dict with 'prompt_tokens', 'completion_tokens', 'total_tokens'.
            prompt_info: Optional prompt trace information.
            error: Error message if the call failed.

        Returns:
            LLMCallMetrics with recorded data.
        """
        # Calculate latency
        latency_ms = (time.time() - self._start_time) * 1000

        # Estimate tokens if not provided
        if usage is None:
            usage = self._estimate_tokens(messages, response)

        # Calculate cost
        cost = calculate_cost(model, usage)

        metrics = LLMCallMetrics(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            cost_usd=cost,
            latency_ms=latency_ms,
            model=model,
            temperature=temperature,
            success=(error is None),
            error=error,
        )

        if self._span:
            # Build input dict
            input_dict = {
                "model": model,
                "temperature": temperature,
                "messages": messages,
            }
            if prompt_info:
                input_dict["prompt"] = prompt_info.to_dict()

            # End the span with data
            self._span.end(
                input=input_dict,
                output=response,
                metadata={
                    **self.metadata,
                    "cost_usd": cost,
                    "latency_ms": latency_ms,
                },
                usage=usage,
            )

        return metrics

    def end(self) -> None:
        """End the span."""
        if self._span:
            self._span.end()

    def _estimate_tokens(
        self,
        messages: list[dict[str, str]],
        response: str,
    ) -> dict[str, int]:
        """Estimate token count.

        This is a rough estimate. For accurate counts, use tiktoken.

        Args:
            messages: List of messages.
            response: Response text.

        Returns:
            Dict with prompt_tokens, completion_tokens, total_tokens.
        """
        # Simple estimate: ~3 characters per token
        prompt_text = "\n".join(m.get("content", "") for m in messages)
        prompt_tokens = len(prompt_text) // 3
        completion_tokens = len(response) // 3

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }


__all__ = ["LLMTracer", "LLMSpan", "LLMCallMetrics", "PromptTraceInfo"]
