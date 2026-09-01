"""Core E2E workflow tests (real worker + real API over HTTP).

Focus:
- strategy generation (fallback/no-LLM)
- OKX backtest (BTC-USDT-SWAP, 1h, last 30 days)
"""

from __future__ import annotations

import json

import pytest
import requests

from tests.conftest import (
    E2EClient,
    last_30d_range_ms,
    wait_for_backtest_completion,
    wait_for_job_completion,
)


@pytest.mark.integration
@pytest.mark.e2e_core
@pytest.mark.timeout(1200)  # backtest + Docker jobs can be slow
def test_e2e_generate_and_backtest_with_fallback(e2e_client: E2EClient, e2e_strategy_id: str):
    start_ms, end_ms = last_30d_range_ms()

    request_data = {
        "prompt": "Simple moving average crossover strategy",
        "dataset": {
            "exchange": "okx",
            "symbol": "BTC-USDT-SWAP",
            "interval": "1h",
            "start_ms": start_ms,
            "end_ms": end_ms,
        },
        "params": {"fast": 10, "slow": 30},
        # Force fallback if any LLM call fails or isn't configured.
        "llm_meta": {"fallback_on_error": True},
    }

    payload = e2e_client.post_json(f"/api/strategies/{e2e_strategy_id}/generate_and_backtest", request_data)
    job_id = payload["job"]["id"]
    run_id = payload["backtest_run"]["id"]

    job = wait_for_job_completion(e2e_client, job_id, timeout_s=1200)
    assert job["status"] == "succeeded", f"Job failed: {job.get('error_message')}"

    run = wait_for_backtest_completion(e2e_client, run_id, timeout_s=1200)
    assert run["status"] == "succeeded", f"Backtest failed: {run.get('error_message')}"

    metrics = run.get("metrics") or {}
    for key in ("total_return", "max_drawdown", "sharpe_ratio", "win_rate"):
        assert key in metrics, f"Missing metric field: {key}"

    eq = e2e_client.get_json(f"/api/backtests/{run_id}/equity_curve")
    assert isinstance(eq.get("data"), list) and len(eq["data"]) > 0

    # Trades / orders / positions artifacts should be available on successful runs.
    trades = e2e_client.get_json(f"/api/backtests/{run_id}/trades")
    assert isinstance(trades.get("trades"), list)
    if trades["trades"]:
        t0 = trades["trades"][0]
        for key in ("side", "entry_price", "exit_price", "entry_time_ms", "exit_time_ms", "holding_time_ms"):
            assert key in t0

    orders = e2e_client.get_json(f"/api/backtests/{run_id}/orders")
    assert isinstance(orders.get("orders"), list)
    if orders["orders"]:
        o0 = orders["orders"][0]
        for key in ("side", "qty", "price", "time_ms", "weight_from", "weight_to", "signal_type", "signal_reason", "signal_source", "signal_detail"):
            assert key in o0

    positions = e2e_client.get_json(f"/api/backtests/{run_id}/positions")
    assert isinstance(positions.get("positions"), list)
    if positions["positions"]:
        p0 = positions["positions"][0]
        for key in ("side", "entry_price", "exit_price", "entry_qty", "max_qty", "holding_time_ms"):
            assert key in p0

    signal_events = e2e_client.get_json(f"/api/backtests/{run_id}/signals/events")
    assert isinstance(signal_events.get("events"), list)
    if signal_events["events"]:
        e0 = signal_events["events"][0]
        for key in ("time_ms", "type", "side", "signal_reason", "signal_detail", "weight_from", "weight_to", "price"):
            assert key in e0

    # Validate generated code artifact exists (fallback still generates code).
    files = e2e_client.get_json(f"/api/strategies/{e2e_strategy_id}/files").get("files", [])
    strategy_py = next((f for f in files if f.get("name") == "strategy.py"), None)
    assert strategy_py is not None, "Missing strategy.py"
    content = (strategy_py.get("content") or "").strip()
    assert "def generate_signals" in content, "strategy.py missing generate_signals()"
    overview_md = next((f for f in files if f.get("name") == "overview.md"), None)
    assert overview_md is not None, "Missing overview.md"
    overview_content = (overview_md.get("content") or "").strip()
    assert overview_content, "overview.md is empty"
    assert "# Summary" in overview_content
    assert "# Trading Board" in overview_content
    assert "# Flow Animation" in overview_content

    # Artifacts: presence depends on the run, but these should generally exist on success.
    artifacts = e2e_client.get_json(f"/api/backtests/{run_id}/artifacts")
    assert isinstance(artifacts, list)
    for name in ("metrics.json", "equity_curve.json", "run_meta.json"):
        assert name in artifacts, f"Missing artifact: {name}"

    # Log metrics for human review in CI logs.
    print("\n[metrics]\n" + json.dumps(metrics, indent=2))


@pytest.mark.integration
@pytest.mark.e2e_core
def test_invalid_dataset_parameters(e2e_client: E2EClient, e2e_strategy_id: str):
    base = f"/api/strategies/{e2e_strategy_id}/generate_and_backtest"

    res = e2e_client.request(
        "POST",
        base,
        json={"prompt": "Test strategy", "dataset": {"exchange": "invalid_exchange", "symbol": "BTC-USDT-SWAP", "interval": "1h"}},
    )
    assert res.status_code == 400

    res = e2e_client.request(
        "POST",
        base,
        json={"prompt": "Test strategy", "dataset": {"exchange": "okx", "symbol": "", "interval": "1h"}},
    )
    assert res.status_code == 400

    res = e2e_client.request(
        "POST",
        base,
        json={"prompt": "Test strategy", "dataset": {"exchange": "okx", "symbol": "BTC-USDT-SWAP", "interval": ""}},
    )
    assert res.status_code == 400


@pytest.mark.integration
@pytest.mark.e2e_core
def test_strategy_not_found(e2e_client: E2EClient):
    fake_strategy_id = "00000000-0000-0000-0000-000000000000"
    res = e2e_client.request(
        "POST",
        f"/api/strategies/{fake_strategy_id}/generate_and_backtest",
        json={"prompt": "Test strategy", "dataset": {"exchange": "okx", "symbol": "BTC-USDT-SWAP", "interval": "1h"}},
    )
    # Some endpoints prefer to hide existence and return 403 for non-members.
    assert res.status_code in (403, 404)


@pytest.mark.integration
@pytest.mark.e2e_core
def test_unauthorized_access(e2e_api_base_url: str, e2e_strategy_id: str):
    # No cookies (fresh session).
    sess = requests.Session()
    try:
        res = sess.post(
            f"{e2e_api_base_url}/api/strategies/{e2e_strategy_id}/generate_and_backtest",
            json={"prompt": "Test strategy", "dataset": {"exchange": "okx", "symbol": "BTC-USDT-SWAP", "interval": "1h"}},
            timeout=30,
        )
        assert res.status_code == 401
    finally:
        sess.close()


@pytest.mark.integration
@pytest.mark.e2e_core
def test_concurrent_job_limit(e2e_client: E2EClient, e2e_strategy_id: str):
    start_ms, end_ms = last_30d_range_ms()
    base = f"/api/strategies/{e2e_strategy_id}/generate_and_backtest"

    first = e2e_client.request(
        "POST",
        base,
        json={
            "prompt": "First strategy",
            "dataset": {"exchange": "okx", "symbol": "BTC-USDT-SWAP", "interval": "1h", "start_ms": start_ms, "end_ms": end_ms},
            "llm_meta": {"fallback_on_error": True},
        },
        timeout=60,
    )
    assert first.status_code == 200, first.text

    second = e2e_client.request(
        "POST",
        base,
        json={
            "prompt": "Second strategy",
            "dataset": {"exchange": "okx", "symbol": "BTC-USDT-SWAP", "interval": "1h", "start_ms": start_ms, "end_ms": end_ms},
            "llm_meta": {"fallback_on_error": True},
        },
        timeout=60,
    )

    # Depending on worker speed, the first job may finish before this request lands.
    if second.status_code == 409:
        assert "job_already_running" in (second.json().get("detail") or "")
    else:
        assert second.status_code == 200, second.text


@pytest.fixture(autouse=True)
def _print_test_separator(request):
    print("\n" + "=" * 80)
    print(f"TEST: {request.node.name}")
    print("=" * 80)
