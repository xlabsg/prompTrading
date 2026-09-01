"""
Prompt base classes and version management.

Design principles:
- Prompt as a first-class citizen with metadata
- Support for template variable interpolation
- Support for composition (combining prompt fragments)
- Version tracking for A/B testing and rollbacks
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PromptVersion(str, Enum):
    """Prompt version identifiers."""

    V1 = "v1.0"
    V2 = "v2.0"
    EXPERIMENTAL = "experimental"


@dataclass(frozen=True)
class PromptMetadata:
    """Metadata associated with a prompt template."""

    name: str
    """Unique identifier for this prompt template."""

    version: PromptVersion
    """Version of this prompt template."""

    description: str
    """Human-readable description of what this prompt does."""

    author: str = "stratsmith"
    """Author or creator of the prompt."""

    tags: list[str] = field(default_factory=list)
    """Tags for categorization and filtering (e.g., ['generation', 'backtest'])."""

    tokens_estimate: int = 0
    """Estimated token count for this prompt (for budgeting)."""


@dataclass
class Prompt:
    """Unified prompt template class.

    A Prompt encapsulates a system and user template that can be
    instantiated with variables to produce final messages for LLM calls.

    Example:
        prompt = Prompt(
            metadata=PromptMetadata(
                name="my_prompt",
                version=PromptVersion.V1,
                description="Does something",
            ),
            system_template="You are a {role}.",
            user_template="Task: {task}",
        )
        system, user = prompt.build(role="expert", task="analyze this")
    """

    metadata: PromptMetadata
    """Metadata about this prompt."""

    system_template: str
    """Template for the system message."""

    user_template: str
    """Template for the user message."""

    variables: dict[str, Any] = field(default_factory=dict)
    """Default variables that can be overridden in build()."""

    def build(self, **kwargs: Any) -> tuple[str, str]:
        """Build the final system and user messages.

        Args:
            **kwargs: Variables to interpolate into templates.
                      Merged with self.variables, with kwargs taking precedence.

        Returns:
            A tuple of (system_message, user_message).
        """
        merged_vars = {**self.variables, **kwargs}
        try:
            system = self.system_template.format(**merged_vars)
            user = self.user_template.format(**merged_vars)
        except KeyError as exc:
            missing = exc.args[0] if exc.args else str(exc)
            raise ValueError(
                f"Prompt '{self.metadata.name}' missing required variable: {missing}"
            ) from exc
        return system, user

    def with_vars(self, **kwargs: Any) -> Prompt:
        """Create a new Prompt with additional default variables.

        Args:
            **kwargs: Variables to add to the default variables.

        Returns:
            A new Prompt instance with merged variables.
        """
        return Prompt(
            metadata=self.metadata,
            system_template=self.system_template,
            user_template=self.user_template,
            variables={**self.variables, **kwargs},
        )

    def estimate_tokens(self, **kwargs: Any) -> int:
        """Estimate the token count of the built prompt.

        This is a rough estimate using character count / 3.
        For production, consider using tiktoken for accurate counts.

        Args:
            **kwargs: Variables to interpolate into templates.

        Returns:
            Estimated token count.
        """
        system, user = self.build(**kwargs)
        # Rough estimate: ~3 characters per token
        return (len(system) + len(user)) // 3


__all__ = ["Prompt", "PromptMetadata", "PromptVersion"]
