from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

from agent.dag.context import DAGContext

logger = logging.getLogger(__name__)

NodeAction = Callable[[DAGContext], Coroutine[Any, Any, Any]]
NodeCondition = Callable[[DAGContext], bool]


@dataclass
class DAGNode:
    """A node in a directed acyclic workflow graph."""

    id: str
    action: NodeAction
    depends_on: list[str] = field(default_factory=list)
    output_key: Optional[str] = None
    condition: Optional[NodeCondition] = None
    timeout_s: Optional[float] = None
    description: str = ""


class DAG:
    """Declarative workflow graph definition with topological level resolution."""

    def __init__(self, name: str, nodes: list[DAGNode] | None = None):
        self.name = name
        self.nodes: dict[str, DAGNode] = {}
        if nodes:
            for node in nodes:
                self.add_node(node)

    def add_node(self, node: DAGNode) -> DAG:
        if node.id in self.nodes:
            raise ValueError(f"Duplicate node id in DAG: '{node.id}'")
        self.nodes[node.id] = node
        return self

    def resolve_execution_levels(self) -> list[list[DAGNode]]:
        """Resolves nodes into concurrent execution levels using Kahn's topological sort.

        Returns a list of levels, where all nodes within a level can be executed
        concurrently with asyncio.gather.
        """
        # Validate all dependencies exist
        for node_id, node in self.nodes.items():
            for dep in node.depends_on:
                if dep not in self.nodes:
                    raise ValueError(f"Node '{node_id}' depends on non-existent node '{dep}'")

        in_degree = {nid: len(n.depends_on) for nid, n in self.nodes.items()}
        dependents: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for nid, n in self.nodes.items():
            for dep in n.depends_on:
                dependents[dep].append(nid)

        levels: list[list[DAGNode]] = []
        current_level = [self.nodes[nid] for nid, deg in in_degree.items() if deg == 0]

        visited_count = 0
        while current_level:
            levels.append(current_level)
            visited_count += len(current_level)

            next_level_candidates: list[str] = []
            for node in current_level:
                for child_id in dependents[node.id]:
                    in_degree[child_id] -= 1
                    if in_degree[child_id] == 0:
                        next_level_candidates.append(child_id)

            current_level = [self.nodes[nid] for nid in next_level_candidates]

        if visited_count != len(self.nodes):
            raise ValueError(
                f"Cycle detected in DAG '{self.name}'. Total nodes: {len(self.nodes)}, resolved: {visited_count}"
            )

        return levels


class DAGRunner:
    """Executes a declarative DAG asynchronously with level-based concurrency."""

    async def run(self, dag: DAG, initial_state: Optional[dict[str, Any]] = None) -> DAGContext:
        ctx = DAGContext(state=dict(initial_state or {}))
        ctx.log(f"Starting DAG workflow: '{dag.name}'")
        start_time = time.monotonic()

        levels = dag.resolve_execution_levels()
        for lvl_idx, level in enumerate(levels):
            # Run all nodes in the same topological level concurrently
            tasks = [self._execute_node(node, ctx) for node in level]
            await asyncio.gather(*tasks, return_exceptions=False)

        total_duration = time.monotonic() - start_time
        ctx.log(f"DAG '{dag.name}' finished in {total_duration:.2f}s")
        return ctx

    async def _execute_node(self, node: DAGNode, ctx: DAGContext) -> None:
        # Check conditional execution
        if node.condition is not None:
            try:
                should_run = node.condition(ctx)
                if not should_run:
                    ctx.log(f"Node '{node.id}' skipped (condition evaluated to False)")
                    return
            except Exception as e:
                ctx.log(f"Node '{node.id}' condition evaluation error: {e}")
                ctx.record_node_execution(node.id, 0.0, error=str(e))
                return

        ctx.log(f"Running node: '{node.id}'")
        t0 = time.monotonic()
        err_msg = None
        try:
            if node.timeout_s is not None and node.timeout_s > 0:
                result = await asyncio.wait_for(node.action(ctx), timeout=node.timeout_s)
            else:
                result = await node.action(ctx)

            if node.output_key:
                ctx.set(node.output_key, result)

        except asyncio.TimeoutError:
            err_msg = f"Node '{node.id}' timed out after {node.timeout_s}s"
            logger.warning(err_msg)
            ctx.log(err_msg)
        except Exception as e:
            err_msg = f"Node '{node.id}' error: {e}"
            logger.warning(err_msg)
            ctx.log(err_msg)
        finally:
            dur = time.monotonic() - t0
            ctx.record_node_execution(node.id, dur, error=err_msg)
