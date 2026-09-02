from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DAGContext:
    """Shared state blackboard for a DAG workflow execution."""

    state: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    execution_times: dict[str, float] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.state[key] = value

    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")

    def record_node_execution(self, node_id: str, duration_s: float, error: Optional[str] = None) -> None:
        self.execution_times[node_id] = round(duration_s, 4)
        if error:
            self.errors[node_id] = error

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "logs": self.logs,
            "execution_times": self.execution_times,
            "errors": self.errors,
        }
