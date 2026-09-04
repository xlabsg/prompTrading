import unittest
import asyncio
from agent.tools.base import tool
from agent.tools.registry import ToolRegistry
from agent.tools.web_search import DuckDuckGoSearchTool
from agent.tools.market_analyzer import MarketAnalyzerTool
from agent.tools.ast_auditor import ASTAuditorTool


class TestAgentTools(unittest.TestCase):
    def test_tool_decorator(self):
        @tool(name="add_numbers", description="Adds two numbers")
        def add(a: int, b: int) -> int:
            return a + b

        self.assertEqual(add.name, "add_numbers")
        result = asyncio.run(add.run(a=2, b=3))
        self.assertTrue(result.success)
        self.assertEqual(result.data, 5)

    def test_tool_registry(self):
        reg = ToolRegistry()
        search_tool = DuckDuckGoSearchTool()
        reg.register(search_tool)

        self.assertTrue(reg.has("web_search"))
        self.assertEqual(reg.get("web_search"), search_tool)

        with self.assertRaises(KeyError):
            reg.require("non_existent_tool")

    def test_market_analyzer_tool(self):
        analyzer = MarketAnalyzerTool()
        result = asyncio.run(analyzer.run(symbol="BTC-USDT", interval="1h"))
        self.assertTrue(result.success)
        self.assertIn("regime", result.data)
        self.assertIn("atr_14", result.data)
        self.assertIn("normalized_atr_pct", result.data)

    def test_ast_auditor_tool(self):
        auditor = ASTAuditorTool()

        # Clean code
        clean_code = """
import numpy as np
import pandas as pd

def generate_signals(df, params):
    df['ema'] = df['close'].ewm(span=20).mean()
    df['signal'] = (df['close'] > df['ema']).astype(int)
    return df
"""
        res_clean = asyncio.run(auditor.run(code=clean_code))
        self.assertTrue(res_clean.success)
        self.assertTrue(res_clean.data["passed"])
        self.assertEqual(len(res_clean.data["issues"]), 0)

        # Lookahead bias code (shift(-1))
        bad_code = """
def generate_signals(df, params):
    df['future_close'] = df['close'].shift(-1)
    return df
"""
        res_bad = asyncio.run(auditor.run(code=bad_code))
        self.assertTrue(res_bad.success)
        self.assertFalse(res_bad.data["passed"])
        self.assertTrue(any("lookahead bias" in issue.lower() for issue in res_bad.data["issues"]))

        # Prohibited import (os)
        evil_code = """
import os
def generate_signals(df, params):
    os.system("ls")
    return df
"""
        res_evil = asyncio.run(auditor.run(code=evil_code))
        self.assertTrue(res_evil.success)
        self.assertFalse(res_evil.data["passed"])
        self.assertTrue(any("prohibited" in issue.lower() for issue in res_evil.data["issues"]))


if __name__ == "__main__":
    unittest.main()
