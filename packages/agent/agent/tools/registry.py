from __future__ import annotations

import logging
from typing import Any, Optional
from agent.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for managing and retrieving agent tools."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        if not tool.name:
            raise ValueError("Tool must have a valid non-empty name")
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def require(self, name: str) -> BaseTool:
        """Get a tool by name or raise KeyError."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered. Available tools: {list(self._tools.keys())}")
        return self._tools[name]

    def list_tools(self) -> list[dict[str, Any]]:
        """List metadata for all registered tools."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters_schema": t.parameters_schema,
            }
            for t in self._tools.values()
        ]

    def has(self, name: str) -> bool:
        return name in self._tools


_GLOBAL_REGISTRY = ToolRegistry()


def get_global_registry() -> ToolRegistry:
    return _GLOBAL_REGISTRY
