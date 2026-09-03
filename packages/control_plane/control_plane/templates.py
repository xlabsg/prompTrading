"""Strategy template definitions and workspace instantiation.

Provides runnable vectorized strategy implementations for standard templates
and handles copying/instantiating them into real user strategy workspaces.
"""
from __future__ import annotations

import json
import os
from typing import Any

from control_plane.workspaces import (
    DEFAULT_STRATEGY_PROTOCOL,
    StrategyPaths,
    get_strategy_paths,
    init_git_repo,
    git_commit,
    snapshot_current_strategy_to_version,
)


TEMPLATE_STRATEGIES: dict[str, str] = {
    "tmpl-divergence": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Divergence-style mean reversion with EMA + RSI guard."""
    close = data["close"]

    # Parameters with safe defaults
    ema_fast_window = int(params.get("ema_fast_window", 20))
    ema_slow_window = int(params.get("ema_slow_window", 50))
    rsi_window = int(params.get("rsi_window", 14))
    rsi_overbought_threshold = float(params.get("rsi_overbought_threshold", 70))
    stop_loss_pct = float(params.get("stop_loss_pct", 2.5))
    take_profit_pct = float(params.get("take_profit_pct", 5.0))
    trailing_stop_pct = float(params.get("trailing_stop_pct", 1.5))

    # Indicators
    ema_fast = close.ewm(span=ema_fast_window, adjust=False).mean()
    ema_slow = close.ewm(span=ema_slow_window, adjust=False).mean()

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # Entry/exit base signals
    ema_cross_up = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
    rsi_not_overbought = rsi < rsi_overbought_threshold
    entries = ema_cross_up & rsi_not_overbought
    exits = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))

    entries_b = entries.fillna(False)

    stop_loss_triggers = pd.Series(False, index=close.index)
    take_profit_triggers = pd.Series(False, index=close.index)
    trailing_stop_triggers = pd.Series(False, index=close.index)
    highest_since_entry = pd.Series(np.nan, index=close.index)

    in_position = False
    entry_price = 0.0
    current_highest = 0.0

    for i in range(len(close)):
        if entries_b.iloc[i] and not in_position:
            in_position = True
            entry_price = close.iloc[i]
            current_highest = entry_price
            highest_since_entry.iloc[i] = current_highest
            continue

        if not in_position:
            highest_since_entry.iloc[i] = np.nan
            continue

        current_highest = max(current_highest, close.iloc[i])
        highest_since_entry.iloc[i] = current_highest

        stop_loss_level = entry_price * (1 - stop_loss_pct / 100)
        take_profit_level = entry_price * (1 + take_profit_pct / 100)
        trailing_stop_level = current_highest * (1 - trailing_stop_pct / 100)

        if close.iloc[i] <= stop_loss_level:
            stop_loss_triggers.iloc[i] = True
            in_position = False
        elif close.iloc[i] >= take_profit_level:
            take_profit_triggers.iloc[i] = True
            in_position = False
        elif close.iloc[i] <= trailing_stop_level:
            trailing_stop_triggers.iloc[i] = True
            in_position = False
        elif exits.iloc[i]:
            in_position = False

    all_exits = exits | stop_loss_triggers | take_profit_triggers | trailing_stop_triggers
    exits_b = all_exits.fillna(False)

    entry_reasons = []
    for entry, cross, rsi_val in zip(entries_b, ema_cross_up, rsi):
        if entry:
            entry_reasons.append(f"ema_cross_up ({ema_fast_window}/{ema_slow_window}) & rsi_{rsi_val:.1f}<{rsi_overbought_threshold}")
        else:
            entry_reasons.append("")

    exit_reasons = []
    for i, exit_signal in enumerate(exits_b):
        if exit_signal:
            if stop_loss_triggers.iloc[i]:
                exit_reasons.append(f"stop_loss_{stop_loss_pct}%")
            elif take_profit_triggers.iloc[i]:
                exit_reasons.append(f"take_profit_{take_profit_pct}%")
            elif trailing_stop_triggers.iloc[i]:
                exit_reasons.append(f"trailing_stop_{trailing_stop_pct}%")
            else:
                exit_reasons.append(f"ema_cross_down ({ema_fast_window}/{ema_slow_window})")
        else:
            exit_reasons.append("")

    target_weights = np.zeros(len(close), dtype=float)
    weight_reason = []
    position = 0.0
    for i in range(len(close)):
        reason = ""
        if bool(entries_b.iloc[i]) and position == 0.0:
            position = 1.0
            reason = entry_reasons[i]
        elif bool(exits_b.iloc[i]) and position != 0.0:
            position = 0.0
            reason = exit_reasons[i]
        target_weights[i] = position
        weight_reason.append(reason)

    return {
        "target_weights": target_weights,
        "weight_reason": weight_reason,
        "ema_fast": ema_fast.to_numpy(),
        "ema_slow": ema_slow.to_numpy(),
        "rsi": rsi.to_numpy(),
        "ema_cross_up": ema_cross_up.to_numpy(),
        "rsi_not_overbought": rsi_not_overbought.to_numpy(),
        "stop_loss_triggers": stop_loss_triggers.to_numpy(),
        "take_profit_triggers": take_profit_triggers.to_numpy(),
        "trailing_stop_triggers": trailing_stop_triggers.to_numpy(),
        "highest_since_entry": highest_since_entry.to_numpy(),
    }
''',

    "tmpl-flow-right": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Flow Right Strategy - Order-flow momentum & multi-window regime."""
    close = data["close"]
    volume = data["volume"]
    high = data["high"]
    low = data["low"]

    ema_period = int(params.get("trend_ema_period", 50))
    vol_lookback = int(params.get("live_history_bars", 60))

    ema_trend = close.ewm(span=ema_period, adjust=False).mean()
    vol_mean = volume.rolling(vol_lookback).mean()
    vol_std = volume.rolling(vol_lookback).std().replace(0, np.nan)
    vol_zscore = ((volume - vol_mean) / vol_std).fillna(0.0)

    # Estimate candle directional flow
    hl_range = (high - low).replace(0, np.nan)
    co_delta = close - data["open"]
    flow_imbalance = (co_delta / hl_range).clip(-1.0, 1.0).fillna(0.0)

    # Price above EMA + positive flow imbalance + volume expansion
    long_regime = (close > ema_trend) & (flow_imbalance > 0.15) & (vol_zscore > -0.5)
    short_regime = (close < ema_trend) & (flow_imbalance < -0.15) & (vol_zscore > -0.5)

    target_weights = np.where(long_regime, 1.0, np.where(short_regime, -1.0, 0.0))
    target_series = pd.Series(target_weights, index=data.index)

    reasons: list[str] = []
    prev = target_series.shift(1).fillna(0.0)
    for i in range(len(target_series)):
        cur = float(target_series.iloc[i])
        prv = float(prev.iloc[i])
        if cur > 0 and prv <= 0:
            reasons.append(f"flow_impulse_long (imb={flow_imbalance.iloc[i]:.2f}, z={vol_zscore.iloc[i]:.2f})")
        elif cur < 0 and prv >= 0:
            reasons.append(f"flow_impulse_short (imb={flow_imbalance.iloc[i]:.2f}, z={vol_zscore.iloc[i]:.2f})")
        elif cur == 0 and prv != 0:
            reasons.append("flow_regime_exit")
        else:
            reasons.append("")

    return {
        "target_weights": target_series.to_numpy(dtype=float),
        "weight_reason": reasons,
        "ema_trend": ema_trend.to_numpy(),
        "flow_imbalance": flow_imbalance.to_numpy(),
        "vol_zscore": vol_zscore.to_numpy(),
    }
''',

    "tmpl-moving-average-crossover": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Moving Average Crossover Strategy"""
    close = data["close"]

    short_window = int(params.get("short_window", 20))
    long_window = int(params.get("long_window", 50))

    short_ma = close.rolling(short_window).mean()
    long_ma = close.rolling(long_window).mean()

    long_regime = (short_ma > long_ma) & short_ma.notna() & long_ma.notna()
    short_regime = (short_ma < long_ma) & short_ma.notna() & long_ma.notna()
    target_weights = np.where(long_regime, 1.0, np.where(short_regime, -1.0, 0.0))
    return {
        "target_weights": target_weights,
        "short_ma": short_ma.to_numpy(),
        "long_ma": long_ma.to_numpy(),
        "long_regime": long_regime.fillna(False).to_numpy(),
        "short_regime": short_regime.fillna(False).to_numpy(),
    }
''',

    "tmpl-rsi-oversold": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """RSI Mean Reversion Strategy"""
    close = data["close"]

    rsi_period = int(params.get("rsi_period", 14))
    oversold = float(params.get("oversold", 30))
    overbought = float(params.get("overbought", 70))

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    long_regime = (rsi <= oversold) & rsi.notna()
    short_regime = (rsi >= overbought) & rsi.notna()
    target_weights = np.where(long_regime, 1.0, np.where(short_regime, -1.0, 0.0))

    return {
        "target_weights": target_weights,
        "rsi": rsi.to_numpy(),
        "long_regime": long_regime.fillna(False).to_numpy(),
        "short_regime": short_regime.fillna(False).to_numpy(),
    }
''',

    "tmpl-price-breakout": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Price Breakout Strategy"""
    close = data["close"]
    high = data["high"]
    volume = data["volume"]

    lookback = int(params.get("lookback", 20))
    volume_mult = float(params.get("volume_mult", 2.0))

    high_lookback = high.rolling(lookback).max()
    avg_volume = volume.rolling(lookback).mean()

    low_lookback = data["low"].rolling(lookback).min()
    breakout_up = (close > high_lookback.shift(1)) & (volume > avg_volume * volume_mult)
    breakout_down = (close < low_lookback.shift(1)) & (volume > avg_volume * volume_mult)

    target_weights = np.where(breakout_up.fillna(False), 1.0, np.where(breakout_down.fillna(False), -1.0, 0.0))
    return {
        "target_weights": target_weights,
        "breakout_up": breakout_up.fillna(False).to_numpy(),
        "breakout_down": breakout_down.fillna(False).to_numpy(),
        "high_lookback": high_lookback.to_numpy(),
        "low_lookback": low_lookback.to_numpy(),
    }
''',

    "tmpl-trend-following": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Trend Following Strategy"""
    close = data["close"]

    fast = int(params.get("fast", 50))
    slow = int(params.get("slow", 100))

    fast_ma = close.ewm(span=fast, adjust=False).mean()
    slow_ma = close.ewm(span=slow, adjust=False).mean()

    long_regime = (close > slow_ma) & (fast_ma > slow_ma) & fast_ma.notna() & slow_ma.notna()
    short_regime = (close < slow_ma) & (fast_ma < slow_ma) & fast_ma.notna() & slow_ma.notna()
    target_weights = np.where(long_regime, 1.0, np.where(short_regime, -1.0, 0.0))

    return {
        "target_weights": target_weights,
        "fast_ma": fast_ma.to_numpy(),
        "slow_ma": slow_ma.to_numpy(),
        "long_regime": long_regime.fillna(False).to_numpy(),
        "short_regime": short_regime.fillna(False).to_numpy(),
    }
''',

    "tmpl-grid-trading": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Grid Trading (Range Mean Reversion)"""
    close = data["close"]

    lookback = int(params.get("lookback", 100))
    lower_pct = float(params.get("lower_pct", 0.02))
    upper_pct = float(params.get("upper_pct", 0.02))

    mid = close.rolling(lookback).mean()
    lower = mid * (1 - lower_pct)
    upper = mid * (1 + upper_pct)

    long_regime = (close <= lower) & lower.notna()
    short_regime = (close >= upper) & upper.notna()
    target_weights = np.where(long_regime, 1.0, np.where(short_regime, -1.0, 0.0))

    return {
        "target_weights": target_weights,
        "mid": mid.to_numpy(),
        "lower": lower.to_numpy(),
        "upper": upper.to_numpy(),
    }
''',

    "tmpl-bollinger-breakout": '''import pandas as pd
import numpy as np

def generate_signals(data: pd.DataFrame, params: dict) -> dict:
    """Bollinger Band Breakout Strategy"""
    close = data["close"]

    bb_period = int(params.get("bb_period", 20))
    bb_std = float(params.get("bb_std", 2))

    sma = close.rolling(bb_period).mean()
    std = close.rolling(bb_period).std()
    upper = sma + (bb_std * std)

    entries = (close > upper) & (close.shift(1) <= upper.shift(1))
    exits = (close < sma) & (close.shift(1) >= sma.shift(1))

    target_weights = np.where(entries.fillna(False), 1.0, np.where(exits.fillna(False), 0.0, 0.0))
    return {
        "target_weights": target_weights,
        "upper": upper.to_numpy(),
        "sma": sma.to_numpy(),
    }
''',
}


def get_template_strategy_code(
    template_id: str = "",
    template_name: str = "",
    prompt: str = "",
) -> str:
    """Retrieve executable Python code for a strategy template."""
    clean_id = (template_id or "").strip().lower()
    clean_name = (template_name or "").strip().lower()

    if clean_id in TEMPLATE_STRATEGIES:
        return TEMPLATE_STRATEGIES[clean_id]

    for key, code in TEMPLATE_STRATEGIES.items():
        if clean_name and (clean_name in key or key.replace("tmpl-", "").replace("-", "_") == clean_name):
            return code

    return TEMPLATE_STRATEGIES["tmpl-moving-average-crossover"]


def _format_yaml(data: dict[str, Any]) -> str:
    """Format dictionary to basic YAML format without external dependencies."""
    try:
        import yaml
        return yaml.safe_dump(data, sort_keys=False)
    except Exception:
        lines = []
        for k, v in data.items():
            if isinstance(v, dict):
                lines.append(f"{k}:")
                for sub_k, sub_v in v.items():
                    lines.append(f"  {sub_k}: {sub_v}")
            else:
                lines.append(f"{k}: {v}")
        return "\n".join(lines) + "\n"


def instantiate_strategy_from_template(
    workspaces_dir: str,
    strategy_id: str,
    version_id: str,
    template: Any,
) -> StrategyPaths:
    """Instantiate a real strategy workspace from a template.

    Writes the template's actual code into strategy/strategy.py, configures
    strategy_spec.yaml, initializes git tracking, and snapshots to versions/{version_id}/.
    """
    paths = get_strategy_paths(workspaces_dir, strategy_id)
    os.makedirs(paths.strategy_dir, exist_ok=True)
    os.makedirs(paths.runs_dir, exist_ok=True)
    os.makedirs(paths.versions_dir, exist_ok=True)
    os.makedirs(paths.data_dir, exist_ok=True)

    template_id = str(getattr(template, "id", "") or "")
    template_name = str(getattr(template, "name", "") or "template")
    prompt = str(getattr(template, "prompt", "") or "")
    config_snapshot = getattr(template, "config_snapshot", None) or {}

    # Write strategy.py with actual template implementation
    strategy_code = get_template_strategy_code(template_id, template_name, prompt)
    strategy_py_path = os.path.join(paths.strategy_dir, "strategy.py")
    with open(strategy_py_path, "w", encoding="utf-8") as f:
        f.write(strategy_code)

    # Write strategy_spec.yaml with template parameters
    spec_data = {
        "engine_type": "vectorized",
        "entrypoint": {
            "module": "strategy.py",
            "function": "generate_signals",
        },
        "signal_mode": "target_weights",
        "params": config_snapshot.get("params", config_snapshot),
    }
    spec_path = os.path.join(paths.strategy_dir, "strategy_spec.yaml")
    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(_format_yaml(spec_data))

    # Write strategy_protocol.json
    protocol_path = os.path.join(paths.strategy_dir, "strategy_protocol.json")
    with open(protocol_path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_STRATEGY_PROTOCOL, f, ensure_ascii=False, indent=2, sort_keys=True)

    # Initialize Git repository and commit initial code
    init_git_repo(paths.strategy_dir)
    git_commit(paths.strategy_dir, f"Forked from template: {template_name}")

    # Snapshot to versions/{version_id}/
    snapshot_current_strategy_to_version(workspaces_dir, strategy_id, version_id)

    return paths
