from __future__ import annotations

import json
import os
import subprocess
import shutil
import time
import traceback
import re
import logging
import logging.config
import threading
import uuid
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional

import docker
from docker.types import Ulimit
import redis
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text, or_, update
from sqlalchemy.orm import Session

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.enums import BacktestStatus, ChatStatus, JobStatus, JobType, TrendingSourceType, TradingSessionStatus
from control_plane.models import Base, BacktestRun, Dataset, Job, Strategy, StrategyVersion, Repository, RepoSync, TradingViewTrendingStrategy, TrendingSchedule, TemplatePerformanceSchedule, TradingSession
from control_plane.queue import QUEUE_NAME, job_log_channel
from control_plane.workspaces import git_commit, init_git_repo
from worker.settings import settings
from worker.repo_sync import clone_or_update, ensure_worktree
from worker.github_app import get_installation_token
from worker.template_performance_job import generate_template_performance_data
from worker.backtest_runner import execute_backtest_container, load_backtest_metrics


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


AGENT_RUNNER_V2_COMMAND = ["python", "-m", "agent.runner_v2"]
STRATEGY_NAME_MAX_CHARS = 20


def _configure_logging(log_dir: str, service_name: str) -> None:
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{service_name}.log")
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            }
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "filename": log_path,
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "root": {"level": "INFO", "handlers": ["stdout", "file"]},
    }
    logging.config.dictConfig(log_config)


_configure_logging(settings.log_dir, "worker")


def _wait_for_db(db_url: str, timeout_s: float = 90.0) -> None:
    """Wait for database to be ready with retry logic."""
    deadline = time.monotonic() + timeout_s
    last_err: Exception | None = None
    attempt = 0
    while time.monotonic() < deadline:
        try:
            engine = create_db_engine(db_url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"[worker] Database connection successful (attempt {attempt + 1})")
            return
        except Exception as e:
            last_err = e
            attempt += 1
            print(f"[worker] DB connection attempt {attempt} failed: {e}")
            time.sleep(1.0)
    raise RuntimeError(f"db_not_ready after {attempt} attempts") from last_err


try:
    import psutil
except ImportError:
    psutil = None
from control_plane.queue import (
    get_file_queue,
    enqueue_job,
    is_job_cancelled,
)


def _check_system_resources_available(min_available_mb: int = 256) -> bool:
    if psutil is None:
        return True
    try:
        vm = psutil.virtual_memory()
        available_mb = vm.available / (1024 * 1024)
        if available_mb < min_available_mb:
            logging.warning(
                f"[worker] Low memory warning: {available_mb:.1f} MB available (threshold: {min_available_mb} MB). Throttling job dequeue."
            )
            return False
        return True
    except Exception:
        return True


def _wait_for_redis(redis_url: str | None, timeout_s: float = 10.0) -> Optional[redis.Redis]:
    if not redis_url:
        return None
    try:
        rds = redis.Redis.from_url(redis_url, decode_responses=True)
        deadline = time.monotonic() + timeout_s
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            try:
                rds.ping()
                return rds
            except Exception as e:
                last_err = e
                time.sleep(0.5)
        print(f"[worker] Redis not reachable ({last_err}), proceeding in zero-redis file queue mode.")
        return None
    except Exception as e:
        print(f"[worker] Redis initialization skipped ({e}).")
        return None


LOG_TAIL_KEY_PREFIX = "jobs:logtail:v1:"
LAST_LOG_KEY_PREFIX = "jobs:lastlog:v1:"
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


def _publish_event(job_id: str, event: dict[str, Any]) -> None:
    try:
        log_dir = os.path.join(settings.app_workspaces_dir, ".queue", "logs")
        _safe_mkdir(log_dir)
        events_path = os.path.join(log_dir, f"{job_id}.events.jsonl")
        if "ts" not in event:
            event["ts"] = time.time()
        with open(events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
    except Exception:
        pass


def _publish_log(job_id: Any, message: str, rds: Optional[Any] = None) -> None:
    # Handle swapped args: _publish_log(rds, job_id, message)
    if isinstance(message, str) and not isinstance(job_id, str):
        actual_job_id = message
        actual_message = str(rds) if rds is not None else ""
        actual_rds = job_id if hasattr(job_id, "publish") else None
        job_id = actual_job_id
        message = actual_message
        rds = actual_rds

    job_id = str(job_id)

    # Always append to local file queue log: /workspaces/.queue/logs/{job_id}.log
    try:
        log_dir = os.path.join(settings.app_workspaces_dir, ".queue", "logs")
        _safe_mkdir(log_dir)
        log_path = os.path.join(log_dir, f"{job_id}.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(message + "\n")
            f.flush()
    except Exception:
        pass

    # If message is a structured event from the agent container, also append to .events.jsonl
    if message.startswith("[agent:event] "):
        try:
            evt_json = json.loads(message[len("[agent:event] "):])
            if isinstance(evt_json, dict):
                _publish_event(job_id, evt_json)
        except Exception:
            pass
    elif message.startswith("[agent] 大模型思考"):
        _publish_event(job_id, {
            "type": "progress",
            "stage": "thinking",
            "message": "大模型思考与逻辑推演中...",
        })
    elif message.startswith("[agent] tool "):
        # Fallback structured event extraction
        match = re.match(r"^\[agent\] tool (\S+)(?: path=(\S+))? (\.\.\.|ok|error)$", message)
        if match:
            tool, path, phase_str = match.groups()
            if phase_str == "...":
                fname = os.path.basename(path) if path else ""
                if tool == "backtest":
                    msg = "正在进行历史数据回测计算..."
                elif tool == "bash":
                    msg = "正在执行沙箱语法与未来函数审计..."
                elif tool == "task_done":
                    msg = "策略生成完毕，正在发布交付物..."
                elif tool in {"edit_file", "write_file", "edit", "write"}:
                    msg = f"正在修改 {fname}..." if fname else "正在修改代码..."
                elif tool in {"read_file", "read"}:
                    msg = f"正在阅读 {fname}..." if fname else "正在读取文件..."
                else:
                    msg = f"正在执行 {tool}..."
                _publish_event(job_id, {
                    "type": "tool_start",
                    "tool": tool,
                    "path": fname,
                    "phase": "tool_start",
                    "message": msg,
                })
            else:
                end_msg = None
                if tool == "backtest":
                    end_msg = "回测计算完成，正在评估指标..." if phase_str == "ok" else "回测执行失败"
                _publish_event(job_id, {
                    "type": "tool_end",
                    "tool": tool,
                    "success": phase_str == "ok",
                    "message": end_msg,
                })

    # Optional Redis fallback/mirroring
    if rds is not None and hasattr(rds, "publish"):
        try:
            rds.publish(job_log_channel(job_id), message)
            pipe = rds.pipeline()
            tail_key = f"{LOG_TAIL_KEY_PREFIX}{job_id}"
            pipe.rpush(tail_key, message)
            pipe.ltrim(tail_key, -200, -1)
            pipe.expire(tail_key, 86400)
            pipe.setex(f"{LAST_LOG_KEY_PREFIX}{job_id}", 86400, message)
            pipe.execute()
        except Exception:
            pass


def _mark_job_log_done(job_id: str, status: Optional[str] = None, error_message: Optional[str] = None) -> None:
    try:
        log_dir = os.path.join(settings.app_workspaces_dir, ".queue", "logs")
        _safe_mkdir(log_dir)
        events_path = os.path.join(log_dir, f"{job_id}.events.jsonl")
        done_marker = os.path.join(log_dir, f"{job_id}.log.done")

        # Check if events.jsonl already has a done event
        has_done = False
        if os.path.isfile(events_path):
            try:
                with open(events_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if '"type": "done"' in line:
                            has_done = True
                            break
            except Exception:
                pass

        if not has_done:
            _publish_event(job_id, {
                "type": "done",
                "status": status or "succeeded",
                "error_message": error_message or "",
            })

        with open(done_marker, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except Exception:
        pass


def _is_cancel_requested(job_id: Any, rds: Optional[Any] = None) -> bool:
    if isinstance(rds, str) and not isinstance(job_id, str):
        actual_job_id = rds
        actual_rds = job_id
        job_id = actual_job_id
        rds = actual_rds
    return is_job_cancelled(settings.app_workspaces_dir, str(job_id), redis_client=rds)


def _raise_if_cancelled(job_id: Any, rds: Optional[Any] = None) -> None:
    if _is_cancel_requested(job_id, rds=rds):
        raise RuntimeError("job_cancelled")


def _safe_mkdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _tail_excerpt(lines: list[str], *, max_lines: int = 20, max_chars: int = 2000) -> str:
    if not lines:
        return "<no logs captured>"
    text = "\n".join(lines[-max_lines:])
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


def _ensure_strategy_repo(strategy_dir: str) -> None:
    os.makedirs(strategy_dir, exist_ok=True)
    init_git_repo(strategy_dir)


def _agent_sandbox_options() -> dict[str, Any]:
    opts: dict[str, Any] = {}
    if settings.agent_memory_limit_mb and settings.agent_memory_limit_mb > 0:
        opts["mem_limit"] = int(settings.agent_memory_limit_mb) * 1024 * 1024
    if settings.agent_cpu_limit and settings.agent_cpu_limit > 0:
        opts["nano_cpus"] = int(float(settings.agent_cpu_limit) * 1_000_000_000)
    if settings.agent_pids_limit and settings.agent_pids_limit > 0:
        opts["pids_limit"] = int(settings.agent_pids_limit)
    if settings.agent_read_only:
        opts["read_only"] = True
        size_mb = int(settings.agent_tmpfs_size_mb or 0)
        if size_mb > 0:
            opts["tmpfs"] = {"/tmp": f"rw,noexec,nosuid,size={size_mb}m"}
    opts["ulimits"] = [
        Ulimit(name="nofile", soft=4096, hard=4096),
        Ulimit(name="nproc", soft=int(settings.agent_pids_limit or 256), hard=int(settings.agent_pids_limit or 256)),
    ]
    return opts


def _run_container_and_stream_logs(
    client: docker.DockerClient,
    *,
    job_id: str,
    rds: Optional[redis.Redis] = None,
    image: str,
    name: str,
    command: Optional[list[str]] = None,
    environment: Optional[dict[str, str]] = None,
    volumes: Optional[dict[str, dict[str, str]]] = None,
    network: Optional[str] = None,
    labels: Optional[dict[str, str]] = None,
    detach: bool = True,
    remove: bool = True,
    log_file_path: Optional[str] = None,
    tail_max_lines: int = 200,
    timeout_s: int | None = None,
    idle_timeout_s: int | None = None,
    mem_limit: int | str | None = None,
    nano_cpus: int | None = None,
    read_only: bool | None = None,
    tmpfs: Optional[dict[str, str]] = None,
    ulimits: Optional[list[Ulimit]] = None,
    pids_limit: int | None = None,
) -> tuple[int, list[str]]:
    tail: deque[str] = deque(maxlen=max(1, int(tail_max_lines)))
    log_f = None
    if log_file_path:
        _safe_mkdir(os.path.dirname(log_file_path))
        log_f = open(log_file_path, "w", encoding="utf-8")

    env = dict(environment or {})
    proxy_val = os.getenv("CONTAINER_HTTP_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    if proxy_val:
        proxy_val = proxy_val.replace("127.0.0.1", "host.docker.internal").replace("localhost", "host.docker.internal")
        for k in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            if k not in env:
                env[k] = proxy_val
    env.setdefault("no_proxy", "127.0.0.1,localhost,api,redis,worker,web,e2e-runner,host.docker.internal")
    env.setdefault("NO_PROXY", "127.0.0.1,localhost,api,redis,worker,web,e2e-runner,host.docker.internal")

    run_kwargs: dict[str, Any] = {
        "image": image,
        "name": name,
        "command": command,
        "environment": env,
        "volumes": volumes or {},
        "network": network,
        "labels": labels or {},
        "detach": detach,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "pids_limit": pids_limit if pids_limit is not None else 512,
        "extra_hosts": {"host.docker.internal": "host-gateway"},
    }
    if mem_limit is not None:
        run_kwargs["mem_limit"] = mem_limit
    if nano_cpus is not None:
        run_kwargs["nano_cpus"] = nano_cpus
    if read_only is not None:
        run_kwargs["read_only"] = read_only
    if tmpfs:
        run_kwargs["tmpfs"] = tmpfs
    if ulimits:
        run_kwargs["ulimits"] = ulimits

    # Support gVisor (runsc) or custom container runtime for sandboxing
    sandbox_runtime = settings.sandbox_runtime or os.getenv("SANDBOX_RUNTIME")
    if sandbox_runtime:
        run_kwargs["runtime"] = sandbox_runtime

    if name:
        try:
            existing = client.containers.get(name)
            try:
                existing.remove(force=True)
            except Exception:
                pass
        except Exception:
            pass

    container = client.containers.run(**run_kwargs)
    stop_event = threading.Event()
    last_activity = [time.monotonic()]
    resolved_idle_timeout = idle_timeout_s if idle_timeout_s is not None else getattr(settings, "container_idle_timeout_s", 120)

    def _stream_logs() -> None:
        try:
            for raw in container.logs(stream=True, follow=True, stdout=True, stderr=True):
                if stop_event.is_set():
                    break
                try:
                    line = raw.decode("utf-8", errors="replace").rstrip("\n")
                except Exception:
                    line = str(raw)
                if not line:
                    continue
                last_activity[0] = time.monotonic()
                tail.append(line)
                _publish_log(job_id, line, rds=rds)
                if log_f is not None:
                    log_f.write(line + "\n")
        except BaseException:
            # Log streaming failures are non-fatal; the main thread decides job status.
            pass

    t = threading.Thread(target=_stream_logs, name=f"job-log-{job_id[:8]}", daemon=True)
    t.start()

    exit_code = 1
    start = time.monotonic()
    try:
        while True:
            try:
                container.reload()
            except Exception:
                # If the daemon or container disappears, treat as failure and let cleanup run.
                break

            if _is_cancel_requested(job_id, rds=rds):
                _publish_log(job_id, "[worker] job_cancelled: killing container", rds=rds)
                try:
                    container.kill()
                except Exception:
                    pass
                exit_code = 125
                break

            if container.status in ("exited", "dead"):
                try:
                    res = container.wait()
                    exit_code = int(res.get("StatusCode", 1))
                except Exception:
                    exit_code = 1
                break

            now = time.monotonic()
            # 1. Idle timeout: detect genuine hangs/deadlocks when zero output is returned
            idle_elapsed = now - last_activity[0]
            if resolved_idle_timeout is not None and idle_elapsed > float(resolved_idle_timeout):
                _publish_log(
                    job_id,
                    f"[worker] job_idle_timeout: container silent for {idle_elapsed:.0f}s (no data returning), killing container",
                    rds=rds,
                )
                try:
                    container.kill()
                except Exception:
                    pass
                exit_code = 124
                break

            # 2. Hard ceiling: safety boundary against infinite loops
            if timeout_s is not None and (now - start) > float(timeout_s):
                _publish_log(
                    job_id,
                    f"[worker] job_timeout: hard timeout ceiling reached ({timeout_s}s), killing container",
                    rds=rds,
                )
                try:
                    container.kill()
                except Exception:
                    pass
                exit_code = 124
                break

            time.sleep(0.5)

        return exit_code, list(tail)
    finally:
        _mark_job_log_done(job_id, status="succeeded" if exit_code == 0 else "failed")
        stop_event.set()
        try:
            t.join(timeout=2.0)
        except Exception:
            pass
        if log_f is not None:
            try:
                log_f.close()
            except Exception:
                pass
        if remove:
            try:
                container.remove(force=True)
            except Exception:
                pass


def _agent_backtest_env(db: Session, job: Job) -> dict[str, str]:
    """Point the agent's in-loop backtest at this job's dataset.

    Keeps the metrics the agent optimises against comparable to the platform
    backtest that runs afterwards. Falls back to the agent defaults when the job
    carries no dataset.
    """
    dataset_id = (job.payload or {}).get("dataset_id")
    if not dataset_id:
        return {}
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        return {}
    env = {
        "AGENT_BACKTEST_EXCHANGE": str(ds.exchange),
        "AGENT_BACKTEST_SYMBOL": str(ds.symbol),
        "AGENT_BACKTEST_INTERVAL": str(ds.interval),
    }
    if ds.start_ms is not None:
        env["AGENT_BACKTEST_START_MS"] = str(ds.start_ms)
    if ds.end_ms is not None:
        env["AGENT_BACKTEST_END_MS"] = str(ds.end_ms)
    return env


def _handle_backtest(db: Session, rds: redis.Redis, docker_client: docker.DockerClient, job: Job) -> None:
    strategy_id = job.payload["strategy_id"]
    version_id = job.payload["version_id"]
    run_id = job.payload["run_id"]
    dataset_id = job.payload["dataset_id"]

    run = db.get(BacktestRun, run_id)
    if run is None:
        raise RuntimeError(f"backtest_run_not_found: {run_id}")
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise RuntimeError(f"dataset_not_found: {dataset_id}")

    run.status = BacktestStatus.RUNNING
    run.started_at = _utcnow()
    db.flush()

    # Ensure run directory exists (within the shared workspaces volume mount)
    run_dir = os.path.join(settings.app_workspaces_dir, strategy_id, "runs", run_id)
    _safe_mkdir(run_dir)

    backtest_log_path = os.path.join(run_dir, "backtest.log")
    exit_code, tail = execute_backtest_container(
        docker_client=docker_client,
        job_id=job.id,
        rds=rds,
        strategy_id=strategy_id,
        version_id=version_id,
        run_id=run_id,
        exchange=ds.exchange,
        symbol=ds.symbol,
        interval=ds.interval,
        start_ms=ds.start_ms,
        end_ms=ds.end_ms,
        run_params=run.params or {},
        log_file_path=backtest_log_path,
        container_name=f"backtest-{job.id}",
    )
    if exit_code != 0:
        run.status = BacktestStatus.FAILED
        run.finished_at = _utcnow()
        msg = (
            f"backtest_container_exit_code={exit_code}\n"
            f"--- backtest.log tail ---\n{_tail_excerpt(tail)}\n"
            "See artifact: backtest.log"
        )
        run.error_message = msg
        db.flush()
        raise RuntimeError(msg)

    run.finished_at = _utcnow()

    # metrics.json is the run's actual output: if it is missing or unreadable the
    # run did not succeed, however the container exited. Reporting SUCCEEDED here
    # used to hand the UI an empty-metrics run with no error to explain it.
    try:
        metrics_payload = load_backtest_metrics(run_dir)
    except Exception as e:
        run.status = BacktestStatus.FAILED
        run.error_message = str(e)
        db.flush()
        raise RuntimeError(run.error_message) from e

    run.status = BacktestStatus.SUCCEEDED
    run.metrics = metrics_payload

    if metrics_payload:
        run.result_summary = {
            "exchange": ds.exchange,
            "symbol": ds.symbol,
            "interval": ds.interval,
            "start_ms": ds.start_ms,
            "end_ms": ds.end_ms,
            "total_return": metrics_payload.get("total_return"),
            "max_drawdown": metrics_payload.get("max_drawdown"),
            "sharpe_ratio": metrics_payload.get("sharpe_ratio"),
            "win_rate": metrics_payload.get("win_rate"),
            "profit_factor": metrics_payload.get("profit_factor"),
            "total_trades": metrics_payload.get("total_trades"),
            "num_bars": metrics_payload.get("num_bars"),
            "final_equity": metrics_payload.get("final_equity"),
            "initial_cash": metrics_payload.get("initial_cash"),
        }
    db.flush()


def _handle_generate_and_backtest(db: Session, rds: redis.Redis, docker_client: docker.DockerClient, job: Job) -> None:
    strategy_id = job.payload["strategy_id"]
    version_id = job.payload["version_id"]
    run_id = job.payload["run_id"]
    dataset_id = job.payload["dataset_id"]
    prompt = job.payload.get("prompt", "")
    llm_meta = job.payload.get("llm_meta") or {}

    # Store logs as artifacts under the backtest run directory for easier debugging.
    run_dir = os.path.join(settings.app_workspaces_dir, strategy_id, "runs", run_id)
    _safe_mkdir(run_dir)

    # Step 1: agent generates code into workspace
    agent_env = {
        "JOB_ID": job.id,
        "STRATEGY_ID": strategy_id,
        "VERSION_ID": version_id,
        "RUN_ID": run_id,
        "PROMPT": prompt,
        "WORKSPACES_DIR": "/workspaces",
    }
    # Optional per-job overrides (kept in the job payload) for OpenAI-compatible endpoints.
    if isinstance(llm_meta, dict):
        if llm_meta.get("force_fallback") or llm_meta.get("mock_llm"):
            agent_env["FORCE_FALLBACK"] = "1"
        if llm_meta.get("base_url"):
            agent_env["LLM_BASE_URL"] = str(llm_meta["base_url"])
        if llm_meta.get("model"):
            agent_env["LLM_MODEL"] = str(llm_meta["model"])
        if llm_meta.get("temperature") is not None:
            agent_env["LLM_TEMPERATURE"] = str(llm_meta["temperature"])
        if llm_meta.get("reasoning_effort"):
            agent_env["LLM_REASONING_EFFORT"] = str(llm_meta["reasoning_effort"])
        if llm_meta.get("thinking_level"):
            agent_env["AGENT_TAU_THINKING_LEVEL"] = str(llm_meta["thinking_level"])
    # Pass-through optional LLM env vars into agent sandbox only.
    # Support DeepSeek (OpenAI-compatible) as well.
    for key in (
        "LLM_PROVIDER",
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_TEMPERATURE",
        "LLM_REASONING_EFFORT",
        "LLM_HTTP_TIMEOUT_S",
        "LLM_STREAM_TIMEOUT_S",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_TEMPERATURE",
        "LLM_FALLBACK_ON_ERROR",
        "NETWORK_GUARD_ENABLED",
        "NETWORK_ALLOWLIST",
        # Market data cache, shared with the backtest container via /workspaces.
        "MARKET_DATA_CACHE_DIR",
        "MARKET_DATA_CACHE_ENABLED",
        "MARKET_DATA_CACHE_TTL_S",
        # Agent in-loop backtest tuning
        "AGENT_BACKTEST_MAX_RUNS",
        "AGENT_BACKTEST_STALL_LIMIT",
        "AGENT_BACKTEST_SCORE_KEY",
        "AGENT_BACKTEST_BARS",
        "AGENT_MAX_STEPS",
        "AGENT_TAU_EVENT_TIMEOUT_S",
        "AGENT_TAU_MAX_FOLLOW_UPS",
        "AGENT_TAU_THINKING_LEVEL",
        "PARENT_TAU_SESSION_ID",
        # Langfuse observability
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_HOST",
        "LANGFUSE_BASE_URL",
        "LANGFUSE_TRACING_ENVIRONMENT",
        "LANGFUSE_SESSION_ID",
        "LANGFUSE_USER_ID",
        *_PROXY_ENV_KEYS,
    ):
        val = os.getenv(key)
        if val:
            agent_env[key] = val
    if "AGENT_BACKTEST_MAX_RUNS" not in agent_env and getattr(settings, "agent_backtest_max_runs", None):
        agent_env["AGENT_BACKTEST_MAX_RUNS"] = str(settings.agent_backtest_max_runs)
    agent_env.update(_agent_backtest_env(db, job))

    agent_log_path = os.path.join(run_dir, "agent.log")
    sandbox_opts = _agent_sandbox_options()
    agent_exit, agent_tail = _run_container_and_stream_logs(
        docker_client,
        job_id=job.id,
        rds=rds,
        image=settings.worker_agent_image,
        command=AGENT_RUNNER_V2_COMMAND,
        name=f"agent-{job.id}",
        environment=agent_env,
        volumes={
            settings.worker_workspaces_volume: {"bind": "/workspaces", "mode": "rw"},
        },
        network=settings.worker_docker_network,
        log_file_path=agent_log_path,
        timeout_s=settings.agent_job_timeout_s or settings.worker_job_timeout_s,
        idle_timeout_s=settings.agent_idle_timeout_s,
        mem_limit=sandbox_opts.get("mem_limit"),
        nano_cpus=sandbox_opts.get("nano_cpus"),
        read_only=sandbox_opts.get("read_only"),
        tmpfs=sandbox_opts.get("tmpfs"),
        ulimits=sandbox_opts.get("ulimits"),
        pids_limit=sandbox_opts.get("pids_limit"),
    )
    if agent_exit != 0:
        msg = (
            f"agent_container_exit_code={agent_exit}\n"
            f"--- agent.log tail ---\n{_tail_excerpt(agent_tail)}\n"
            "See artifact: agent.log"
        )
        run = db.get(BacktestRun, run_id)
        if run is not None:
            run.status = BacktestStatus.FAILED
            run.finished_at = _utcnow()
            run.error_message = msg
            db.flush()
        raise RuntimeError(msg)

    # Convenience: copy generated strategy sources into the run directory so the report UI can
    # preview/download them as artifacts alongside metrics/logs.
    try:
        version_dir = os.path.join(settings.app_workspaces_dir, strategy_id, "versions", version_id)
        for name in (
            "strategy.py",
            "strategy_spec.yaml",
            "strategy_protocol.json",
            "params_schema.json",
            "strategy_meta.json",
            "overview.md",
            "llm_prompt.txt",
            "llm_meta.json",
            "plan.json",
            "change_spec_report.json",
            "backtest_config.json",
            "smoke_backtest.py",
            "smoke_validation.json",
            "verification_report.json",
            "diagnosis.json",
            "hitl_required.json",
            "strategy_explain.json",
            "README.md",
        ):
            src = os.path.join(version_dir, name)
            dst = os.path.join(run_dir, name)
            if os.path.isfile(src):
                shutil.copyfile(src, dst)
    except Exception:
        # Non-fatal: backtest/report still works without these extra artifacts.
        pass

    # Step 2: run backtest
    _handle_backtest(db, rds, docker_client, job)

    # Step 3: generate AI strategy name and mark chat_status as DONE
    strategy_dir = os.path.join(settings.app_workspaces_dir, strategy_id, "strategy")
    strategy = db.get(Strategy, strategy_id)
    if strategy is not None:
        naming_prompt, source = _build_strategy_name_prompt(strategy, prompt)
        _publish_log(job.id, f"Generating strategy name from {source}...", rds=rds)
        new_name = _generate_strategy_name(naming_prompt, llm_meta=llm_meta)
        strategy.name = new_name
        strategy.chat_status = ChatStatus.DONE
        strategy.updated_at = _utcnow()
        db.flush()
        _publish_log(job.id, f"Strategy name: {new_name}", rds=rds)

    _ensure_strategy_repo(strategy_dir)
    git_commit(strategy_dir, f"AI generate & backtest: {prompt[:80]}" if prompt else "AI generate & backtest")


def _dir_stats(path: str) -> tuple[int, int]:
    total_bytes = 0
    total_files = 0
    for root, dirs, files in os.walk(path):
        # Skip .git object store inside repo root; worktrees are outside .git
        if os.path.basename(root) == ".git":
            dirs[:] = []
            continue
        for name in files:
            total_files += 1
            try:
                total_bytes += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total_bytes, total_files


def _dir_size_bytes(path: str) -> int:
    return _dir_stats(path)[0]


def _git_rev_parse(path: str) -> str | None:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            return None
        return res.stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        return None


def _handle_repo_sync(db: Session, rds: redis.Redis, job: Job) -> None:
    repo_id = job.payload["repo_id"]
    owner = job.payload["owner"]
    name = job.payload["name"]
    branches = job.payload.get("branches") or []
    repos_root = job.payload["repos_root"]
    installation_id = job.payload.get("installation_id")

    repo = db.get(Repository, repo_id)
    if repo is None:
        raise RuntimeError(f"repo_not_found: {repo_id}")

    token = None
    if installation_id:
        token = get_installation_token(str(installation_id))

    _publish_log(job.id, f"Cloning {owner}/{name} (shallow, partial)…", rds=rds)
    info = clone_or_update(repos_root, owner, name, token=token)
    default_branch = info.default_branch
    if not branches:
        branches = repo.tracked_branches or [default_branch]

    # Update repo record
    repo.default_branch = default_branch
    if branches:
        repo.tracked_branches = branches
    db.flush()

    total_size = 0
    total_indexed = 0
    for br in branches:
        _publish_log(job.id, f"Preparing worktree for branch {br}…", rds=rds)
        wt = ensure_worktree(info.repo_path, br, token=token)
        sha = _git_rev_parse(wt)
        rs = (
            db.query(RepoSync).filter(RepoSync.repo_id == repo.id, RepoSync.branch == br).one_or_none()
        )
        if rs is None:
            rs = RepoSync(repo_id=repo.id, branch=br, last_local_sha=sha, last_synced_at=_utcnow())
            db.add(rs)
        else:
            rs.last_local_sha = sha
            rs.last_synced_at = _utcnow()
        db.flush()

        sz, count = _dir_stats(wt)
        total_size += sz
        total_indexed += count

    repo.size_bytes = total_size
    repo.quota_state = "ok" if total_size <= 1_000_000_000 else "over_quota"
    repo.last_error = None
    db.flush()
    action = "Import" if job.type == JobType.REPO_IMPORT else "Sync"
    _publish_log(job.id, f"{action} complete. Indexed {total_indexed} files; size={total_size} bytes.", rds=rds)


def _handle_repo_import(db: Session, rds: redis.Redis, job: Job) -> None:
    _handle_repo_sync(db, rds, job)


def _enqueue_stale_repo_syncs(session_factory, rds: redis.Redis, *, min_age_s: int) -> None:
    cutoff = _utcnow() - timedelta(seconds=min_age_s)
    with session_scope(session_factory) as db:
        repos = db.query(Repository).filter(Repository.status == "active").all()
        for repo in repos:
            branches = repo.tracked_branches or ([repo.default_branch] if repo.default_branch else [])
            if not branches:
                continue
            stale = False
            for br in branches:
                rs = (
                    db.query(RepoSync)
                    .filter(RepoSync.repo_id == repo.id, RepoSync.branch == br)
                    .one_or_none()
                )
                if rs is None or rs.last_synced_at is None or rs.last_synced_at < cutoff:
                    stale = True
                    break
            if not stale:
                continue
            job_exists = (
                db.query(Job)
                .filter(
                    Job.type == JobType.REPO_SYNC,
                    Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                    Job.payload["repo_id"].as_string() == repo.id,
                )
                .first()
            )
            if job_exists:
                continue
            job = Job(
                type=JobType.REPO_SYNC,
                payload={
                    "repo_id": repo.id,
                    "provider": repo.provider,
                    "owner": repo.owner,
                    "name": repo.name,
                    "branches": branches,
                    "installation_id": repo.github_installation_id,
                    "repos_root": os.path.join(settings.app_workspaces_dir, "repos"),
                },
            )
            db.add(job)
            db.flush()
            enqueue_job(settings.app_workspaces_dir, job.id, job.type, job.payload, priority="batch", redis_client=rds)


def _parse_timeout_s(env_key: str) -> float | None:
    raw = (os.getenv(env_key) or "").strip()
    if not raw:
        return None
    try:
        val = float(raw)
        return val if val > 0 else None
    except Exception:
        print(f"[worker] invalid {env_key}={raw!r}; ignoring")
        return None


def _extract_name_hint_from_json_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""

    candidates = [raw]
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        candidates.insert(0, match.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        for key in ("summary", "strategy_name", "name", "title"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        nested = parsed.get("answer")
        if isinstance(nested, str):
            nested_hint = _extract_name_hint_from_json_text(nested)
            if nested_hint:
                return nested_hint
    return ""


def _normalize_strategy_name_candidate(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""

    json_hint = _extract_name_hint_from_json_text(text)
    if json_hint:
        text = json_hint

    text = text.splitlines()[0] if "\n" in text else text
    text = re.sub(r"^(strategy\s*name|name|title|策略名称|策略名)\s*[:：-]\s*", "", text, flags=re.IGNORECASE)
    text = text.strip().strip("\"'`")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > STRATEGY_NAME_MAX_CHARS:
        text = text[:STRATEGY_NAME_MAX_CHARS].rstrip()
    return text


def _is_valid_strategy_name(name: str) -> bool:
    text = str(name or "").strip()
    if len(text) < 2:
        return False
    lowered = text.lower()
    if lowered.startswith("here is") or lowered.startswith("below is"):
        return False
    if re.fullmatch(r"\d+([.,]\d+)?", text):
        return False
    # Require at least one letter-like character, so names like "25" are rejected.
    if not any(ch.isalpha() for ch in text):
        return False
    return True


def _prompt_from_config_json(prompt: str) -> str:
    raw = str(prompt or "").strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except Exception:
        return ""
    if not isinstance(parsed, dict):
        return ""

    fields: list[tuple[str, str]] = [
        ("strategy_type", "策略类型"),
        ("symbol", "交易标的"),
        ("interval", "周期"),
        ("indicators", "指标"),
        ("entry_rules", "入场规则"),
        ("exit_rules", "出场规则"),
        ("risk_management", "风控"),
    ]
    parts: list[str] = []
    for key, label in fields:
        value = parsed.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        parts.append(f"{label}: {text}")
    return "\n".join(parts).strip()


def _build_strategy_name_prompt(strategy: Strategy | None, fallback_prompt: str) -> tuple[str, str]:
    if strategy and isinstance(strategy.chat_history, list):
        user_messages: list[str] = []
        for item in strategy.chat_history:
            if not isinstance(item, dict):
                continue
            if str(item.get("role") or "") != "user":
                continue
            content = str(item.get("content") or "").strip()
            if not content or content.startswith("/"):
                continue
            user_messages.append(content)
        if user_messages:
            # Keep recent user intent to avoid feeding JSON configs to name generation.
            return "\n\n".join(user_messages[-3:])[:3000], "chat_history"

    from_config = _prompt_from_config_json(fallback_prompt)
    if from_config:
        return from_config, "config_json"

    cleaned = re.sub(r"```[\s\S]*?```", " ", str(fallback_prompt or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return (cleaned[:3000] if cleaned else "trading strategy"), "raw_prompt"


def _fallback_strategy_name(prompt: str) -> str:
    hint = _normalize_strategy_name_candidate(_extract_name_hint_from_json_text(prompt))
    if _is_valid_strategy_name(hint):
        return hint
    cleaned = re.sub(r"```[\s\S]*?```", " ", str(prompt or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    candidate = _normalize_strategy_name_candidate(cleaned)
    return candidate if _is_valid_strategy_name(candidate) else "Untitled Strategy"


def _generate_strategy_name(prompt: str, *, llm_meta: dict | None = None) -> str:
    """Use LLM to generate a short strategy name from the prompt."""
    import requests

    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.deepseek.com/v1"
    model = os.getenv("DEEPSEEK_MODEL") or os.getenv("LLM_MODEL") or "deepseek-chat"

    if isinstance(llm_meta, dict):
        if llm_meta.get("base_url"):
            base_url = str(llm_meta["base_url"])
        if llm_meta.get("model"):
            model = str(llm_meta["model"])

    if not api_key:
        return _fallback_strategy_name(prompt)

    # Name generation should be fast; use a dedicated fail-fast timeout to avoid blocking the worker.
    timeout_s = _parse_timeout_s("STRATEGY_NAME_LLM_TIMEOUT_S") or 20.0

    system_prompts = [
        (
            "You are a quantitative strategy naming assistant. "
            "Generate one short strategy title from the user intent. "
            "Output ONLY the title text, no JSON, no explanation. "
            "Prefer Chinese format like 'RSI 策略' or 'MACD 趋势策略'. "
            "Never output pure numbers."
        ),
        (
            "Return exactly one concise strategy title. "
            "No punctuation wrappers, no markdown, no JSON, no extra words. "
            "The title must contain at least one alphabetic character and cannot be numeric-only."
        ),
    ]

    for system_prompt in system_prompts:
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": f"用户策略描述：\n{prompt}\n\n请输出策略标题。",
                        },
                    ],
                    "max_tokens": 80,
                    "temperature": 0.0,
                },
                timeout=timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()
            raw_name = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            candidate = _normalize_strategy_name_candidate(raw_name)
            if _is_valid_strategy_name(candidate):
                return candidate
            print(f"[worker] Invalid generated strategy name: {raw_name!r}")
        except requests.exceptions.HTTPError as e:
            try:
                body = e.response.text if e.response is not None else ""
            except Exception:
                body = ""
            print(f"[worker] Failed to generate strategy name (http): {e} body={body[:500]!r}")
        except Exception as e:
            print(f"[worker] Failed to generate strategy name: {e}")

    return _fallback_strategy_name(prompt)


def _merge_agent_meta_into_version(db: Session, strategy_id: str, version_id: str) -> None:
    """Copy the agent's `llm_meta.json` onto the version row.

    `runner_v2` records how the session actually ended there (`used_llm`,
    `stop_reason`, `degraded`, the in-loop backtest history). Left on disk it was
    read by nothing, so a degraded run was indistinguishable from a clean one in
    the API and the console.
    """
    path = os.path.join(
        settings.app_workspaces_dir, strategy_id, "versions", version_id, "llm_meta.json"
    )
    try:
        with open(path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(meta, dict):
        return
    version = db.get(StrategyVersion, version_id)
    if version is None:
        return
    version.llm_meta = {**(version.llm_meta or {}), **meta}
    db.flush()


def _handle_generate_strategy(db: Session, rds: redis.Redis, docker_client: docker.DockerClient, job: Job) -> None:
    """Generate strategy code from prompt, and generate AI strategy name."""
    strategy_id = job.payload["strategy_id"]
    version_id = job.payload["version_id"]
    prompt = job.payload.get("prompt", "")
    llm_meta = job.payload.get("llm_meta") or {}
    strategy_dir = os.path.join(settings.app_workspaces_dir, strategy_id, "strategy")

    # Store logs under the version directory for debugging/traceability.
    version_dir = os.path.join(settings.app_workspaces_dir, strategy_id, "versions", version_id)
    _safe_mkdir(version_dir)

    agent_env = {
        "JOB_ID": job.id,
        "JOB_TYPE": job.type,
        "STRATEGY_ID": strategy_id,
        "VERSION_ID": version_id,
        "PROMPT": prompt,
        "WORKSPACES_DIR": "/workspaces",
    }
    # Optional per-job overrides (kept in the job payload) for OpenAI-compatible endpoints.
    if isinstance(llm_meta, dict):
        if llm_meta.get("force_fallback") or llm_meta.get("mock_llm"):
            agent_env["FORCE_FALLBACK"] = "1"
        if llm_meta.get("base_url"):
            agent_env["LLM_BASE_URL"] = str(llm_meta["base_url"])
        if llm_meta.get("model"):
            agent_env["LLM_MODEL"] = str(llm_meta["model"])
        if llm_meta.get("temperature") is not None:
            agent_env["LLM_TEMPERATURE"] = str(llm_meta["temperature"])
        if llm_meta.get("reasoning_effort"):
            agent_env["LLM_REASONING_EFFORT"] = str(llm_meta["reasoning_effort"])
        if llm_meta.get("thinking_level"):
            agent_env["AGENT_TAU_THINKING_LEVEL"] = str(llm_meta["thinking_level"])
    # Pass-through optional LLM env vars into agent sandbox only.
    for key in (
        "LLM_PROVIDER",
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_TEMPERATURE",
        "LLM_REASONING_EFFORT",
        "LLM_HTTP_TIMEOUT_S",
        "LLM_STREAM_TIMEOUT_S",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_TEMPERATURE",
        "LLM_FALLBACK_ON_ERROR",
        "LLM_STREAM",
        "NETWORK_GUARD_ENABLED",
        "NETWORK_ALLOWLIST",
        # Market data cache, shared with the backtest container via /workspaces.
        "MARKET_DATA_CACHE_DIR",
        "MARKET_DATA_CACHE_ENABLED",
        "MARKET_DATA_CACHE_TTL_S",
        # Agent in-loop backtest tuning
        "AGENT_BACKTEST_MAX_RUNS",
        "AGENT_BACKTEST_STALL_LIMIT",
        "AGENT_BACKTEST_SCORE_KEY",
        "AGENT_BACKTEST_BARS",
        "AGENT_MAX_STEPS",
        "AGENT_TAU_EVENT_TIMEOUT_S",
        "AGENT_TAU_MAX_FOLLOW_UPS",
        "AGENT_TAU_THINKING_LEVEL",
        "PARENT_TAU_SESSION_ID",
        # Langfuse observability
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_HOST",
        "LANGFUSE_BASE_URL",
        "LANGFUSE_TRACING_ENVIRONMENT",
        "LANGFUSE_SESSION_ID",
        "LANGFUSE_USER_ID",
        *_PROXY_ENV_KEYS,
    ):
        val = os.getenv(key)
        if val:
            agent_env[key] = val
    if "AGENT_BACKTEST_MAX_RUNS" not in agent_env and getattr(settings, "agent_backtest_max_runs", None):
        agent_env["AGENT_BACKTEST_MAX_RUNS"] = str(settings.agent_backtest_max_runs)
    agent_env.update(_agent_backtest_env(db, job))

    agent_log_path = os.path.join(version_dir, "agent.log")
    sandbox_opts = _agent_sandbox_options()
    agent_exit, agent_tail = _run_container_and_stream_logs(
        docker_client,
        job_id=job.id,
        rds=rds,
        image=settings.worker_agent_image,
        command=AGENT_RUNNER_V2_COMMAND,
        name=f"agent-{job.id}",
        environment=agent_env,
        volumes={
            settings.worker_workspaces_volume: {"bind": "/workspaces", "mode": "rw"},
        },
        network=settings.worker_docker_network,
        log_file_path=agent_log_path,
        timeout_s=settings.agent_job_timeout_s or settings.worker_job_timeout_s,
        idle_timeout_s=settings.agent_idle_timeout_s,
        mem_limit=sandbox_opts.get("mem_limit"),
        nano_cpus=sandbox_opts.get("nano_cpus"),
        read_only=sandbox_opts.get("read_only"),
        tmpfs=sandbox_opts.get("tmpfs"),
        ulimits=sandbox_opts.get("ulimits"),
        pids_limit=sandbox_opts.get("pids_limit"),
    )
    if agent_exit != 0:
        msg = (
            f"agent_container_exit_code={agent_exit}\n"
            f"--- agent.log tail ---\n{_tail_excerpt(agent_tail)}\n"
            "See artifact: agent.log"
        )
        raise RuntimeError(msg)

    _merge_agent_meta_into_version(db, strategy_id, version_id)

    # Generate AI strategy name and update the strategy
    strategy = db.get(Strategy, strategy_id)
    if strategy is not None:
        naming_prompt, source = _build_strategy_name_prompt(strategy, prompt)
        _publish_log(job.id, f"Generating strategy name from {source}...", rds=rds)
        new_name = _generate_strategy_name(naming_prompt, llm_meta=llm_meta)
        strategy.name = new_name
        strategy.chat_status = ChatStatus.DONE

        strategy.updated_at = _utcnow()
        db.flush()
        _publish_log(job.id, f"Strategy name: {new_name}", rds=rds)

    _ensure_strategy_repo(strategy_dir)
    git_commit(strategy_dir, f"AI generate: {prompt[:80]}" if prompt else "AI generate")


def _handle_refine_strategy(db: Session, rds: redis.Redis, docker_client: docker.DockerClient, job: Job) -> None:
    strategy_id = job.payload["strategy_id"]
    version_id = job.payload["version_id"]
    prompt = job.payload.get("prompt", "")
    llm_meta = job.payload.get("llm_meta") or {}
    strategy_dir = os.path.join(settings.app_workspaces_dir, strategy_id, "strategy")

    # Store logs under the version directory for debugging/traceability.
    version_dir = os.path.join(settings.app_workspaces_dir, strategy_id, "versions", version_id)
    _safe_mkdir(version_dir)

    agent_env = {
        "JOB_ID": job.id,
        "JOB_TYPE": job.type,
        "STRATEGY_ID": strategy_id,
        "VERSION_ID": version_id,
        "PROMPT": prompt,
        "WORKSPACES_DIR": "/workspaces",
    }
    # Optional per-job overrides (kept in the job payload) for OpenAI-compatible endpoints.
    if isinstance(llm_meta, dict):
        if llm_meta.get("base_url"):
            agent_env["LLM_BASE_URL"] = str(llm_meta["base_url"])
        if llm_meta.get("model"):
            agent_env["LLM_MODEL"] = str(llm_meta["model"])
        if llm_meta.get("temperature") is not None:
            agent_env["LLM_TEMPERATURE"] = str(llm_meta["temperature"])
        if llm_meta.get("thinking_level"):
            agent_env["AGENT_TAU_THINKING_LEVEL"] = str(llm_meta["thinking_level"])
        if llm_meta.get("reasoning_effort"):
            agent_env["LLM_REASONING_EFFORT"] = str(llm_meta["reasoning_effort"])
        if llm_meta.get("parent_tau_session_id"):
            agent_env["PARENT_TAU_SESSION_ID"] = str(llm_meta["parent_tau_session_id"])

    # If parent_version_id is provided, automatically inherit its tau_session_id for continuous memory
    parent_version_id = job.payload.get("parent_version_id")
    if parent_version_id and "PARENT_TAU_SESSION_ID" not in agent_env:
        try:
            parent_v = db.query(StrategyVersion).filter(StrategyVersion.id == parent_version_id).first()
            if parent_v and isinstance(parent_v.llm_meta, dict):
                p_sid = parent_v.llm_meta.get("tau_session_id")
                if p_sid:
                    agent_env["PARENT_TAU_SESSION_ID"] = str(p_sid)
        except Exception:
            pass

    # Pass-through optional LLM env vars into agent sandbox only.
    # Support DeepSeek (OpenAI-compatible) as well.
    for key in (
        "LLM_PROVIDER",
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_TEMPERATURE",
        "LLM_REASONING_EFFORT",
        "LLM_HTTP_TIMEOUT_S",
        "LLM_STREAM_TIMEOUT_S",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_TEMPERATURE",
        "LLM_FALLBACK_ON_ERROR",
        "LLM_STREAM",
        "NETWORK_GUARD_ENABLED",
        "NETWORK_ALLOWLIST",
        # Market data cache, shared with the backtest container via /workspaces.
        "MARKET_DATA_CACHE_DIR",
        "MARKET_DATA_CACHE_ENABLED",
        "MARKET_DATA_CACHE_TTL_S",
        # Agent in-loop backtest tuning
        "AGENT_BACKTEST_MAX_RUNS",
        "AGENT_BACKTEST_STALL_LIMIT",
        "AGENT_BACKTEST_SCORE_KEY",
        "AGENT_BACKTEST_BARS",
        "AGENT_MAX_STEPS",
        "AGENT_TAU_EVENT_TIMEOUT_S",
        "AGENT_TAU_MAX_FOLLOW_UPS",
        "AGENT_TAU_THINKING_LEVEL",
        "PARENT_TAU_SESSION_ID",
        # Langfuse observability
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_HOST",
        "LANGFUSE_BASE_URL",
        "LANGFUSE_TRACING_ENVIRONMENT",
        "LANGFUSE_SESSION_ID",
        "LANGFUSE_USER_ID",
        *_PROXY_ENV_KEYS,
    ):
        val = os.getenv(key)
        if val:
            agent_env[key] = val
    if "AGENT_BACKTEST_MAX_RUNS" not in agent_env and getattr(settings, "agent_backtest_max_runs", None):
        agent_env["AGENT_BACKTEST_MAX_RUNS"] = str(settings.agent_backtest_max_runs)
    agent_env.update(_agent_backtest_env(db, job))

    agent_log_path = os.path.join(version_dir, "agent.log")
    sandbox_opts = _agent_sandbox_options()
    agent_exit, agent_tail = _run_container_and_stream_logs(
        docker_client,
        job_id=job.id,
        rds=rds,
        image=settings.worker_agent_image,
        command=AGENT_RUNNER_V2_COMMAND,
        name=f"agent-{job.id}",
        environment=agent_env,
        volumes={
            settings.worker_workspaces_volume: {"bind": "/workspaces", "mode": "rw"},
        },
        network=settings.worker_docker_network,
        log_file_path=agent_log_path,
        timeout_s=settings.agent_job_timeout_s or settings.worker_job_timeout_s,
        idle_timeout_s=settings.agent_idle_timeout_s,
        mem_limit=sandbox_opts.get("mem_limit"),
        nano_cpus=sandbox_opts.get("nano_cpus"),
        read_only=sandbox_opts.get("read_only"),
        tmpfs=sandbox_opts.get("tmpfs"),
        ulimits=sandbox_opts.get("ulimits"),
        pids_limit=sandbox_opts.get("pids_limit"),
    )
    if agent_exit != 0:
        msg = (
            f"agent_container_exit_code={agent_exit}\n"
            f"--- agent.log tail ---\n{_tail_excerpt(agent_tail)}\n"
            "See artifact: agent.log"
        )
        raise RuntimeError(msg)

    _merge_agent_meta_into_version(db, strategy_id, version_id)

    # Update strategy status to DONE (refinement complete)
    strategy = db.get(Strategy, strategy_id)
    if strategy is not None:
        strategy.chat_status = ChatStatus.DONE

        strategy.updated_at = _utcnow()
        db.flush()

    _ensure_strategy_repo(strategy_dir)
    git_commit(strategy_dir, f"AI refine: {prompt[:80]}" if prompt else "AI refine")


def _handle_scrape_tradingview_trending(
    db: Session, rds: redis.Redis, docker_client: docker.DockerClient, job: Job
) -> None:
    """
    Execute TradingView trending strategies scraping.

    Process:
    1. Use trending_scraper to scrape scripts/ideas
    2. Detect trading symbols
    3. Save to tradingview_trending_strategies table
    4. If auto_backtest=True, create TRENDING_BACKTEST job
    """
    params = job.payload
    source_types = params.get("source_types", ["scripts"])
    max_count = params.get("max_count", 50)
    auto_backtest = params.get("auto_backtest", True)
    auto_backtest_top_n = params.get("auto_backtest_top_n", 15)

    _publish_log(job.id, f"Starting TradingView scrape: sources={source_types}, max={max_count}", rds=rds)
    _raise_if_cancelled(job.id, rds=rds)

    try:
        # Import scraper (may need to install package first)
        try:
            from trending_scraper.scraper import TradingViewTrendingScraper
        except ImportError:
            raise RuntimeError(
                "trending_scraper package not found. Install with: pip install -e packages/trending_scraper"
            )

        scraper = TradingViewTrendingScraper(rate_limit_delay=0.5)

        # Map singular to plural for scraper
        source_type_map = {
            "script": "scripts",
            "idea": "ideas",
        }

        # Convert to plural form for parallel scraping
        scraper_source_types = [source_type_map.get(st, st) for st in source_types]

        # Use parallel scraping
        _publish_log(job.id, f"Parallel scraping {len(scraper_source_types)} source types...", rds=rds)
        _raise_if_cancelled(job.id, rds=rds)
        all_strategies = scraper.scrape_trending_parallel(
            source_types=scraper_source_types,
            max_count=max_count,
        )

        # Save to database with idempotency
        _publish_log(job.id, f"Saving {len(all_strategies)} strategies to database...", rds=rds)
        _raise_if_cancelled(job.id, rds=rds)
        saved_count = 0
        skipped_count = 0
        updated_count = 0

        for strategy_data in all_strategies:
            _raise_if_cancelled(job.id, rds=rds)
            tradingview_id = strategy_data.get("tradingview_id")
            url = strategy_data.get("url")

            # Check if strategy already exists (idempotency check)
            existing = (
                db.query(TradingViewTrendingStrategy)
                .filter(
                    or_(
                        TradingViewTrendingStrategy.tradingview_id == tradingview_id,
                        TradingViewTrendingStrategy.url == url,
                    )
                )
                .first()
            )

            if existing:
                # Strategy exists - skip or update dynamic fields
                # For now, skip to avoid duplicate entries
                skipped_count += 1
                _publish_log(job.id, f"Skipped existing strategy: {existing.title[:50]}", rds=rds)
                continue

            # Generate UUID for new strategies
            if "id" not in strategy_data:
                strategy_data["id"] = str(uuid.uuid4())

            # Convert source_type string to enum if needed
            if isinstance(strategy_data.get("source_type"), str):
                # Map plural to singular for enum
                source_type_map = {
                    "scripts": TrendingSourceType.SCRIPT,
                    "ideas": TrendingSourceType.IDEA,
                    "script": TrendingSourceType.SCRIPT,
                    "idea": TrendingSourceType.IDEA,
                }
                strategy_data["source_type"] = source_type_map.get(
                    strategy_data["source_type"],
                    TrendingSourceType.SCRIPT
                )

            # Create new strategy
            strategy = TradingViewTrendingStrategy(**strategy_data)
            db.add(strategy)
            saved_count += 1

        db.commit()
        _publish_log(job.id, f"Saved: {saved_count} new, Skipped: {skipped_count} existing, Updated: {updated_count}", rds=rds)

        # If auto_backtest, create backtest job for top N strategies
        if auto_backtest and all_strategies:
            _raise_if_cancelled(job.id, rds=rds)
            top_strategies = all_strategies[:auto_backtest_top_n]

            _publish_log(
                job.id,
                f"Creating backtest job for top {len(top_strategies)} strategies...",
                rds=rds,
            )

            _create_backtest_trending_top_n_job(
                db=db,
                rds=rds,
                strategy_ids=[s.get("tradingview_id") for s in top_strategies if s.get("tradingview_id")],
            )

    except Exception as e:
        _publish_log(job.id, f"Error during scraping: {e}", rds=rds)
        raise


def _handle_backtest_trending_top_n(
    db: Session, rds: redis.Redis, docker_client: docker.DockerClient, job: Job
) -> None:
    """
    Batch backtest top N trending strategies with full PineScript conversion.

    Strategies are processed in parallel (up to 3 at a time).
    """
    from concurrent.futures import ThreadPoolExecutor
    from worker.trending_backtest_impl import (
        create_temporary_strategy_from_tradingview,
        trigger_llm_conversion,
        create_backtest_datasets,
        create_backtest_jobs,
        wait_for_backtest_completion,
        update_trending_strategy_results,
    )

    params = job.payload
    strategy_ids = params.get("strategy_ids", [])

    default_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    default_interval = "1h"
    default_duration_days = 90

    _publish_log(job.id, f"Starting parallel backtest pipeline for {len(strategy_ids)} trending strategies (max_workers=3)", rds=rds)
    _raise_if_cancelled(job.id, rds=rds)

    def process_single_strategy(tradingview_id: str) -> bool:
        """Process a single strategy - returns True if successful."""
        try:
            _raise_if_cancelled(job.id, rds=rds)
            from control_plane.db import create_db_engine, create_session_factory, session_scope
            from control_plane.models import TradingViewTrendingStrategy

            engine = create_db_engine(settings.app_db_url)
            local_session_factory = create_session_factory(engine)

            with session_scope(local_session_factory) as local_db:
                tv_strategy = local_db.query(TradingViewTrendingStrategy).filter_by(
                    tradingview_id=tradingview_id
                ).first()

                if not tv_strategy:
                    _publish_log(job.id, f"Warning: strategy {tradingview_id} not found, skipping", rds=rds)
                    return False

                tv_strategy.backtest_status = "running"
                local_db.flush()
                _publish_log(job.id, f"Processing {tv_strategy.title}...", rds=rds)
                _raise_if_cancelled(job.id, rds=rds)

                symbols = tv_strategy.detected_symbols or default_symbols

                _publish_log(job.id, "  Step 1: Creating temporary strategy...", rds=rds)
                _raise_if_cancelled(job.id, rds=rds)
                strategy, version, pinescript_source = create_temporary_strategy_from_tradingview(
                    local_db, rds, tv_strategy
                )

                _publish_log(job.id, "  Step 2: Triggering PineScript to Python conversion...", rds=rds)
                _raise_if_cancelled(job.id, rds=rds)
                conversion_job = trigger_llm_conversion(
                    local_db, rds, strategy, version, pinescript_source, tv_strategy
                )

                if conversion_job:
                    _publish_log(job.id, "  Step 3: Waiting for LLM conversion...", rds=rds)
                    conversion_timeout = 1800
                    conversion_start = time.time()

                    while time.time() - conversion_start < conversion_timeout:
                        _raise_if_cancelled(job.id, rds=rds)
                        local_db.refresh(conversion_job)
                        if conversion_job.status == "succeeded":
                            _publish_log(job.id, "  Conversion completed successfully", rds=rds)
                            break
                        elif conversion_job.status == "failed":
                            error_msg = conversion_job.error_message or "Unknown error"
                            raise RuntimeError(f"LLM conversion failed: {error_msg}")
                        time.sleep(5)
                    else:
                        raise RuntimeError("LLM conversion timeout")
                else:
                    _publish_log(job.id, "  Step 3: Skipped (reusing existing strategy code)", rds=rds)

                _publish_log(job.id, f"  Step 4: Creating backtest datasets for {symbols[:3]}...", rds=rds)
                _raise_if_cancelled(job.id, rds=rds)
                datasets = create_backtest_datasets(
                    local_db, strategy, version, symbols, default_interval, default_duration_days
                )

                _publish_log(job.id, "  Step 5: Triggering backtest jobs...", rds=rds)
                _raise_if_cancelled(job.id, rds=rds)
                backtest_jobs = create_backtest_jobs(local_db, rds, datasets)

                _publish_log(job.id, "  Step 6: Waiting for backtests to complete...", rds=rds)
                _raise_if_cancelled(job.id, rds=rds)
                run_ids = [run.id for _, run in datasets]
                backtest_results = wait_for_backtest_completion(local_db, run_ids, timeout_seconds=600)

                _publish_log(job.id, "  Step 7: Updating results and quality score...", rds=rds)
                _raise_if_cancelled(job.id, rds=rds)
                update_trending_strategy_results(local_db, tv_strategy, backtest_results)

                _publish_log(job.id, "  ✓ Completed", rds=rds)
                return True

        except Exception as e:
            _publish_log(job.id, f"  ✗ Error backtesting {tradingview_id}: {e}", rds=rds)
            print(f"[ERROR] Error backtesting trending strategy {tradingview_id}: {e}")

            try:
                from control_plane.db import create_db_engine, create_session_factory, session_scope
                from control_plane.models import TradingViewTrendingStrategy

                engine = create_db_engine(settings.app_db_url)
                local_session_factory = create_session_factory(engine)

                with session_scope(local_session_factory) as local_db:
                    tv_strategy = local_db.query(TradingViewTrendingStrategy).filter_by(
                        tradingview_id=tradingview_id
                    ).first()
                    if tv_strategy:
                        tv_strategy.backtest_status = "failed"
                        tv_strategy.backtest_error = str(e)[:500]
                        local_db.flush()
            except Exception:
                pass
            return False

    # Process strategies in parallel with max 3 workers
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(process_single_strategy, tv_id) for tv_id in strategy_ids]
        results = [f.result() for f in futures]

    success_count = sum(results)
    _publish_log(job.id, f"Trending strategy backtests completed: {success_count}/{len(strategy_ids)} successful", rds=rds)


def _create_backtest_trending_top_n_job(
    db: Session, rds: redis.Redis, strategy_ids: list[str]
) -> None:
    """Create a batch backtest job for trending strategies."""
    job_id = str(uuid.uuid4())

    job = Job(
        id=job_id,
        type=JobType.TRENDING_BACKTEST.value,
        payload={"strategy_ids": strategy_ids},
        status="queued",
    )

    db.add(job)
    db.commit()

    enqueue_job(settings.app_workspaces_dir, job_id, JobType.TRENDING_BACKTEST.value, {"strategy_ids": strategy_ids}, priority="batch", redis_client=rds)


# --- Job dispatch ----------------------------------------------------------
#
# Every handler is normalised to (db, rds, docker_client, job); handlers that do
# not spawn a container simply ignore docker_client. Template jobs are imported
# lazily inside their wrappers to keep worker start-up cheap.


def _dispatch_repo(db: Session, rds: redis.Redis, docker_client: docker.DockerClient, job: Job) -> None:
    # REPO_SYNC is handled as a re-run of import over the selected branches.
    _handle_repo_import(db, rds, job)


def _dispatch_template_performance(db: Session, rds: redis.Redis, docker_client: docker.DockerClient, job: Job) -> None:

    generate_template_performance_data(db, rds, job)


def _dispatch_template_backtest(db: Session, rds: redis.Redis, docker_client: docker.DockerClient, job: Job) -> None:
    from worker.template_backtest_job import handle_template_backtest

    handle_template_backtest(db, rds, docker_client, job)


def _handle_live_trading_start(db: Session, rds: redis.Redis, docker_client: docker.DockerClient, job: Job) -> None:
    session_id = job.payload["session_id"]
    strategy_id = job.payload["strategy_id"]
    session = db.get(TradingSession, session_id)
    if session is None:
        raise RuntimeError(f"trading_session_not_found: {session_id}")

    config = session.config
    exchange = config.exchange if config else "okx"
    symbol = config.symbol if config else "BTC-USDT"
    interval = (config.intervals[0] if (config and config.intervals) else "1m")

    from worker.live_trading_runner import start_live_trading_container

    cid = start_live_trading_container(
        docker_client,
        session_id=session_id,
        strategy_id=strategy_id,
        exchange=exchange,
        symbol=symbol,
        interval=interval,
    )

    session.container_id = cid
    session.status = TradingSessionStatus.RUNNING
    session.started_at = _utcnow()
    db.flush()


def _handle_live_trading_stop(db: Session, rds: redis.Redis, docker_client: docker.DockerClient, job: Job) -> None:
    session_id = job.payload["session_id"]
    from worker.live_trading_runner import stop_live_trading_container

    stop_live_trading_container(docker_client, session_id=session_id)

    session = db.get(TradingSession, session_id)
    if session:
        session.status = TradingSessionStatus.STOPPED
        session.stopped_at = _utcnow()
        if session.config:
            session.config.is_active = False
        db.flush()


JOB_HANDLERS: dict[str, Callable[[Session, redis.Redis, docker.DockerClient, Job], None]] = {
    # MVP core
    JobType.BACKTEST.value: _handle_backtest,
    JobType.GENERATE_STRATEGY.value: _handle_generate_strategy,
    JobType.GENERATE_AND_BACKTEST.value: _handle_generate_and_backtest,
    JobType.REFINE_STRATEGY.value: _handle_refine_strategy,
    # Live trading containers
    JobType.LIVE_TRADING_START.value: _handle_live_trading_start,
    JobType.LIVE_TRADING_STOP.value: _handle_live_trading_stop,
    # Repositories
    JobType.REPO_IMPORT.value: _dispatch_repo,
    JobType.REPO_SYNC.value: _dispatch_repo,
    # Trending (gated by settings.trending_scheduler_enabled)
    JobType.TRENDING_SCRAPE.value: _handle_scrape_tradingview_trending,
    JobType.TRENDING_BACKTEST.value: _handle_backtest_trending_top_n,
    # Templates
    JobType.TEMPLATE_PERFORMANCE_UPDATE.value: _dispatch_template_performance,
    JobType.TEMPLATE_BACKTEST.value: _dispatch_template_backtest,
}

_TRENDING_JOB_TYPES = frozenset(
    {JobType.TRENDING_SCRAPE.value, JobType.TRENDING_BACKTEST.value}
)


def _process_job(session_factory, rds: Optional[redis.Redis], docker_client: docker.DockerClient, job_id: str) -> None:
    # DB/queue are not transactional together; the worker may see the queue message
    # slightly before the DB commit. Retry a bit to avoid dropping jobs.
    claimed = False
    for _ in range(25):
        with session_scope(session_factory) as db:
            job = db.get(Job, job_id)
            if job is not None:
                # If an admin already cancelled this job, or another consumer already started it, don't re-run.
                if str(job.status) in (JobStatus.CANCELLED, JobStatus.RUNNING, JobStatus.SUCCEEDED):
                    return
                if _is_cancel_requested(job_id, rds=rds):
                    job.status = JobStatus.CANCELLED
                    job.finished_at = _utcnow()
                    job.error_message = "cancelled"
                    db.flush()
                    return
                # Atomically claim the job
                stmt = (
                    update(Job)
                    .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
                    .values(status=JobStatus.RUNNING, started_at=_utcnow())
                )
                res = db.execute(stmt)
                if res.rowcount > 0:
                    claimed = True
                    break
                else:
                    return
        time.sleep(0.2)
    if not claimed:
        return

    try:
        with session_scope(session_factory) as db:
            job = db.get(Job, job_id)
            if job is None:
                return
            if str(job.status) == JobStatus.CANCELLED:
                return
            if _is_cancel_requested(job_id, rds=rds):
                job.status = JobStatus.CANCELLED
                job.finished_at = _utcnow()
                job.error_message = "cancelled"
                db.flush()
                return
            if job.type in _TRENDING_JOB_TYPES and not settings.trending_scheduler_enabled:
                _publish_log(job.id, "trending_disabled", rds=rds)
                job.status = JobStatus.CANCELLED
                job.finished_at = _utcnow()
                job.error_message = "trending_disabled"
                db.flush()
                return

            handler = JOB_HANDLERS.get(job.type)
            if handler is None:
                raise RuntimeError(f"unsupported_job_type: {job.type}")
            handler(db, rds, docker_client, job)

        with session_scope(session_factory) as db:
            job = db.get(Job, job_id)
            if job is None:
                return
            job.status = JobStatus.SUCCEEDED
            job.finished_at = _utcnow()
            db.flush()
            _publish_log(job_id, "job succeeded", rds=rds)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        tb = traceback.format_exc()
        _publish_log(job_id, err, rds=rds)
        _publish_log(job_id, tb, rds=rds)
        with session_scope(session_factory) as db:
            job = db.get(Job, job_id)
            if job is None:
                return
            if _is_cancel_requested(job_id, rds=rds) or "cancelled" in err.lower():
                job.status = JobStatus.CANCELLED
                job.error_message = "cancelled"
            else:
                job.status = JobStatus.FAILED
                job.error_message = err
            job.finished_at = _utcnow()
            # Ensure related entities reflect failure even if the original transaction rolled back.
            run_id = None
            strategy_id = None
            try:
                if isinstance(job.payload, dict):
                    run_id = job.payload.get("run_id")
                    strategy_id = job.payload.get("strategy_id")
            except Exception:
                run_id = None
                strategy_id = None

            if run_id:
                run = db.get(BacktestRun, run_id)
                if run is not None:
                    run.status = BacktestStatus.FAILED
                    run.finished_at = _utcnow()
                    run.error_message = err

            if strategy_id:
                strat = db.get(Strategy, strategy_id)
                if strat is not None:
                    if job.type in (JobType.GENERATE_STRATEGY, JobType.GENERATE_AND_BACKTEST):
                        strat.chat_status = ChatStatus.READY
                    elif job.type == JobType.REFINE_STRATEGY.value:
                        strat.chat_status = ChatStatus.DONE
                    strat.updated_at = _utcnow()
            db.flush()
    finally:
        _mark_job_log_done(job_id)


def _run_scheduled_scrape(rds: redis.Redis) -> None:
    """Run the scheduled trending scrape job."""
    logger = logging.getLogger(__name__)

    try:
        engine = create_db_engine(settings.app_db_url)
        session_factory = create_session_factory(engine)

        with session_scope(session_factory) as db:
            schedule = db.query(TrendingSchedule).first()
            if not schedule or not schedule.enabled:
                logger.info("Trending schedule is disabled or not configured")
                return

            job_id = str(uuid.uuid4())
            job = Job(
                id=job_id,
                type=JobType.TRENDING_SCRAPE.value,
                payload={
                    "source_types": schedule.source_types or ["script"],
                    "max_count": schedule.max_count,
                    "auto_backtest": schedule.auto_backtest,
                    "auto_backtest_top_n": schedule.auto_backtest_top_n,
                    "scheduled": True,
                },
                status="queued",
            )
            db.add(job)
            db.commit()

            schedule.last_run_at = _utcnow()
            schedule.next_run_at = None
            db.commit()

            enqueue_job(settings.app_workspaces_dir, job_id, job.type, job.payload, priority="batch", redis_client=rds)
            logger.info(f"Created scheduled scrape job: {job_id}")
    except Exception as e:
        logger.error(f"Error running scheduled scrape: {e}")


def _setup_trending_scheduler(session_factory, rds: redis.Redis) -> BackgroundScheduler | None:
    """Set up the APScheduler for trending scrape."""
    logger = logging.getLogger(__name__)

    if not settings.trending_scheduler_enabled:
        logger.info("Trending scheduler is disabled via settings")
        return None

    scheduler = BackgroundScheduler(timezone="UTC")

    try:
        with session_scope(session_factory) as db:
            schedule = db.query(TrendingSchedule).first()

            # Auto-create default schedule if not exists
            if not schedule:
                schedule = TrendingSchedule(
                    enabled=True,
                    cron_expression="0 */6 * * *",
                    source_types=["script"],
                    max_count=50,
                    auto_backtest=True,
                    auto_backtest_top_n=15,
                )
                db.add(schedule)
                db.commit()
                logger.info("Created default trending schedule configuration")
                # Refresh to get the created object
                db.refresh(schedule)

        if not schedule.enabled:
            logger.info("Trending schedule is disabled")
            return None

        cron_expr = schedule.cron_expression or settings.trending_default_cron
        trigger = CronTrigger.from_crontab(cron_expr, timezone="UTC")

        scheduler.add_job(
            _run_scheduled_scrape,
            trigger=trigger,
            id="trending_scrape",
            name="TradingView Trending Scrape",
            replace_existing=True,
            args=[rds],
        )

        scheduler.start()
        logger.info(f"Trending scheduler started with cron: {cron_expr}")

    except Exception as e:
        logger.error(f"Error setting up trending scheduler: {e}")
        scheduler.shutdown(wait=False)
        return None

    return scheduler


def _run_scheduled_template_update(rds: redis.Redis) -> None:
    """Run scheduled template performance update."""
    logger = logging.getLogger(__name__)

    try:
        engine = create_db_engine(settings.app_db_url)
        session_factory = create_session_factory(engine)

        with session_scope(session_factory) as db:
            schedule = db.query(TemplatePerformanceSchedule).first()
            if not schedule or not schedule.enabled:
                logger.info("Template performance schedule is disabled or not configured")
                return

            job_id = str(uuid.uuid4())
            job = Job(
                id=job_id,
                type=JobType.TEMPLATE_PERFORMANCE_UPDATE.value,
                payload={},
                status="queued",
            )
            db.add(job)
            db.commit()

            if schedule:
                schedule.last_run_at = _utcnow()
                schedule.next_run_at = None
                db.commit()

            enqueue_job(settings.app_workspaces_dir, job_id, job.type, job.payload, priority="batch", redis_client=rds)
            logger.info(f"Created scheduled template performance update job: {job_id}")
    except Exception as e:
        logger.error(f"Error running scheduled template update: {e}")


def _setup_template_performance_scheduler(session_factory, rds: redis.Redis) -> BackgroundScheduler | None:
    """Set up scheduler for template performance updates."""
    logger = logging.getLogger(__name__)

    # Default to enabled unless explicitly disabled
    enabled = getattr(settings, "template_performance_scheduler_enabled", True)

    if not enabled:
        logger.info("Template performance scheduler is disabled via settings")
        return None

    scheduler = BackgroundScheduler(timezone="UTC")

    try:
        with session_scope(session_factory) as db:
            schedule = db.query(TemplatePerformanceSchedule).first()

            # Auto-create default schedule if not exists
            if not schedule:
                schedule = TemplatePerformanceSchedule(
                    enabled=True,
                    cron_expression="0 2 * * *",  # Daily at 2 AM UTC
                    templates_per_batch=5,
                    backtest_days_history=90,
                    signals_per_day=3,
                    max_signals_per_template=100,
                )
                db.add(schedule)
                db.commit()
                logger.info("Created default template performance schedule configuration")
                db.refresh(schedule)

        if not schedule.enabled:
            logger.info("Template performance schedule is disabled")
            return None

        cron_expr = schedule.cron_expression or "0 2 * * *"
        trigger = CronTrigger.from_crontab(cron_expr, timezone="UTC")

        scheduler.add_job(
            _run_scheduled_template_update,
            trigger=trigger,
            id="template_performance_update",
            name="Template Performance Update",
            replace_existing=True,
            args=[rds],
        )

        scheduler.start()
        logger.info(f"Template performance scheduler started with cron: {cron_expr}")

    except Exception as e:
        logger.error(f"Error setting up template performance scheduler: {e}")
        scheduler.shutdown(wait=False)
        return None

    return scheduler




def main() -> None:
    print("worker starting")

    # Wait for database with better error messages
    print("[worker] Waiting for database connection...")
    _wait_for_db(settings.app_db_url, timeout_s=90.0)
    print("[worker] Database connected")

    engine = create_db_engine(settings.app_db_url)
    session_factory = create_session_factory(engine)
    # Multiple workers/tests may start concurrently in e2e. Use an advisory lock to
    # avoid DDL races (e.g., duplicate composite types for tables) during create_all on postgres.
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_lock(8811223344)"))
            try:
                Base.metadata.create_all(conn)
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(8811223344)"))
        else:
            Base.metadata.create_all(conn)

    print("[worker] Connecting to Redis (optional)...")
    rds = _wait_for_redis(settings.app_redis_url, timeout_s=10.0)
    if rds:
        print("[worker] Redis connected")
    else:
        print("[worker] Running in standalone zero-redis mode")

    file_queue = get_file_queue(settings.app_workspaces_dir)
    recovered = file_queue.recover_stale_processing_jobs()
    if recovered > 0:
        print(f"[worker] Recovered {recovered} stale processing job(s) into queue")

    mode = (getattr(settings, "worker_mode", "all") or "all").strip().lower()
    run_scheduler = mode in {"all", "scheduler"}
    run_consumer = mode in {"all", "consumer"}

    # Set up schedulers (optional)
    trending_scheduler = None
    template_perf_scheduler = None
    if run_scheduler:
        trending_scheduler = _setup_trending_scheduler(session_factory, rds)
        template_perf_scheduler = _setup_template_performance_scheduler(session_factory, rds)

    docker_client = None
    if run_consumer:
        docker_client = docker.DockerClient(base_url="unix://var/run/docker.sock")

    last_sync_check = 0.0
    processed_jobs = 0
    processed_jobs_lock = threading.Lock()
    stop_event = threading.Event()

    if not run_consumer:
        print(f"[worker] Worker mode={mode}; schedulers active, queue consumer disabled")
        try:
            while True:
                time.sleep(60)
        finally:
            if trending_scheduler:
                trending_scheduler.shutdown(wait=False)
            if template_perf_scheduler:
                template_perf_scheduler.shutdown(wait=False)
        return

    consumers = max(1, int(getattr(settings, "worker_consumers", 1) or 1))
    print(f"[worker] Starting job processing loop (mode={mode}, consumers={consumers})...")

    def _consumer_loop(consumer_id: int) -> None:
        nonlocal last_sync_check, processed_jobs
        while not stop_event.is_set():
            # Resource admission control check (prevent host OOM)
            if not _check_system_resources_available(min_available_mb=settings.min_available_memory_mb):
                time.sleep(1.0)
                continue

            q_item = None
            job_id = None

            # 1. Try file queue first (interactive priority first, then batch)
            try:
                q_item = file_queue.dequeue(timeout_s=1.0)
                if q_item is not None:
                    job_id = q_item.job_id
            except Exception as e:
                print(f"[worker] File queue dequeue error (c{consumer_id}): {e}")

            # 2. If no file job, check Redis queue if redis is connected
            if not job_id and rds is not None:
                try:
                    r_item = rds.blpop(QUEUE_NAME, timeout=1)
                    if r_item:
                        _, raw = r_item
                        try:
                            payload = json.loads(raw)
                            if isinstance(payload, dict):
                                job_id = payload.get("job_id")
                            elif isinstance(payload, str):
                                job_id = payload
                        except Exception:
                            if isinstance(raw, str):
                                job_id = raw
                except Exception as e:
                    pass

            if not job_id:
                # Only one consumer performs periodic repo-sync enqueue to avoid noisy duplication.
                if consumer_id == 0:
                    now = time.monotonic()
                    if now - last_sync_check >= settings.repo_sync_interval_s:
                        last_sync_check = now
                        try:
                            _enqueue_stale_repo_syncs(session_factory, rds, min_age_s=settings.repo_sync_interval_s)
                        except Exception:
                            pass
                continue

            print(f"[worker] (c{consumer_id}) Processing job: {job_id[:8]}...")

            try:
                _process_job(session_factory, rds, docker_client, job_id)
                if q_item is not None:
                    file_queue.mark_completed(q_item)
                with processed_jobs_lock:
                    processed_jobs += 1
                    total = processed_jobs
                print(f"[worker] (c{consumer_id}) Job {job_id[:8]}... completed (total: {total})")
            except Exception as e:
                if q_item is not None:
                    file_queue.mark_failed(q_item)
                print(f"[worker] (c{consumer_id}) Job {job_id[:8]}... FAILED: {e}")
                traceback.print_exc()

            time.sleep(0.01)

    threads = [
        threading.Thread(target=_consumer_loop, args=(i,), name=f"worker-consumer-{i}", daemon=True)
        for i in range(consumers)
    ]
    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[worker] Shutting down...")
    finally:
        stop_event.set()
        for t in threads:
            try:
                t.join(timeout=2.0)
            except Exception:
                pass
        print("[worker] Cleaning up...")
        if trending_scheduler:
            trending_scheduler.shutdown(wait=False)
        if template_perf_scheduler:
            template_perf_scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
