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
        "workflow_graph": {
            "nodes": [{"id": "string", "label": "string", "type": "process"}],
            "edges": [{"source": "string", "target": "string", "label": "string"}]
        },
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


def fallback_strategy_py(prompt: str) -> str:
    """Generate a simple MA crossover strategy as fallback when LLM is unavailable."""
    prompt_snippet = prompt.replace("\n", " ")[:200]
    return f'''"""
Auto-generated strategy (fallback).

User prompt: {prompt_snippet}

This is a simple MA crossover strategy used as a fallback when the LLM is unavailable.
"""

import pandas as pd
import numpy as np
from backtest.indicators import sma


def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Vectorized bi-directional MA regime strategy.

    Args:
        data: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Strategy parameters (e.g., {{"fast": 10, "slow": 30}})

    Returns:
        Dictionary with target weights:
        {{
            "target_weights": float_array,  # [-1, 1], negative = short
            "weight_reason": list[str],     # per-bar reason
        }}
    """
    close = data["close"].astype(float)
    fast_n = int(params.get("fast", 10))
    slow_n = int(params.get("slow", 30))

    # Validate parameters
    if slow_n <= fast_n:
        slow_n = fast_n + 10

    fast = sma(close, fast_n)
    slow = sma(close, slow_n)

    long_regime = (fast > slow) & fast.notna() & slow.notna()
    short_regime = (fast < slow) & fast.notna() & slow.notna()
    weights = np.where(long_regime, 1.0, np.where(short_regime, -1.0, 0.0))
    w_series = pd.Series(weights, index=data.index)
    prev = w_series.shift(1).fillna(0.0)

    reasons = []
    for i in range(len(w_series)):
        cur = float(w_series.iloc[i])
        prv = float(prev.iloc[i])
        if cur > 0 and prv <= 0:
            reasons.append(f"ma_regime_long (fast={{fast_n}}, slow={{slow_n}})")
        elif cur < 0 and prv >= 0:
            reasons.append(f"ma_regime_short (fast={{fast_n}}, slow={{slow_n}})")
        elif cur == 0 and prv != 0:
            reasons.append("ma_regime_flat")
        else:
            reasons.append("")

    return {{
        "target_weights": w_series.to_numpy(dtype=float),
        "weight_reason": reasons,
        # Helpful debug series (bar-aligned).
        "fast_ma": fast.to_numpy(),
        "slow_ma": slow.to_numpy(),
        "long_regime": long_regime.fillna(False).to_numpy(),
        "short_regime": short_regime.fillna(False).to_numpy(),
    }}
'''
