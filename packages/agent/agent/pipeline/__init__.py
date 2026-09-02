"""
Pipeline module for strategy generation.

Provides:
- EnhancedPipeline: Pipeline with observability and metrics
- Common utilities for pipeline operations
"""

from agent.pipeline.base import (
    PipelineConfig,
    PipelineResult,
    extract_json_from_text,
)
from agent.pipeline.enhanced import EnhancedPipeline

__all__ = [
    # Base classes
    "PipelineConfig",
    "PipelineResult",
    # Pipelines
    "EnhancedPipeline",
    # Utilities
    "extract_json_from_text",
]
