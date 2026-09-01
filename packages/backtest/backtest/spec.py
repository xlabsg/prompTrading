from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml


@dataclass(frozen=True)
class EntrypointSpec:
    module: str
    function: str


@dataclass(frozen=True)
class StrategySpec:
    engine_type: str
    entrypoint: EntrypointSpec
    params: dict[str, Any]
    signal_mode: str = "target_weights"


def load_strategy_spec(path: str) -> StrategySpec:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    engine_type = str(raw.get("engine_type") or "vectorized")
    ep_raw = raw.get("entrypoint") or {}
    entrypoint = EntrypointSpec(
        module=str(ep_raw.get("module") or "strategy.py"),
        function=str(ep_raw.get("function") or "generate_signals"),
    )
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("strategy_spec.params must be a dict")
    signal_mode_raw = str(raw.get("signal_mode") or "target_weights").strip().lower()
    if signal_mode_raw not in ("target_weights", "auto"):
        signal_mode_raw = "target_weights"
    return StrategySpec(engine_type=engine_type, entrypoint=entrypoint, params=params, signal_mode=signal_mode_raw)
