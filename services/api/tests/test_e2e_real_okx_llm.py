"""Extended E2E test against real external dependencies (LLM + OKX)."""

from __future__ import annotations

import os

import pytest

from tests.conftest import (
    E2EClient,
    last_30d_range_ms,
    wait_for_backtest_completion,
    wait_for_job_completion,
)


@pytest.mark.integration
@pytest.mark.e2e_extended
@pytest.mark.slow
@pytest.mark.timeout(3600)
@pytest.mark.skipif(
    os.getenv("E2E_REAL_EXTERNAL") not in {"1", "true", "TRUE", "yes", "YES"},
    reason="Set E2E_REAL_EXTERNAL=1 to enable real external E2E test",
)
def test_e2e_generate_and_backtest_real_okx_llm(e2e_client: E2EClient, e2e_strategy_id: str):
    if not (os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")):
        pytest.skip("No LLM API key configured in environment")

    start_ms, end_ms = last_30d_range_ms()

    prompt = os.getenv(
        "E2E_LLM_PROMPT",
        "Build a simple 1h trend strategy for BTC-USDT-SWAP using moving averages. "
        "Use clear entry/exit rules and basic risk management. "
        "Ensure generate_signals is implemented for backtesting.",
    )

    payload = e2e_client.post_json(
        f"/api/strategies/{e2e_strategy_id}/generate_and_backtest",
        {
            "prompt": prompt,
            "dataset": {
                "exchange": "okx",
                "symbol": "BTC-USDT-SWAP",
                "interval": "1h",
                "start_ms": start_ms,
                "end_ms": end_ms,
            },
            "params": {},
            "llm_meta": {},
        },
    )

    job_id = payload["job"]["id"]
    run_id = payload["backtest_run"]["id"]

    job = wait_for_job_completion(e2e_client, job_id, timeout_s=3600)
    assert job["status"] == "succeeded", f"Job failed: {job.get('error_message')}"

    run = wait_for_backtest_completion(e2e_client, run_id, timeout_s=3600)
    assert run["status"] == "succeeded", f"Backtest failed: {run.get('error_message')}"

    metrics = run.get("metrics") or {}
    for key in ("total_return", "max_drawdown", "sharpe_ratio", "win_rate"):
        assert key in metrics, f"Missing metric field: {key}"

    eq = e2e_client.get_json(f"/api/backtests/{run_id}/equity_curve")
    assert isinstance(eq.get("data"), list) and len(eq["data"]) > 0

    files = e2e_client.get_json(f"/api/strategies/{e2e_strategy_id}/files").get("files", [])
    strategy_py = next((f for f in files if f.get("name") == "strategy.py"), None)
    assert strategy_py is not None, "Missing strategy.py"
    content = strategy_py.get("content") or ""
    assert "def generate_signals" in content, "Generated strategy.py missing generate_signals()"
    overview_md = next((f for f in files if f.get("name") == "overview.md"), None)
    assert overview_md is not None, "Missing overview.md"
    overview_content = (overview_md.get("content") or "").strip()
    assert overview_content, "overview.md is empty"
    assert "# Summary" in overview_content
    assert "# Trading Board" in overview_content
    assert "# Flow Animation" in overview_content
