"""Strategy adapter utilities for migrating strategies.

This module provides tools to help adapt trading_view_script strategies
to the new platform format.
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any


def convert_yaml_config_to_spec(
    yaml_path: str | Path,
    strategy_name: str,
) -> dict[str, Any]:
    """Convert a trading_view_script YAML config to strategy_spec.yaml.

    Args:
        yaml_path: Path to the original YAML config
        strategy_name: Name for the new strategy

    Returns:
        Dictionary suitable for writing to strategy_spec.yaml
    """
    yaml_path = Path(yaml_path)
    with open(yaml_path) as f:
        original_config = yaml.safe_load(f)

    # Map original config to new format
    spec = {
        "name": strategy_name,
        "description": f"Migrated from {yaml_path.name}",
        "version": "1.0.0",
        "entrypoint": {
            "function": "create_live_strategy",
        },
        "params": {
            # Trading parameters
            "live_bar_interval": _map_interval(original_config.get("interval", "1H")),
            "live_history_bars": 150,

            # Exchange and symbol
            "exchange": original_config.get("exchange", "okx"),
            "symbol": original_config.get("instrument", "BTC-USDT-SWAP"),

            # Strategy-specific parameters (extract from original)
            **_extract_strategy_params(original_config),
        },
    }

    return spec


def _map_interval(original_interval: str) -> str:
    """Map interval format from trading_view_script to platform format."""
    interval_map = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1H": "1H",
        "4H": "4H",
        "1D": "1D",
    }
    return interval_map.get(original_interval, original_interval)


def _extract_strategy_params(config: dict[str, Any]) -> dict[str, Any]:
    """Extract strategy-specific parameters from config.

    This extracts common parameter sections from the original config.
    """
    params = {}

    # Entry configuration
    if "entry" in config:
        entry = config["entry"]
        params["entry_mode"] = entry.get("mode", "signal_range")
        params["max_wait_candles"] = entry.get("max_wait_candles", 2)

    # Trading configuration
    if "trading" in config:
        trading = config["trading"]
        params["order_notional_usdt"] = trading.get("order_notional_usdt", 50)
        params["leverage"] = trading.get("leverage", 1)
        params["margin_mode"] = trading.get("margin_mode", "isolated")

        # Close chase configuration
        if "close_chase" in trading:
            close_chase = trading["close_chase"]
            if "stop_loss" in close_chase:
                params["sl_chase_enabled"] = close_chase["stop_loss"].get("enabled", False)
                params["sl_fallback_to_market"] = close_chase["stop_loss"].get("fallback_to_market", True)

    # Filters
    if "filters" in config:
        filters = config["filters"]
        if "trend" in filters:
            trend = filters["trend"]
            params["trend_filter_enabled"] = trend.get("enabled", False)
            params["trend_filter_indicator"] = trend.get("indicator", "macd")

        if "funding_rate" in filters:
            funding = filters["funding_rate"]
            params["funding_filter_enabled"] = funding.get("enabled", False)
            params["funding_rate_threshold"] = funding.get("threshold", 0.01)

    # Risk management
    if "risk" in config:
        risk = config["risk"]
        params["max_position_size"] = risk.get("max_position_size", 1.0)
        params["min_risk_reward"] = risk.get("min_risk_reward", 1.5)

    return params


def create_strategy_skeleton(
    template_name: str,
    output_path: str | Path,
    metadata: dict[str, Any],
) -> None:
    """Create a skeleton strategy template directory.

    Args:
        template_name: Name of the template (e.g., "divergence")
        output_path: Base path for templates directory
        metadata: Template metadata dict
    """
    output_path = Path(output_path)
    template_dir = output_path / template_name

    # Create directory structure
    (template_dir / "indicators").mkdir(parents=True, exist_ok=True)
    (template_dir / "tests").mkdir(exist_ok=True)

    # Create __init__.py
    init_content = f'''"""{template_name.title()} strategy template."""

from strategy_templates.base import BaseTemplateStrategy, TemplateMetadata
from live_trading_sdk import Bar, Broker, StrategyContext
import pandas as pd


class {template_name.title().replace("_", "")}Strategy(BaseTemplateStrategy):
    """{metadata.get("description", template_name.title() + " strategy")}"""

    metadata = TemplateMetadata(
        name="{template_name}",
        description="{metadata.get("description", "")}",
        version="1.0.0",
        author="PromptTrading",
        tags={metadata.get("tags", [])},
        risk_level="{metadata.get("risk_level", "medium")}",
        trading_frequency="{metadata.get("trading_frequency", "intraday")}",
        complexity_score={metadata.get("complexity_score", 3)},
    )

    def initialize(self, context: StrategyContext) -> None:
        super().initialize(context)
        # TODO: Initialize strategy-specific state

    def on_bar(self, bar: Bar, history: pd.DataFrame, broker: Broker) -> None:
        # TODO: Implement strategy logic
        pass


def create_live_strategy() -> {template_name.title().replace("_", "")}Strategy:
    """Factory function for live trading."""
    return {template_name.title().replace("_", "")}Strategy()
'''

    (template_dir / "__init__.py").write_text(init_content)

    # Create strategy_spec.yaml
    spec_content = f'''# {template_name.title()} Strategy Configuration

name: {template_name}
description: {metadata.get("description", "")}
version: 1.0.0

entrypoint:
  function: create_live_strategy

params:
  live_bar_interval: "1H"
  live_history_bars: 150

  # TODO: Add strategy-specific parameters
'''

    (template_dir / "strategy_spec.yaml").write_text(spec_content)

    # Create README.md
    readme_content = f'''# {template_name.title()} Strategy

{metadata.get("description", "")}

## Strategy Overview

- **Risk Level**: {metadata.get("risk_level", "medium")}
- **Trading Frequency**: {metadata.get("trading_frequency", "intraday")}
- **Complexity**: {metadata.get("complexity_score", 3)}/5

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| TODO | TODO | TODO |

## Usage

```python
from strategy_templates.templates.{template_name} import create_live_strategy

strategy = create_live_strategy()
```

## Performance

TODO: Add backtest results after migration.
'''

    (template_dir / "README.md").write_text(readme_content)

    print(f"Created skeleton for '{template_name}' at {template_dir}")
