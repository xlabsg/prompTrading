"""
Prompt builder for constructing prompts with context injection.

The PromptBuilder is the main entry point for building prompts.
It handles:
- Template selection based on context
- Variable interpolation
- Language detection
- Code context preparation
- AST-based code slicing
"""

from __future__ import annotations

from typing import Any

from agent.prompt.base import Prompt
from agent.prompt.code_slice import (
    extract_function_signatures,
    prepare_code_summary,
)
from agent.prompt.context import (
    build_platform_info,
    prepare_code_context,
)
from agent.prompt.registry import get_registry
from agent.prompt.templates import (
    STRATEGY_GENERATION_NEW,
    STRATEGY_GENERATION_REFINE,
)


class PromptBuilder:
    """Unified prompt construction entry point.

    The PromptBuilder handles the creation of prompts for various scenarios,
    automatically selecting the appropriate template and injecting context.
    """

    def __init__(
        self,
        default_language: str = "en",
        max_code_length: int = 8000,
    ):
        """Initialize the PromptBuilder.

        Args:
            default_language: Default language for responses ("en" or "zh").
            max_code_length: Maximum length of code context in characters.
        """
        self.default_language = default_language
        self.max_code_length = max_code_length
        self._registry = get_registry()

    def build_strategy_generation(
        self,
        *,
        prompt: str,
        current_code: str = "",
        platform_capabilities: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        """Build a prompt for strategy generation.

        Automatically selects the new strategy or refine template based on
        whether current_code is empty.

        Args:
            prompt: The user's request prompt.
            current_code: Existing strategy code (empty for new strategies).
            platform_capabilities: Dictionary of platform capabilities.

        Returns:
            A tuple of (system_message, user_message, metadata).
            Metadata includes template name, version, etc.
        """
        # 1. Prepare code context
        code_context = prepare_code_context(
            current_code,
            max_length=self.max_code_length,
            include_imports=True,
            include_function_signatures=True,
        )

        # 2. Prepare platform info (smart indicator selection based on user request)
        platform_info = build_platform_info(platform_capabilities, user_prompt=prompt)

        # 3. Select template
        is_new_strategy = not current_code.strip()
        template = STRATEGY_GENERATION_NEW if is_new_strategy else STRATEGY_GENERATION_REFINE

        # 4. Build
        system, user = template.build(
            prompt=prompt,
            current_code=code_context,
            platform_info=platform_info,
        )

        metadata = {
            "template": template.metadata.name,
            "version": template.metadata.version.value,
            "is_new_strategy": is_new_strategy,
            "code_length": len(current_code),
            "code_context_length": len(code_context),
        }

        return system, user, metadata

    def build_spec_generation(
        self,
        *,
        prompt: str,
        current_code: str = "",
    ) -> tuple[str, str, dict[str, Any]]:
        """Build a prompt for spec generation.

        Args:
            prompt: The user's request prompt.
            current_code: Existing strategy code.

        Returns:
            A tuple of (system_message, user_message, metadata).
        """
        code_context = prepare_code_context(
            current_code,
            max_length=2000,  # Spec needs less context
            include_imports=False,
        )

        template = self._registry.get("spec_generation")
        if not template:
            raise RuntimeError("spec_generation template not found in registry")

        system, user = template.build(
            prompt=prompt,
            current_code=code_context,
        )

        metadata = {
            "template": template.metadata.name,
            "version": template.metadata.version.value,
        }

        return system, user, metadata

    def build_plan_generation(
        self,
        *,
        prompt: str,
        current_code: str = "",
        protocol: dict[str, Any],
        platform_capabilities: dict[str, Any],
        params_schema: dict[str, Any] | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        """Build a prompt for plan generation.

        Uses AST-based code analysis to provide function signatures
        instead of truncated code. This allows the LLM to select
        which function to modify without seeing the entire codebase.

        Args:
            prompt: The user's request prompt.
            current_code: Existing strategy code.
            protocol: Strategy protocol dictionary.
            platform_capabilities: Platform capabilities.
            params_schema: Parameter schema.

        Returns:
            A tuple of (system_message, user_message, metadata).
        """
        # Extract function signatures using AST
        function_signatures = extract_function_signatures(current_code)

        # Format function signatures for the prompt
        if function_signatures:
            sig_lines = []
            for sig in function_signatures:
                sig_lines.append(
                    f"  - {sig['name']}: {sig['signature']} "
                    f"(line {sig['line_start']}, {sig['length_lines']} lines, "
                    f"~{sig['estimated_tokens']} tokens)"
                )
            function_signatures_str = "\n".join(sig_lines)
        else:
            function_signatures_str = "  # No existing functions - this is a new strategy"

        platform_info = build_platform_info(platform_capabilities)

        template = self._registry.get("plan_generation")
        if not template:
            raise RuntimeError("plan_generation template not found in registry")

        import json

        system, user = template.build(
            prompt=prompt,
            function_signatures=function_signatures_str,
            protocol=json.dumps(protocol, ensure_ascii=False),
            platform_info=platform_info,
            params_schema=json.dumps(params_schema or {}, ensure_ascii=False),
        )

        metadata = {
            "template": template.metadata.name,
            "version": template.metadata.version.value,
            "function_count": len(function_signatures),
        }

        return system, user, metadata

    def build_code_repair(
        self,
        *,
        prompt: str,
        code: str,
        validation: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        """Build a prompt for code repair based on validation failure.

        Args:
            prompt: The original user request.
            code: The code that failed validation.
            validation: The validation result dictionary.

        Returns:
            A tuple of (system_message, user_message, metadata).
        """
        import json

        validation_str = json.dumps(
            validation,
            ensure_ascii=False,
            indent=2,
        )[:8000]  # Limit validation output size

        template = self._registry.get("code_repair_validation")
        if not template:
            raise RuntimeError("code_repair_validation template not found in registry")

        system, user = template.build(
            prompt=prompt,
            code=code,
            validation=validation_str,
        )

        metadata = {
            "template": template.metadata.name,
            "version": template.metadata.version.value,
        }

        return system, user, metadata

    def build_plan_decision(
        self,
        *,
        prompt: str,
        current_code: str = "",
    ) -> tuple[str, str, dict[str, Any]]:
        """Build a prompt for deciding whether to generate a plan.

        Args:
            prompt: The user's request prompt.
            current_code: Existing strategy code.

        Returns:
            A tuple of (system_message, user_message, metadata).
        """
        code_preview = current_code[:1200] if current_code else "# Empty"

        template = self._registry.get("plan_decision")
        if not template:
            raise RuntimeError("plan_decision template not found in registry")

        system, user = template.build(
            prompt=prompt,
            current_code=code_preview,
        )

        metadata = {
            "template": template.metadata.name,
            "version": template.metadata.version.value,
        }

        return system, user, metadata


__all__ = ["PromptBuilder"]
