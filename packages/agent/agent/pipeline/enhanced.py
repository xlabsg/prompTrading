"""
Enhanced pipeline with observability support.

Includes:
- Langfuse tracing
- Metrics collection
- Session tracking
"""

from __future__ import annotations

import os
from typing import Any

from agent.llm_openai_compat import (
    ChatCompletionRequest,
    ChatMessage,
    _strip_code_fences,
    chat_completion,
)
from agent.observability.metrics import SessionMetrics
from agent.observability.tracer import (
    LLMTracer,
    LLMCallMetrics,
    PromptTraceInfo,
)
from agent.pipeline.base import PipelineConfig, PipelineResult
from agent.prompt.builder import PromptBuilder


class EnhancedPipeline:
    """Enhanced pipeline with observability support.

    Tracks all LLM calls and provides detailed metrics.
    """

    def __init__(
        self,
        config: PipelineConfig,
        prompt_builder: PromptBuilder | None = None,
        session_metrics: SessionMetrics | None = None,
    ) -> None:
        """Initialize the enhanced pipeline.

        Args:
            config: Pipeline configuration.
            prompt_builder: Optional prompt builder.
            session_metrics: Optional session metrics for aggregation.
        """
        self.config = config
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.session_metrics = session_metrics

    def run(
        self,
        *,
        prompt: str,
        current_code: str,
        platform_capabilities: dict[str, Any],
        trace_name: str = "strategy_generation",
    ) -> PipelineResult:
        """Execute the pipeline with tracing.

        Args:
            prompt: The user's request prompt.
            current_code: Existing strategy code.
            platform_capabilities: Platform capabilities.
            trace_name: Name for the trace.

        Returns:
            PipelineResult with generated code, metadata, and metrics.
        """
        # 1. Create trace
        tracer = LLMTracer(
            trace_name=trace_name,
            trace_metadata={
                "strategy_id": os.getenv("STRATEGY_ID"),
                "prompt_length": len(prompt),
                "has_current_code": bool(current_code.strip()),
                "model": self.config.model,
            },
        )

        # 2. Create span
        span = tracer.create_span(
            name="generate_strategy_code",
            metadata={"llm_model": self.config.model},
        )

        try:
            # 3. Build prompt
            system, user, prompt_metadata = self.prompt_builder.build_strategy_generation(
                prompt=prompt,
                current_code=current_code,
                platform_capabilities=platform_capabilities,
            )

            # 4. Call LLM
            req = ChatCompletionRequest(
                api_key=self.config.api_key or "",
                base_url=self.config.base_url,
                model=self.config.model,
                messages=[
                    ChatMessage(role="system", content=system),
                    ChatMessage(role="user", content=user),
                ],
                temperature=self.config.temperature,
            )

            raw = chat_completion(req)
            code = _strip_code_fences(raw)

            # 5. Validate
            self._validate_code(code)

            # 6. Record metrics
            llm_metrics = span.log_llm_call(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.config.temperature,
                response=code,
                error=None,
                prompt_info=PromptTraceInfo(
                    template_name=prompt_metadata.get("template", ""),
                    template_version=prompt_metadata.get("version", ""),
                    language=prompt_metadata.get("language", "en"),
                    is_new_strategy=prompt_metadata.get("is_new_strategy", True),
                    code_length=prompt_metadata.get("code_length", 0),
                    estimated_tokens=0,
                ),
            )

            span.end()
            tracer.finish()

            # 7. Update session metrics
            if self.session_metrics:
                self.session_metrics.add_call(
                    llm_metrics,
                    prompt_version=prompt_metadata.get("version"),
                )

            return PipelineResult(
                code=code,
                metadata={
                    "prompt": prompt_metadata,
                    "llm": {
                        "model": self.config.model,
                        "temperature": self.config.temperature,
                        "provider": self.config.provider,
                    },
                    "trace_id": getattr(tracer.trace, "id", None)
                    if tracer.trace
                    else None,
                },
                metrics=llm_metrics,
            )

        except Exception as exc:
            # Record failure
            span.log_llm_call(
                model=self.config.model,
                messages=[],
                temperature=self.config.temperature,
                response="",
                error=str(exc),
                prompt_info=None,
            )
            span.end()
            raise

    def _validate_code(self, code: str) -> None:
        """Validate generated code.

        Args:
            code: The generated code.

        Raises:
            ValueError: If code is invalid.
        """
        import ast

        try:
            tree = ast.parse(code)
        except Exception as e:
            raise ValueError(f"generated_code_invalid_syntax: {e}") from e

        has_fn = any(
            isinstance(n, ast.FunctionDef) and n.name == "generate_signals"
            for n in tree.body
        )
        if not has_fn:
            raise ValueError("generated_code_missing_generate_signals")


__all__ = ["EnhancedPipeline"]
