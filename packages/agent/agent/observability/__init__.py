"""
Observability module for LLM call tracking and metrics.

Provides Langfuse integration for:
- Tracing LLM calls
- Recording token usage and costs
- Session-level metrics aggregation
"""

from agent.observability.langfuse_client import (
    LangfuseClient,
    LangfuseConfig,
    get_langfuse,
)
from agent.observability.metrics import (
    MODEL_PRICING,
    SessionMetrics,
    calculate_cost,
)
from agent.observability.tracer import (
    LLMSpan,
    LLMTracer,
    LLMCallMetrics,
    PromptTraceInfo,
)

__all__ = [
    # Langfuse client
    "LangfuseClient",
    "LangfuseConfig",
    "get_langfuse",
    # Metrics
    "SessionMetrics",
    "calculate_cost",
    "MODEL_PRICING",
    # Tracer
    "LLMTracer",
    "LLMSpan",
    "LLMCallMetrics",
    "PromptTraceInfo",
]
