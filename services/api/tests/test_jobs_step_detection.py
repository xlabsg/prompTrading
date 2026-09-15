from __future__ import annotations

from app.routers.jobs import _detect_step_from_line


def test_startup_dataset_config_line_is_not_a_backtest() -> None:
    """The dataset config line must not advance the pipeline to `running_backtest`.

    `runner_v2` prints `[agent] backtest dataset=... budget=...` before the agent
    authors anything. It configures the in-loop backtest; it does not run one. The
    console's four-step ladder is monotonic, so treating it as a run pinned the
    pipeline to the backtest step for the whole authoring turn.
    """
    line = "[agent] backtest dataset=okx BTC-USDT-SWAP 1h 2024-01-01..2024-02-01 budget=1"

    assert _detect_step_from_line(line) is None


def test_initializing_config_lines_still_map_to_the_first_step() -> None:
    assert _detect_step_from_line("[agent] seeded workspace with: ['strategy_spec.yaml']") == "initializing_agent"
    assert _detect_step_from_line("[agent] tau provider=deepseek model=deepseek-chat") == "initializing_agent"


def test_empty_line_maps_to_nothing() -> None:
    assert _detect_step_from_line("") is None
