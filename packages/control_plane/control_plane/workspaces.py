from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyPaths:
    root: str
    strategy_dir: str
    runs_dir: str
    versions_dir: str
    data_dir: str


def get_strategy_paths(workspaces_dir: str, strategy_id: str) -> StrategyPaths:
    root = os.path.join(workspaces_dir, strategy_id)
    return StrategyPaths(
        root=root,
        strategy_dir=os.path.join(root, "strategy"),
        runs_dir=os.path.join(root, "runs"),
        versions_dir=os.path.join(root, "versions"),
        data_dir=os.path.join(root, "data"),
    )


DEFAULT_STRATEGY_PY = """\
import pandas as pd
import numpy as np


def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    \"\"\"Return vectorized signals for backtesting.

    Expected return keys:
    - target_weights: float array in [-1, 1]
    \"\"\"
    close = data[\"close\"]
    fast_n = int(params.get(\"fast\", 10))
    slow_n = int(params.get(\"slow\", 30))
    if slow_n <= fast_n:
        slow_n = fast_n + 5

    fast = close.rolling(fast_n).mean()
    slow = close.rolling(slow_n).mean()

    long_regime = (fast > slow) & fast.notna() & slow.notna()
    short_regime = (fast < slow) & fast.notna() & slow.notna()
    target_weights = np.where(long_regime, 1.0, np.where(short_regime, -1.0, 0.0))
    target_series = pd.Series(target_weights, index=data.index)

    prev = target_series.shift(1).fillna(0.0)
    reasons: list[str] = []
    for i in range(len(target_series)):
        cur = float(target_series.iloc[i])
        prv = float(prev.iloc[i])
        if cur > 0 and prv <= 0:
            reasons.append(f\"ma_regime_long ({fast_n}/{slow_n})\")
        elif cur < 0 and prv >= 0:
            reasons.append(f\"ma_regime_short ({fast_n}/{slow_n})\")
        elif cur == 0 and prv != 0:
            reasons.append(\"ma_regime_flat\")
        else:
            reasons.append(\"\")

    return {
        \"target_weights\": target_series.to_numpy(dtype=float),
        \"weight_reason\": reasons,
        # Helpful debug series (bar-aligned).
        \"fast_ma\": fast.to_numpy(),
        \"slow_ma\": slow.to_numpy(),
        \"long_regime\": long_regime.fillna(False).to_numpy(),
        \"short_regime\": short_regime.fillna(False).to_numpy(),
    }
"""

DEFAULT_LIVE_STRATEGY_PY = """\
import importlib.util
import os
import pandas as pd

try:
    from live_trading_sdk import LiveStrategy, StrategyContext, Broker, Bar
except Exception:  # SDK is optional during cold start/backtests
    LiveStrategy = object  # type: ignore
    StrategyContext = Broker = Bar = object  # type: ignore


def _load_generate_signals():
    strategy_path = os.path.join(os.path.dirname(__file__), "strategy.py")
    spec = importlib.util.spec_from_file_location("strategy_module", strategy_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, "generate_signals", None)
    return fn if callable(fn) else None


class ExampleLiveStrategy(LiveStrategy):
    \"\"\"Default live strategy that reuses generate_signals().\"\"\"

    def __init__(self) -> None:
        self.context: StrategyContext | None = None
        self._signals_fn = None

    def initialize(self, context: StrategyContext) -> None:
        self.context = context
        self._signals_fn = _load_generate_signals()

    def on_bar(self, bar: Bar, history: pd.DataFrame, broker: Broker) -> None:
        if self._signals_fn is None:
            return
        params = dict(getattr(self.context, "params", {}) or {})
        signals = self._signals_fn(history, params)
        if not isinstance(signals, dict):
            return

        weight = None
        if "target" in signals:
            try:
                weight = float(signals.get("target"))
            except Exception:
                weight = None
        elif "target_weights" in signals:
            weights = signals.get("target_weights")
            if weights is None or len(weights) == 0:
                return
            weight = float(weights[-1])

        if weight is not None:
            if weight > 1.0:
                weight = 1.0
            if weight < -1.0:
                weight = -1.0
            reasons = signals.get("weight_reason")
            reason = ""
            if reasons is not None and len(reasons) > 0:
                reason = reasons[-1]
            broker.set_target_allocation(weight, reason=reason or "target_weight")
            return

    def on_error(self, error: Exception, broker: Broker) -> None:
        pass
"""


DEFAULT_STRATEGY_SPEC_YAML = """\
engine_type: vectorized
entrypoint:
  module: strategy.py
  function: generate_signals
signal_mode: target_weights
params: {}
"""

DEFAULT_STRATEGY_PROTOCOL = {
    "version": 2,
    "signal_mode": "target_weights",
    "input": {
        "function": "generate_signals(data, params)",
        "data_schema": {
            "columns": ["timestamp", "open", "high", "low", "close", "volume"],
            "types": {
                "timestamp": "int(ms)",
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
                "volume": "float",
            },
            "sorted": "timestamp_asc",
        },
        "params_schema": "params_schema.json",
    },
    "output": {
        "required_series": ["target_weights", "weight_reason"],
        "series_length": "n (len(data))",
        "debug_series": {"min": 2, "max": 8, "types": ["bool", "float", "int"]},
        "notes": "target_weights in [-1,1]; negative values represent short exposure; signals act at bar close for next bar",
    },
    "lifecycle": {
        "strategy_generation": ["queued", "running", "succeeded", "failed"],
        "backtest_run": ["queued", "running", "succeeded", "failed"],
    },
    "logs": {
        "agent_log": "runs/<run_id>/agent.log",
        "backtest_log": "runs/<run_id>/backtest.log",
        "signals": "runs/<run_id>/signals.json",
        "signal_events": "runs/<run_id>/signal_events.json",
    },
    "metrics": {
        "metrics_file": "runs/<run_id>/metrics.json",
        "fields": [
            "total_return",
            "max_drawdown",
            "win_rate",
            "profit_factor",
            "sharpe_ratio",
            "total_trades",
            "num_bars",
            "fee_rate",
            "slippage_bps",
        ],
    },
}


def init_git_repo(strategy_dir: str) -> bool:
    """Initialize git repository in strategy directory if not exists.
    
    Returns True if newly initialized, False if already exists.
    """
    git_dir = os.path.join(strategy_dir, ".git")
    if os.path.exists(git_dir):
        return False  # Already initialized
    
    try:
        subprocess.run(["git", "init"], cwd=strategy_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "ai@strategy.local"],
            cwd=strategy_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "AI Strategy Bot"],
            cwd=strategy_dir, check=True, capture_output=True
        )
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        # git not installed
        return False


def git_commit(strategy_dir: str, message: str) -> str | None:
    """Stage all changes and commit.
    
    Returns commit SHA if successful, None if nothing to commit or error.
    """
    git_dir = os.path.join(strategy_dir, ".git")
    if not os.path.exists(git_dir):
        return None
    
    try:
        # Stage all changes
        subprocess.run(["git", "add", "."], cwd=strategy_dir, check=True, capture_output=True)
        
        # Commit (may fail if nothing to commit)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=strategy_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return None
        
        # Get commit SHA
        sha_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=strategy_dir,
            capture_output=True,
            text=True
        )
        if sha_result.returncode == 0:
            return sha_result.stdout.strip()
        return None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def init_strategy_workspace(workspaces_dir: str, strategy_id: str) -> StrategyPaths:
    paths = get_strategy_paths(workspaces_dir, strategy_id)
    os.makedirs(paths.strategy_dir, exist_ok=True)
    os.makedirs(paths.runs_dir, exist_ok=True)
    os.makedirs(paths.versions_dir, exist_ok=True)
    os.makedirs(paths.data_dir, exist_ok=True)

    strategy_py_path = os.path.join(paths.strategy_dir, "strategy.py")
    spec_path = os.path.join(paths.strategy_dir, "strategy_spec.yaml")
    protocol_path = os.path.join(paths.strategy_dir, "strategy_protocol.json")
    if not os.path.exists(strategy_py_path):
        with open(strategy_py_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_STRATEGY_PY)
    if not os.path.exists(spec_path):
        with open(spec_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_STRATEGY_SPEC_YAML)
    if not os.path.exists(protocol_path):
        with open(protocol_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_STRATEGY_PROTOCOL, f, ensure_ascii=False, indent=2, sort_keys=True)
    
    # Initialize git repository for version control
    init_git_repo(paths.strategy_dir)
    git_commit(paths.strategy_dir, "Initial strategy scaffold")
    
    return paths


def get_version_dir(paths: StrategyPaths, version_id: str) -> str:
    return os.path.join(paths.versions_dir, version_id)


def snapshot_current_strategy_to_version(workspaces_dir: str, strategy_id: str, version_id: str) -> str:
    """Copy current strategy files into a stable, version-addressed directory.

    Returns the relative workspace path, e.g. "versions/<version_id>/".
    """
    paths = get_strategy_paths(workspaces_dir, strategy_id)
    version_dir = get_version_dir(paths, version_id)
    os.makedirs(version_dir, exist_ok=True)

    # Copy strategy sources
    for name in (
        "strategy.py",
        "strategy_spec.yaml",
        "strategy_live.py",
        "strategy_protocol.json",
        "params_schema.json",
        "strategy_meta.json",
    ):
        src = os.path.join(paths.strategy_dir, name)
        dst = os.path.join(version_dir, name)
        if os.path.exists(src):
            with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                fdst.write(fsrc.read())
    return f"versions/{version_id}"


def get_run_dir(workspaces_dir: str, strategy_id: str, run_id: str) -> str:
    paths = get_strategy_paths(workspaces_dir, strategy_id)
    return os.path.join(paths.runs_dir, run_id)


def restore_version_to_current_strategy(workspaces_dir: str, strategy_id: str, version_id: str) -> None:
    """Restore a version snapshot into the current (working) strategy directory."""
    paths = get_strategy_paths(workspaces_dir, strategy_id)
    version_dir = get_version_dir(paths, version_id)

    # Copy strategy sources from version snapshot into working copy.
    for name in (
        "strategy.py",
        "strategy_spec.yaml",
        "strategy_live.py",
        "strategy_protocol.json",
        "params_schema.json",
        "strategy_meta.json",
    ):
        src = os.path.join(version_dir, name)
        dst = os.path.join(paths.strategy_dir, name)
        os.makedirs(paths.strategy_dir, exist_ok=True)
        if os.path.exists(src):
            with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                fdst.write(fsrc.read())
        else:
            if os.path.exists(dst):
                os.remove(dst)
