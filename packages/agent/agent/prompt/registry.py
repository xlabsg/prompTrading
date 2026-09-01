"""
Prompt registry for version management and A/B testing.

Provides:
- Central registration of all prompt templates
- Version-aware retrieval
- A/B testing support
- Fallback to default versions
"""

from __future__ import annotations

import hashlib
from typing import Any

from agent.prompt.base import Prompt, PromptVersion
from agent.prompt.templates import (
    CODE_REPAIR_VALIDATION,
    PLAN_DECISION,
    PLAN_GENERATION,
    PLAN_GENERATION_V1,
    SPEC_GENERATION,
    STRATEGY_GENERATION_NEW,
    STRATEGY_GENERATION_REFINE,
)


class PromptRegistry:
    """Central registry for prompt templates.

    Manages multiple versions of prompts and supports A/B testing.
    """

    def __init__(self) -> None:
        self._prompts: dict[str, dict[str, Prompt]] = {}
        # {name: {version: Prompt}}
        self._defaults: dict[str, str] = {}
        # {name: default_version}
        self._ab_tests: dict[str, list[str]] = {}
        # {test_name: [version_a, version_b]}

        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register all default prompts."""
        defaults = [
            STRATEGY_GENERATION_NEW,
            STRATEGY_GENERATION_REFINE,
            SPEC_GENERATION,
            PLAN_GENERATION,  # V2 - semantic operations (default)
            PLAN_GENERATION_V1,  # V1 - legacy exact_replace (available but not default)
            PLAN_DECISION,
            CODE_REPAIR_VALIDATION,
        ]

        for prompt in defaults:
            self.register(prompt)
            # Set V2 as default for plan_generation
            if prompt.metadata.name == "plan_generation":
                if prompt.metadata.version == PromptVersion.V2:
                    self.set_default(prompt.metadata.name, prompt.metadata.version)
            else:
                self.set_default(prompt.metadata.name, prompt.metadata.version)

    def register(self, prompt: Prompt) -> None:
        """Register a prompt template.

        Args:
            prompt: The Prompt instance to register.
        """
        name = prompt.metadata.name
        version = prompt.metadata.version.value

        if name not in self._prompts:
            self._prompts[name] = {}
        self._prompts[name][version] = prompt

    def set_default(self, name: str, version: PromptVersion) -> None:
        """Set the default version for a prompt.

        Args:
            name: The prompt name.
            version: The version to set as default.
        """
        self._defaults[name] = version.value

    def get(
        self,
        name: str,
        version: str | None = None,
    ) -> Prompt | None:
        """Get a prompt by name and optional version.

        Args:
            name: The prompt name.
            version: The version to retrieve. If None, uses the default.

        Returns:
            The Prompt instance, or None if not found.
        """
        if name not in self._prompts:
            return None

        if version is None:
            version = self._defaults.get(name, PromptVersion.V1.value)

        return self._prompts[name].get(version)

    def list_versions(self, name: str) -> list[str]:
        """List all available versions for a prompt.

        Args:
            name: The prompt name.

        Returns:
            List of version strings.
        """
        if name not in self._prompts:
            return []
        return list(self._prompts[name].keys())

    def setup_ab_test(
        self,
        test_name: str,
        version_a: str,
        version_b: str,
    ) -> None:
        """Configure an A/B test for a prompt.

        Args:
            test_name: Name of the prompt to A/B test.
            version_a: First variant version.
            version_b: Second variant version.
        """
        self._ab_tests[test_name] = [version_a, version_b]

    def get_ab_variant(
        self,
        test_name: str,
        user_id: str,
    ) -> Prompt | None:
        """Get an A/B test variant based on user ID hash.

        Args:
            test_name: Name of the configured A/B test.
            user_id: User ID for consistent hashing.

        Returns:
            The selected Prompt variant, or None if test not configured.
        """
        if test_name not in self._ab_tests:
            return None

        variants = self._ab_tests[test_name]
        hash_val = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
        variant = variants[hash_val % len(variants)]

        return self.get(test_name, variant)

    def list_prompts(self) -> dict[str, list[str]]:
        """List all registered prompts and their versions.

        Returns:
            Dict mapping prompt names to lists of versions.
        """
        return {
            name: list(versions.keys())
            for name, versions in self._prompts.items()
        }

    def get_metadata(
        self,
        name: str,
        version: str | None = None,
    ) -> dict[str, Any] | None:
        """Get metadata for a prompt without loading the full template.

        Args:
            name: The prompt name.
            version: The version. If None, uses default.

        Returns:
            Dict with metadata fields, or None if not found.
        """
        prompt = self.get(name, version)
        if not prompt:
            return None

        return {
            "name": prompt.metadata.name,
            "version": prompt.metadata.version.value,
            "description": prompt.metadata.description,
            "author": prompt.metadata.author,
            "tags": prompt.metadata.tags,
            "tokens_estimate": prompt.metadata.tokens_estimate,
        }


# Global singleton
_global_registry: PromptRegistry | None = None


def get_registry() -> PromptRegistry:
    """Get the global prompt registry singleton.

    Returns:
        The global PromptRegistry instance.
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = PromptRegistry()
    return _global_registry


__all__ = ["PromptRegistry", "get_registry"]
