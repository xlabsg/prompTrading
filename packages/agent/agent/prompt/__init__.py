"""
Prompt system for agent LLM interactions.

This module provides a unified way to manage, version, and build prompts
for LLM-based strategy generation.

Main components:
- Prompt: Base class for prompt templates with versioning
- PromptBuilder: Build prompts with context injection
- PromptRegistry: Register and retrieve prompts by name/version
- Context utilities: Intelligent code truncation, language detection
- Code slice: AST-based code extraction and analysis
- Indicator docs: Smart indicator documentation retrieval
"""

from agent.prompt.base import Prompt, PromptMetadata, PromptVersion
from agent.prompt.builder import PromptBuilder
from agent.prompt.code_slice import (
    estimate_tokens,
    extract_class_signatures,
    extract_function_body,
    extract_function_signatures,
    extract_logic_blocks,
    extract_relevant_context,
    find_anchor_position,
    find_block_with_anchor,
    prepare_code_summary,
    should_slice_function,
)
from agent.prompt.context import (
    build_language_directive,
    build_platform_info,
    detect_language,
    prepare_code_context,
)
from agent.prompt.indicator_docs import (
    build_indicator_docs,
    get_all_indicator_names,
    get_indicator_info,
)
from agent.prompt.registry import PromptRegistry, get_registry

__all__ = [
    # Base classes
    "Prompt",
    "PromptMetadata",
    "PromptVersion",
    # Builder
    "PromptBuilder",
    # Context
    "detect_language",
    "build_language_directive",
    "build_platform_info",
    "prepare_code_context",
    # Code slice
    "estimate_tokens",
    "extract_class_signatures",
    "extract_function_body",
    "extract_function_signatures",
    "extract_logic_blocks",
    "extract_relevant_context",
    "find_anchor_position",
    "find_block_with_anchor",
    "prepare_code_summary",
    "should_slice_function",
    # Indicator docs
    "build_indicator_docs",
    "get_all_indicator_names",
    "get_indicator_info",
    # Registry
    "PromptRegistry",
    "get_registry",
]
