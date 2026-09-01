"""Strategy Protocol Constants.

Defines the standard file naming conventions and entry points for strategies.
This is the single source of truth for strategy file structure.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyProtocol:
    """Strategy file naming protocol.

    These are the standard conventions for strategy workspaces.
    All agent components should reference these constants rather than hardcoding.
    """

    # Entry point
    entry_file: str = "strategy.py"
    entry_function: str = "generate_signals"

    # Documentation
    overview_file: str = "overview.md"
    readme_file: str = "README.md"

    # Configuration
    spec_file: str = "strategy_spec.yaml"
    params_schema_file: str = "params_schema.json"
    backtest_config_file: str = "backtest_config.json"

    # Metadata
    meta_file: str = "strategy_meta.json"
    explain_file: str = "strategy_explain.json"

    # Overview requirements
    overview_required_marker: str = "```mermaid"


# Default protocol instance - import this in other modules
PROTOCOL = StrategyProtocol()

# Convenience aliases for common use
STRATEGY_FILE = PROTOCOL.entry_file
STRATEGY_FUNCTION = PROTOCOL.entry_function
OVERVIEW_FILE = PROTOCOL.overview_file
SPEC_FILE = PROTOCOL.spec_file
