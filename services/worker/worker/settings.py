from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    app_db_url: str = "sqlite:////workspaces/app.db"
    app_redis_url: Optional[str] = None
    app_workspaces_dir: str = "/workspaces"
    log_dir: str = "/var/log/app"
    sandbox_runtime: Optional[str] = None
    min_available_memory_mb: int = 256

    github_app_id: Optional[str] = None
    github_app_private_key: Optional[str] = None

    worker_docker_network: str = "compose_default"
    worker_workspaces_volume: str = "workspaces"
    worker_agent_image: str = "prompt-trading-agent:local"
    worker_backtest_image: str = "prompt-trading-backtest:local"
    repo_sync_interval_s: int = 900

    # Worker execution mode:
    # - "all": run schedulers + consume queue (default, backward compatible)
    # - "scheduler": run schedulers only (enqueue jobs)
    # - "consumer": consume queue only
    worker_mode: str = "all"

    # Max wall-time (seconds) for each job container execution. If exceeded, the
    # container is killed and the job is marked failed so the queue keeps moving.
    worker_job_timeout_s: int = 420

    # Max silence duration (seconds) with zero log/data output before treating container as dead/hung
    container_idle_timeout_s: int = 120

    # Agent sandbox limits (code generation hard ceiling).
    #
    # A generation is a Tau session: up to AGENT_TAU_MAX_FOLLOW_UPS + 1 prompts,
    # each with several model turns and up to AGENT_BACKTEST_MAX_RUNS backtests
    # over 2000 bars. 420s did not cover one clean run, so healthy jobs were
    # killed at the wall clock -- after the model spend, before the version was
    # published.
    agent_job_timeout_s: int = 1800
    # Silence budget for agent containers, kept above the driver's own
    # AGENT_TAU_EVENT_TIMEOUT_S (300s) so a stalled session fails with the
    # driver's `tau_event_timeout` rather than an opaque container kill.
    agent_idle_timeout_s: int = 420
    agent_cpu_limit: float = 1.0  # vCPU cores (0 = no limit)
    agent_memory_limit_mb: int = 1536  # 0 = no limit
    agent_pids_limit: int = 256
    agent_read_only: bool = False
    agent_tmpfs_size_mb: int = 256
    agent_backtest_max_runs: int = 2

    # Number of queue consumer loops to run in parallel within a worker process.
    # Increasing this reduces head-of-line blocking for long-running jobs.
    worker_consumers: int = 1

    # Trending scraper scheduler settings
    trending_scheduler_enabled: bool = False
    trending_default_cron: str = "0 */6 * * *"

    # Template performance scheduler settings
    template_performance_scheduler_enabled: bool = True


settings = Settings()
