"""
Pipeline module for strategy generation.

Provides:
- BasicPipeline: Simple LLM-based code generation
- EnhancedPipeline: Pipeline with observability and metrics
- Common utilities for pipeline operations
"""

from agent.pipeline.base import (
    PipelineConfig,
    PipelineResult,
    extract_json_from_text,
)
from agent.pipeline.basic import BasicPipeline
from agent.pipeline.enhanced import EnhancedPipeline

__all__ = [
    # Base classes
    "PipelineConfig",
    "PipelineResult",
    # Pipelines
    "BasicPipeline",
    "EnhancedPipeline",
    # Utilities
    "extract_json_from_text",
]
