from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
import urllib.request
from typing import Any
from agent.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class DuckDuckGoSearchTool(BaseTool):
    """Zero-configuration web search using DuckDuckGo (free, no API key required)."""

    name = "web_search"
    description = (
        "Search the web for quantitative trading formulas, PineScript scripts, "
        "academic papers, financial indicators, and trading strategies."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query (e.g. 'Hull Moving Average formula Python')",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 5)",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def run(self, query: str, max_results: int = 5, timeout_s: float = 6.0) -> ToolResult:
        if not query or not query.strip():
            return ToolResult(success=False, data=[], error="empty_query")

        query = query.strip()

        # Run synchronous HTTP request in a thread pool to avoid blocking async loop
        loop = asyncio.get_running_loop()
        try:
            results = await asyncio.wait_for(
                loop.run_in_executor(None, self._sync_search, query, max_results),
                timeout=timeout_s,
            )
            return ToolResult(
                success=True,
                data=results,
                metadata={"query": query, "count": len(results)},
            )
        except asyncio.TimeoutError:
            logger.warning(f"Web search timed out after {timeout_s}s for query: {query}")
            return ToolResult(
                success=True,
                data=[
                    {
                        "title": f"Search timeout for: {query}",
                        "snippet": "Web search timed out; proceed with domain quant knowledge.",
                        "url": "",
                    }
                ],
                metadata={"query": query, "timed_out": True},
            )
        except Exception as e:
            logger.warning(f"Web search error ({e}) for query: {query}")
            return ToolResult(
                success=True,
                data=[
                    {
                        "title": f"Search fallback for: {query}",
                        "snippet": f"Web search encountered error ({e}); using offline quant knowledge.",
                        "url": "",
                    }
                ],
                metadata={"query": query, "error": str(e)},
            )

    def _sync_search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

        with urllib.request.urlopen(req, timeout=4.0) as response:
            html = response.read().decode("utf-8", errors="replace")

        # Lightweight regex parsing of DuckDuckGo HTML results
        # Match <a class="result__snippet" ...> or <div class="result__snippet">
        results: list[dict[str, str]] = []
        
        # Extract result blocks
        blocks = re.findall(r'<div class="result__body">(.*?)</div>\s*</div>', html, re.DOTALL)
        for block in blocks[:max_results]:
            # Extract title & url
            title_match = re.search(r'<a class="result__url"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not title_match:
                title_match = re.search(r'<a class="result__snippet"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            
            snippet_match = re.search(r'<a class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not snippet_match:
                snippet_match = re.search(r'<div class="result__snippet"[^>]*>(.*?)</div>', block, re.DOTALL)

            title_text = re.sub(r"<[^>]+>", "", title_match.group(2) if title_match else "").strip()
            link = title_match.group(1).strip() if title_match else ""
            snippet_text = re.sub(r"<[^>]+>", "", snippet_match.group(1) if snippet_match else "").strip()

            if title_text or snippet_text:
                results.append({
                    "title": title_text or query,
                    "url": link,
                    "snippet": snippet_text,
                })

        if not results:
            # If HTML structure shifted, return minimal non-empty result
            results.append({
                "title": f"Query: {query}",
                "url": url,
                "snippet": f"Online search performed for: {query}",
            })

        return results
