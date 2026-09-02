"""Strategy-authoring domain layer for the coding agent.

The agent loop itself is Tau (`tau-ai`); this package supplies what only this
platform knows: the strategy file protocol, the in-loop backtest tool and its run
budget, the prompts, and the driver that runs a Tau session and decides when its
output is publishable.

Only the protocol is re-exported here. The other modules pull in pandas, the
backtest engine or Tau itself, and importing this package must stay cheap enough
for a caller that only wants `agent.tau_driver` -- which depends on nothing
beyond the standard library.
"""

from agent.protocol import (
    OVERVIEW_FILE,
    PROTOCOL,
    SPEC_FILE,
    STRATEGY_FILE,
    STRATEGY_FUNCTION,
    StrategyProtocol,
)

__all__ = [
    "StrategyProtocol",
    "PROTOCOL",
    "STRATEGY_FILE",
    "STRATEGY_FUNCTION",
    "OVERVIEW_FILE",
    "SPEC_FILE",
]
