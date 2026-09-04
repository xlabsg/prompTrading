from __future__ import annotations

import json
import os
from typing import Any

import docker

from worker.settings import settings


_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "OKX_BASE_URL",
)


def build_backtest_environment(
    *,
    strategy_id: str,
    version_id: str,
    run_id: str,
    exchange: str,
    symbol: str,
    interval: str,
    start_ms: int | None,
    end_ms: int | None,
    run_params: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Build unified environment variables for backtest container execution."""
    env: dict[str, str] = {
        "STRATEGY_ID": strategy_id,
        "VERSION_ID": version_id,
        "RUN_ID": run_id,
        "WORKSPACES_DIR": "/workspaces",
        "RUN_PARAMS_JSON": json.dumps(run_params or {}, ensure_ascii=False),
        "EXCHANGE": exchange,
        "SYMBOL": symbol,
        "INTERVAL": interval,
        "START_MS": "" if start_ms is None else str(start_ms),
        "END_MS": "" if end_ms is None else str(end_ms),
    }

    # US Stock data provider configuration
    for key in (
        "US_STOCK_PROVIDER",
        "US_STOCK_FALLBACK_PROVIDER",
        "US_STOCK_FALLBACK",
        "US_STOCK_CACHE_DIR",
        "US_STOCK_CACHE_TTL_DAYS",
        "US_STOCK_MAX_RETRIES",
        "US_STOCK_RATE_LIMIT_SLEEP_S",
    ):
        val = os.getenv(key)
        if val is not None:
            env[key] = val

    # Shared market data cache configuration
    for key in (
        "MARKET_DATA_CACHE_DIR",
        "MARKET_DATA_CACHE_ENABLED",
        "MARKET_DATA_CACHE_TTL_S",
    ):
        val = os.getenv(key)
        if val is not None:
            env[key] = val

    # Network guard allowlist
    for key in (
        "NETWORK_GUARD_ENABLED",
        "NETWORK_ALLOWLIST",
    ):
        val = os.getenv(key)
        if val is not None:
            env[key] = val

    # Proxy settings
    for key in _PROXY_ENV_KEYS:
        val = os.getenv(key)
        if val is not None:
            env[key] = val

    return env


def execute_backtest_container(
    docker_client: docker.DockerClient,
    *,
    job_id: str,
    rds: Any = None,
    strategy_id: str,
    version_id: str,
    run_id: str,
    exchange: str,
    symbol: str,
    interval: str,
    start_ms: int | None,
    end_ms: int | None,
    run_params: dict[str, Any] | None = None,
    log_file_path: str,
    container_name: str | None = None,
) -> tuple[int, list[str]]:
    """Execute the backtest container with standardized environment, volumes, and timeouts."""
    from worker.main import _run_container_and_stream_logs

    env = build_backtest_environment(
        strategy_id=strategy_id,
        version_id=version_id,
        run_id=run_id,
        exchange=exchange,
        symbol=symbol,
        interval=interval,
        start_ms=start_ms,
        end_ms=end_ms,
        run_params=run_params,
    )
    name = container_name or f"backtest-{job_id}"

    return _run_container_and_stream_logs(
        docker_client,
        job_id=job_id,
        rds=rds,
        image=settings.worker_backtest_image,
        name=name,
        command=None,
        environment=env,
        volumes={
            settings.worker_workspaces_volume: {"bind": "/workspaces", "mode": "rw"},
        },
        network=settings.worker_docker_network,
        log_file_path=log_file_path,
        timeout_s=settings.worker_job_timeout_s,
    )


def load_backtest_metrics(run_dir: str) -> dict[str, Any]:
    """Read and validate metrics.json from run directory. Raises on missing or invalid payload."""
    metrics_path = os.path.join(run_dir, "metrics.json")
    if not os.path.isfile(metrics_path):
        raise FileNotFoundError(
            f"backtest_metrics_missing: {metrics_path} was not written by the runner. See artifact: backtest.log"
        )

    try:
        with open(metrics_path, "r", encoding="utf-8") as f:
            metrics_payload = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"backtest_metrics_unreadable: {type(e).__name__}: {e}") from e

    if not isinstance(metrics_payload, dict) or not metrics_payload:
        raise ValueError("backtest_metrics_empty: metrics.json did not contain a metrics object")

    return metrics_payload
