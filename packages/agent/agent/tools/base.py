from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ToolResult:
    """Standard execution result from a tool."""
    success: bool
    data: Any
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
        }


class BaseTool(ABC):
    """Abstract base class for all agent tools."""

    name: str
    description: str
    parameters_schema: dict[str, Any]

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult:
        """Execute the tool asynchronously and return a ToolResult."""
        pass

    def __call__(self, **kwargs: Any) -> Any:
        return self.run(**kwargs)


def tool(name: str, description: str, parameters_schema: dict[str, Any] | None = None):
    """Decorator to convert an async function into a BaseTool instance."""
    def decorator(fn: Callable[..., Any]) -> BaseTool:
        schema = parameters_schema or {}

        class DecoratedTool(BaseTool):
            def __init__(self):
                self.name = name
                self.description = description
                self.parameters_schema = schema

            async def run(self, **kwargs: Any) -> ToolResult:
                try:
                    if inspect.iscoroutinefunction(fn):
                        res = await fn(**kwargs)
                    else:
                        res = fn(**kwargs)
                    if isinstance(res, ToolResult):
                        return res
                    return ToolResult(success=True, data=res)
                except Exception as e:
                    return ToolResult(success=False, data=None, error=str(e))

        return DecoratedTool()

    return decorator
