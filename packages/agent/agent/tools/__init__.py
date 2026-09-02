from __future__ import annotations

from agent.tools.base import BaseTool, ToolResult, tool
from agent.tools.registry import ToolRegistry, get_global_registry
from agent.tools.web_search import DuckDuckGoSearchTool
from agent.tools.market_analyzer import MarketAnalyzerTool
from agent.tools.ast_auditor import ASTAuditorTool


def init_default_tools(registry: ToolRegistry | None = None) -> ToolRegistry:
    reg = registry or get_global_registry()
    if not reg.has("web_search"):
        reg.register(DuckDuckGoSearchTool())
    if not reg.has("market_analyzer"):
        reg.register(MarketAnalyzerTool())
    if not reg.has("ast_auditor"):
        reg.register(ASTAuditorTool())
    return reg


__all__ = [
    "BaseTool",
    "ToolResult",
    "tool",
    "ToolRegistry",
    "get_global_registry",
    "init_default_tools",
    "DuckDuckGoSearchTool",
    "MarketAnalyzerTool",
    "ASTAuditorTool",
]
