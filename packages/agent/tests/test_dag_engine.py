import asyncio
import time
import unittest
from agent.dag.context import DAGContext
from agent.dag.engine import DAG, DAGNode, DAGRunner
from agent.dag.pipelines.smart_pipeline import (
    build_smart_strategy_dag,
    should_trigger_deep_research,
)


class TestDAGEngine(unittest.TestCase):
    def test_dag_topological_resolution(self):
        dag = DAG(name="test_dag")

        # N0
        # N1 -> depends on N0
        # N2 -> depends on N0 (N1 and N2 are parallel)
        # N3 -> depends on N1 and N2
        dag.add_node(DAGNode(id="n0", action=lambda ctx: asyncio.sleep(0)))
        dag.add_node(DAGNode(id="n1", depends_on=["n0"], action=lambda ctx: asyncio.sleep(0)))
        dag.add_node(DAGNode(id="n2", depends_on=["n0"], action=lambda ctx: asyncio.sleep(0)))
        dag.add_node(DAGNode(id="n3", depends_on=["n1", "n2"], action=lambda ctx: asyncio.sleep(0)))

        levels = dag.resolve_execution_levels()
        self.assertEqual(len(levels), 3)
        self.assertEqual([n.id for n in levels[0]], ["n0"])
        self.assertEqual(set(n.id for n in levels[1]), {"n1", "n2"})
        self.assertEqual([n.id for n in levels[2]], ["n3"])

    def test_dag_cycle_detection(self):
        dag = DAG(name="cyclic_dag")
        dag.add_node(DAGNode(id="a", depends_on=["b"], action=lambda ctx: asyncio.sleep(0)))
        dag.add_node(DAGNode(id="b", depends_on=["a"], action=lambda ctx: asyncio.sleep(0)))

        with self.assertRaises(ValueError):
            dag.resolve_execution_levels()

    def test_dag_parallel_execution_concurrency(self):
        dag = DAG(name="parallel_timing_test")

        # Two nodes each sleeping 0.05s concurrently
        async def sleep_task(ctx):
            await asyncio.sleep(0.05)
            return "done"

        dag.add_node(DAGNode(id="task1", action=sleep_task, output_key="res1"))
        dag.add_node(DAGNode(id="task2", action=sleep_task, output_key="res2"))

        runner = DAGRunner()
        t0 = time.monotonic()
        ctx = asyncio.run(runner.run(dag))
        t1 = time.monotonic()

        self.assertEqual(ctx.get("res1"), "done")
        self.assertEqual(ctx.get("res2"), "done")
        # Concurrent execution should take ~0.05s, definitely less than sequential 0.10s
        self.assertLess(t1 - t0, 0.09)

    def test_intent_routing_heuristics(self):
        # Fast track prompts: standard quant terms must NOT falsely trigger search
        self.assertFalse(should_trigger_deep_research("write a simple EMA crossover"))
        self.assertFalse(should_trigger_deep_research("buy when close > ema 20"))
        self.assertFalse(should_trigger_deep_research("编写一个资金费率套利策略"))
        self.assertFalse(should_trigger_deep_research("implement a VWAP mean reversion strategy"))

        # Deep research prompts: explicit research / paper / external sources
        self.assertTrue(should_trigger_deep_research("search for the latest funding rate arbitrage strategy"))
        self.assertTrue(should_trigger_deep_research("implement the Hull Moving Average formula from research paper"))
        self.assertTrue(should_trigger_deep_research("convert this TradingView PineScript supertrend indicator"))
        self.assertTrue(should_trigger_deep_research("请联网调研最新波动率通道突破策略"))

        # Custom classifier injection test
        custom_mock = lambda prompt: (True, "mocked query")
        self.assertTrue(should_trigger_deep_research("any prompt", classifier=custom_mock))

    def test_smart_strategy_pipeline_fast_track(self):
        dag = build_smart_strategy_dag()
        runner = DAGRunner()

        initial_state = {
            "prompt": "write a 5/20 EMA crossover strategy",
            "symbol": "BTC-USDT",
        }

        ctx = asyncio.run(runner.run(dag, initial_state))

        # Fast track should NOT execute web_search_node
        self.assertEqual(ctx.get("execution_track"), "fast_track")
        self.assertFalse(ctx.get("needs_web_search"))
        self.assertIsNone(ctx.get("search_results"))
        self.assertIsNotNone(ctx.get("market_regime"))
        self.assertIsNotNone(ctx.get("strategy_code"))
        self.assertTrue(ctx.get("audit_report")["passed"])

    def test_smart_strategy_pipeline_deep_track(self):
        dag = build_smart_strategy_dag()
        runner = DAGRunner()

        initial_state = {
            "prompt": "research the Supertrend breakout strategy from TradingView",
            "symbol": "BTC-USDT",
        }

        ctx = asyncio.run(runner.run(dag, initial_state))

        # Deep track SHOULD execute web_search_node
        self.assertEqual(ctx.get("execution_track"), "deep_research_track")
        self.assertTrue(ctx.get("needs_web_search"))
        self.assertIsNotNone(ctx.get("search_results"))
        self.assertIsNotNone(ctx.get("market_regime"))
        self.assertIn("Market Regime Context", ctx.get("enriched_prompt"))
        self.assertTrue(ctx.get("audit_report")["passed"])


if __name__ == "__main__":
    unittest.main()
