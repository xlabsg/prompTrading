"""
Basic pipeline for strategy generation.

Simple pipeline without observability overhead.
Use for scenarios where minimal overhead is required.
"""

from __future__ import annotations

import os
from agent.llm_openai_compat import (
    ChatCompletionRequest,
    ChatMessage,
    _strip_code_fences,
    chat_completion,
)
from agent.pipeline.base import PipelineConfig, PipelineResult
from agent.prompt.builder import PromptBuilder


class BasicPipeline:
    """Basic pipeline for strategy generation.

    Uses the new prompt system but without observability overhead.
    """

    def __init__(
        self,
        config: PipelineConfig,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        """Initialize the pipeline.

        Args:
            config: Pipeline configuration.
            prompt_builder: Optional prompt builder (creates one if not provided).
        """
        self.config = config
        self.prompt_builder = prompt_builder or PromptBuilder()

    def run(
        self,
        *,
        prompt: str,
        current_code: str,
        platform_capabilities: dict[str, Any],
    ) -> PipelineResult:
        """Execute the pipeline.

        Args:
            prompt: The user's request prompt.
            current_code: Existing strategy code.
            platform_capabilities: Platform capabilities dictionary.

        Returns:
            PipelineResult with generated code and metadata.
        """
        # 1. Build prompt
        system, user, prompt_metadata = self.prompt_builder.build_strategy_generation(
            prompt=prompt,
            current_code=current_code,
            platform_capabilities=platform_capabilities,
        )

        # 2. Call LLM
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

        # Check if streaming is enabled
        stream_enabled = (os.getenv("LLM_STREAM", "").lower() not in ("0", "false", "no"))

        if stream_enabled:
            code = self._stream_completion(req)
        else:
            raw = chat_completion(req)
            code = _strip_code_fences(raw)

        # 3. Validate
        self._validate_code(code)

        # 4. Build result
        return PipelineResult(
            code=code,
            metadata={
                "prompt": prompt_metadata,
                "llm": {
                    "model": self.config.model,
                    "temperature": self.config.temperature,
                    "provider": self.config.provider,
                },
            },
        )

    def _stream_completion(self, req: ChatCompletionRequest) -> str:
        """Handle streaming completion.

        Args:
            req: The completion request.

        Returns:
            The stripped code from the stream.
        """
        from agent.llm_openai_compat import chat_completion_stream

        print("[agent] llm_stream=true (printing code as it is generated)")
        print("=== LLM_CODE_BEGIN ===")

        full = ""
        line_buf = ""
        code_lines: list[str] = []
        started = False
        in_fence = False

        def looks_like_code_line(line: str) -> bool:
            s = line.lstrip()
            return s.startswith(("import ", "from ", "def ", "class ", "#", '"""', "'''"))

        for delta in chat_completion_stream(req):
            full += delta
            line_buf += delta

            while "\n" in line_buf:
                line, line_buf = line_buf.split("\n", 1)
                if line.strip().startswith("```"):
                    in_fence = not in_fence
                    continue
                if not started and not in_fence:
                    if not line.strip():
                        continue
                    if not looks_like_code_line(line):
                        continue
                    started = True

                if in_fence:
                    started = True

                if started:
                    print(line)
                    code_lines.append(line)

            if len(line_buf) >= 500:
                chunk = line_buf
                line_buf = ""
                if started:
                    print(chunk)
                    code_lines.append(chunk)

        if line_buf and started:
            if not line_buf.strip().startswith("```"):
                print(line_buf)
                code_lines.append(line_buf)

        print("=== LLM_CODE_END ===")
        code = "\n".join(code_lines).strip() or full.strip()
        return _strip_code_fences(code)

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


__all__ = ["BasicPipeline"]
