from __future__ import annotations

import logging
from typing import Any

from agent.dag.context import DAGContext
from agent.dag.engine import DAG, DAGNode
from agent.tools import init_default_tools

logger = logging.getLogger(__name__)

# Heuristic keywords (bilingual) that signal an exploratory / deep research prompt
_RESEARCH_KEYWORDS = frozenset({
    # English
    "search", "research", "paper", "arxiv", "find", "explore", "latest",
    "hull", "supertrend", "vwap", "funding", "arbitrage", "pinescript",
    "tradingview", "orderbook", "machine learning", "neural", "kalman",
    "garch", "copula", "stat arb", "reinforcement", "alpha",
    # Chinese
    "联网", "调研", "搜索", "前沿", "研报", "论文", "最新",
    "套利", "资金费率", "超买超卖", "动态波动", "机器学习",
})


def should_trigger_deep_research(prompt: str) -> bool:
    """Evaluates whether the user's prompt warrants a web research pre-flight step."""
    if not prompt:
        return False
    lower = prompt.lower()
    for kw in _RESEARCH_KEYWORDS:
        if kw in lower:
            return True
    # If prompt is long and detailed (>120 chars) and asks for specific indicators
    if len(prompt) > 120 and ("indicator" in lower or "strategy" in lower or "formula" in lower):
        return True
    return False


def build_smart_strategy_dag() -> DAG:
    """Constructs the intent-aware adaptive strategy generation DAG."""
    tools = init_default_tools()

    # Node 1: Fast Intent Router
    async def _router_action(ctx: DAGContext) -> dict[str, Any]:
        prompt = ctx.get("prompt", "")
        needs_search = should_trigger_deep_research(prompt)
        track = "deep_research_track" if needs_search else "fast_track"
        ctx.set("needs_web_search", needs_search)
        ctx.set("needs_market_analysis", True)
        ctx.set("execution_track", track)
        ctx.log(f"Intent routed to: '{track}' (needs_web_search={needs_search})")
        return {"track": track, "needs_search": needs_search}

    # Node 2A: Web Search (executed conditionally on deep track)
    async def _search_action(ctx: DAGContext) -> Any:
        import re
        prompt = ctx.get("prompt", "")
        search_tool = tools.require("web_search")
        # Strip generic instruction filler words to focus search on core indicators/concepts
        clean_q = re.sub(r"(?i)(请|联网|调研|搜索|编写|实现|一个|基于|策略|量化|代码|结合)", " ", prompt).strip()
        clean_q = re.sub(r"\s+", " ", clean_q) or prompt
        query = f"{clean_q} trading strategy"
        ctx.log(f"Performing web search for: '{query}'")
        res = await search_tool.run(query=query, max_results=3)
        return res.data if res.success else []

    # Node 2B: Market Regime Analysis (executed in parallel with 2A)
    async def _market_action(ctx: DAGContext) -> Any:
        symbol = ctx.get("symbol", "BTC-USDT")
        interval = ctx.get("interval", "1h")
        analyzer = tools.require("market_analyzer")
        res = await analyzer.run(symbol=symbol, interval=interval)
        return res.data if res.success else {}

    # Node 3: Context & Blueprint Assembly
    async def _assembly_action(ctx: DAGContext) -> str:
        prompt = ctx.get("prompt", "")
        search_data = ctx.get("search_results") or []
        market_data = ctx.get("market_regime") or {}

        sections = [f"User Goal: {prompt}"]
        if market_data:
            regime = market_data.get("regime", "normal")
            atr_pct = market_data.get("normalized_atr_pct", 2.0)
            sections.append(
                f"Market Regime Context: {regime} (Normalized ATR: {atr_pct}%). "
                f"Recommended Style: {market_data.get('recommended_style', 'momentum')}"
            )

        if search_data:
            snippets = [
                f"- {item.get('title')}: {item.get('snippet')}"
                for item in search_data[:2]
                if isinstance(item, dict) and item.get("snippet")
            ]
            if snippets:
                sections.append("Relevant Research Findings:\n" + "\n".join(snippets))

        enriched = "\n\n".join(sections)
        ctx.set("enriched_prompt", enriched)
        return enriched

    # Node 4: Tau Coding / Strategy Generator Node
    async def _tau_action(ctx: DAGContext) -> str:
        custom_generator = ctx.get("custom_generator")
        if custom_generator and callable(custom_generator):
            code = await custom_generator(ctx)
            return code

        # Default code generator fallback / Mock for testing
        code = ctx.get("strategy_code") or (
            "import numpy as np\n"
            "import pandas as pd\n\n"
            "def generate_signals(df, params):\n"
            "    df['ema_fast'] = df['close'].ewm(span=params.get('fast', 10)).mean()\n"
            "    df['ema_slow'] = df['close'].ewm(span=params.get('slow', 30)).mean()\n"
            "    df['signal'] = (df['ema_fast'] > df['ema_slow']).astype(int)\n"
            "    return df\n"
        )
        return code

    # Node 5: AST Security & Future Leak Audit
    async def _audit_action(ctx: DAGContext) -> dict[str, Any]:
        code = ctx.get("strategy_code", "")
        auditor = tools.require("ast_auditor")
        res = await auditor.run(code=code)
        report = res.data if res.success else {"passed": False, "issues": ["Audit failed"]}
        ctx.set("audit_report", report)
        return report

    dag = DAG(name="smart_strategy_pipeline")
    dag.add_node(DAGNode(id="router", action=_router_action, output_key="route_info"))
    dag.add_node(
        DAGNode(
            id="web_search_node",
            depends_on=["router"],
            action=_search_action,
            output_key="search_results",
            condition=lambda c: bool(c.get("needs_web_search", False)),
            timeout_s=8.0,
        )
    )
    dag.add_node(
        DAGNode(
            id="market_analysis_node",
            depends_on=["router"],
            action=_market_action,
            output_key="market_regime",
            condition=lambda c: bool(c.get("needs_market_analysis", True)),
        )
    )
    dag.add_node(
        DAGNode(
            id="blueprint_assembly_node",
            depends_on=["web_search_node", "market_analysis_node"],
            action=_assembly_action,
            output_key="enriched_prompt",
        )
    )
    dag.add_node(
        DAGNode(
            id="tau_coding_node",
            depends_on=["blueprint_assembly_node"],
            action=_tau_action,
            output_key="strategy_code",
        )
    )
    dag.add_node(
        DAGNode(
            id="code_audit_node",
            depends_on=["tau_coding_node"],
            action=_audit_action,
            output_key="audit_report",
        )
    )

    return dag
