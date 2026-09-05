from __future__ import annotations

import logging
import os

import docker
from docker.errors import NotFound

from worker.settings import settings

logger = logging.getLogger(__name__)

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


def get_live_trading_container_name(session_id: str) -> str:
    return f"live-trading-{session_id}"


def start_live_trading_container(
    docker_client: docker.DockerClient,
    *,
    session_id: str,
    strategy_id: str,
    exchange: str = "okx",
    symbol: str = "BTC-USDT",
    interval: str = "1m",
    api_internal_url: str = "http://api:8000",
) -> str:
    """Launch an isolated daemon Docker container for live strategy execution."""
    container_name = get_live_trading_container_name(session_id)

    # Clean up any existing dead container with same name
    try:
        old_container = docker_client.containers.get(container_name)
        logger.info(f"Removing pre-existing container {container_name} (status={old_container.status})")
        old_container.stop(timeout=2)
        old_container.remove(force=True)
    except NotFound:
        pass
    except Exception as e:
        logger.warning(f"Error while cleaning up old container {container_name}: {e}")

    env: dict[str, str] = {
        "SESSION_ID": session_id,
        "STRATEGY_ID": strategy_id,
        "EXCHANGE": exchange,
        "SYMBOL": symbol,
        "INTERVAL": interval,
        "API_INTERNAL_URL": api_internal_url,
        "WORKSPACES_DIR": "/workspaces",
    }

    # Pass proxy settings if configured
    proxy_val = os.getenv("CONTAINER_HTTP_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    if proxy_val:
        proxy_val = proxy_val.replace("127.0.0.1", "host.docker.internal").replace("localhost", "host.docker.internal")
        for k in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            env[k] = proxy_val
    for k in _PROXY_ENV_KEYS:
        val = os.getenv(k)
        if val is not None and k not in env:
            env[k] = val

    logger.info(f"Spawning live trading container: {container_name} for session={session_id}")
    run_kwargs: dict = {
        "image": settings.worker_backtest_image,
        "name": container_name,
        "command": ["python", "-m", "live_trading_sdk.live_container_runner"],
        "environment": env,
        "volumes": {
            settings.worker_workspaces_volume: {"bind": "/workspaces", "mode": "rw"},
        },
        "network": settings.worker_docker_network,
        "mem_limit": "512m",
        "pids_limit": 100,
        "detach": True,
        "restart_policy": {"Name": "on-failure", "MaximumRetryCount": 3},
    }
    sandbox_runtime = settings.sandbox_runtime or os.getenv("SANDBOX_RUNTIME")
    if sandbox_runtime:
        run_kwargs["runtime"] = sandbox_runtime

    container = docker_client.containers.run(**run_kwargs)
    logger.info(f"Live trading container {container_name} successfully started in background (id={container.id})")
    return str(container.id)


def stop_live_trading_container(
    docker_client: docker.DockerClient,
    *,
    session_id: str,
) -> None:
    """Stop and remove a running live trading container."""
    container_name = get_live_trading_container_name(session_id)
    try:
        container = docker_client.containers.get(container_name)
        logger.info(f"Stopping live trading container {container_name}...")
        container.stop(timeout=5)
        container.remove(force=True)
        logger.info(f"Live trading container {container_name} removed")
    except NotFound:
        logger.info(f"Live trading container {container_name} not found, nothing to stop")
    except Exception as e:
        logger.error(f"Failed to stop live trading container {container_name}: {e}")
        raise
