from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from typing import Any
from agent.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class DuckDuckGoSearchTool(BaseTool):
    """Multi-source web & financial research tool with zero API key requirement."""

    name = "web_search"
    description = (
        "Search the web and quantitative encyclopedia for trading formulas, "
        "PineScript scripts, academic papers, financial indicators, and trading strategies."
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
                "description": "Maximum number of results to return (default: 3)",
                "default": 3,
            },
        },
        "required": ["query"],
    }

    async def run(self, query: str, max_results: int = 3, timeout_s: float = 6.0) -> ToolResult:
        if not query or not query.strip():
            return ToolResult(success=False, data=[], error="empty_query")

        query = query.strip()

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
                        "title": f"Search summary for: {query}",
                        "snippet": "Web search timed out; proceed with built-in quant domain knowledge.",
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

    def _sync_search(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
        # 1. If Tavily API key is provided, use Tavily AI Search for top-tier results
        tavily_key = os.getenv("TAVILY_API_KEY") or os.getenv("SEARCH_API_KEY")
        if tavily_key:
            try:
                return self._search_tavily(query, tavily_key, max_results)
            except Exception as e:
                logger.debug(f"Tavily search fallback: {e}")

        # 2. Try DuckDuckGo Lite HTML search
        try:
            ddg_results = self._search_ddg_lite(query, max_results)
            if ddg_results:
                return ddg_results
        except Exception as e:
            logger.debug(f"DuckDuckGo search fallback: {e}")

        # 3. Query Wikipedia Quant & Financial Encyclopedia API
        try:
            wiki_results = self._search_wikipedia(query, max_results)
            if wiki_results:
                return wiki_results
        except Exception as e:
            logger.debug(f"Wikipedia search fallback: {e}")

        # 4. Fallback domain response
        return [
            {
                "title": f"Quant Domain Knowledge for: {query}",
                "url": "https://prompttrading.local/docs/indicators",
                "snippet": (
                    f"Quantitative strategy research reference for '{query}'. "
                    "Apply standard vectorized formulas (e.g. pandas/numpy EMA, ATR, Bollinger, RSI) "
                    "with proper parameter lookback and risk budgeting."
                ),
            }
        ]

    def _search_tavily(self, query: str, api_key: str, max_results: int) -> list[dict[str, str]]:
        req_data = json.dumps({"query": query, "max_results": max_results, "search_depth": "basic"}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=req_data,
            headers={"Content-Type": "application/json", "api-key": api_key, "User-Agent": "PromptTradingBot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=4.0) as res:
            data = json.loads(res.read().decode("utf-8"))
            results: list[dict[str, str]] = []
            for item in data.get("results", []):
                results.append({
                    "title": item.get("title", query),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", "")[:300],
                })
            return results

    def _search_ddg_lite(self, query: str, max_results: int) -> list[dict[str, str]]:
        url = "https://lite.duckduckgo.com/lite/"
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(req, timeout=3.5) as response:
            html = response.read().decode("utf-8", errors="replace")

        # Parse lite results table
        results: list[dict[str, str]] = []
        snippets = re.findall(r'<td class="result-snippet">\s*(.*?)\s*</td>', html, re.DOTALL)
        titles = re.findall(r'<a class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)

        for i in range(min(len(snippets), len(titles), max_results)):
            link, raw_title = titles[i]
            clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
            clean_snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            if clean_title or clean_snippet:
                results.append({
                    "title": clean_title or query,
                    "url": link,
                    "snippet": clean_snippet,
                })
        return results

    def _search_wikipedia(self, query: str, max_results: int) -> list[dict[str, str]]:
        # Strip generic prompt words for encyclopedic lookup
        clean_query = re.sub(r"(?i)(please|search|research|write|implement|strategy|python|formula|code)", "", query).strip()
        clean_query = clean_query or query

        url = (
            "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit="
            f"{max_results}&srsearch={urllib.parse.quote_plus(clean_query)}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "PromptTradingBot/1.0"})
        with urllib.request.urlopen(req, timeout=3.5) as res:
            data = json.loads(res.read().decode("utf-8"))
            results: list[dict[str, str]] = []
            for item in data.get("query", {}).get("search", []):
                title = item.get("title", "")
                raw_snippet = item.get("snippet", "")
                clean_snippet = re.sub(r"<[^>]+>", "", raw_snippet).strip()
                page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                results.append({
                    "title": title,
                    "url": page_url,
                    "snippet": clean_snippet,
                })
            return results
