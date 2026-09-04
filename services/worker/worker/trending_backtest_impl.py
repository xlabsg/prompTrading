"""
Implementation of trending strategy auto-backtest functionality.
"""
import os
import sys
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
import redis

from control_plane.enums import (
    ChatStatus, JobStatus, JobType
)
from control_plane.versions import create_strategy_version
from control_plane.models import (
    BacktestRun, Dataset, Job, Strategy,
    StrategyVersion, TradingViewTrendingStrategy
)

logger = logging.getLogger(__name__)


def _build_pinescript_conversion_prompt(
    pinescript_source: str,
    script_name: str,
    script_description: str,
) -> str:
    """Build prompt for LLM to convert PineScript to Python (vectorized backtest format)."""
    return f"""Convert the following TradingView PineScript strategy to Python for backtesting.

**Original Script Information:**
- Name: {script_name}
- Description: {script_description}

**PineScript Source Code:**
```pinescript
{pinescript_source}
```

**Conversion Requirements:**

1. **Convert to Python:**
   - Implement as vectorized pandas/numpy operations
   - Prefer using indicators from backtest.indicators when possible:
     - sma(x, window), ema(x, window), rsi(close, window=14)
     - cross_over(a, b), cross_under(a, b), zscore(x, window)
   - Define generate_signals(data: pd.DataFrame, params: dict) -> dict
   - Return {{'entries': bool_array, 'exits': bool_array}}

2. **Maintain Strategy Essence:**
   - Keep the same core trading logic and signals
   - Preserve key parameters (make them configurable via params.get)

3. **Best Practices:**
   - Handle NaN/insufficient data safely
   - Deterministic outputs, no network/file I/O

**Output Format:**
Generate a complete Python strategy file. Output ONLY Python code, no markdown.
"""


def create_temporary_strategy_from_tradingview(
    db: Session,
    rds: redis.Redis,
    tv_strategy: TradingViewTrendingStrategy,
    force_new: bool = False,
) -> tuple[Strategy, StrategyVersion, str]:
    """Create or reuse temporary Strategy from TradingView URL.

    Args:
        force_new: If True, create new strategy even if one exists

    Returns:
        (Strategy, StrategyVersion, pinescript_source)
        If reusing existing strategy, pinescript_source will be empty string
    """
    # Use function-level logger to avoid any import issues
    func_logger = logging.getLogger(__name__)

    func_logger.info(f"Processing trending strategy: {tv_strategy.title}")

    # Strategy name pattern
    strategy_name = f"Trending: {tv_strategy.title[:80]}"

    # Check if strategy already exists
    if not force_new:
        func_logger.info(f"Searching for existing strategy with name: {strategy_name}")
        existing_strategy = db.query(Strategy).filter_by(name=strategy_name).first()
        if existing_strategy:
            # Reuse existing strategy
            func_logger.info(f"Found existing strategy {existing_strategy.id}, reusing it")

            # Get the latest version
            latest_version = db.query(StrategyVersion).filter_by(
                strategy_id=existing_strategy.id
            ).order_by(StrategyVersion.created_at.desc()).first()

            if latest_version:
                func_logger.info(f"Reusing existing version {latest_version.id}")
                return existing_strategy, latest_version, ""
        else:
            func_logger.info(f"No existing strategy found with name: {strategy_name}")

    # Need to create new strategy
    func_logger.info(f"Creating new strategy for: {tv_strategy.title}")

    scraper_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "..", "packages", "tradingview_scraper"
    )
    if scraper_path not in sys.path:
        sys.path.insert(0, scraper_path)

    try:
        from tradingview_scraper import get_pinescript
        func_logger.info(f"Scraping PineScript from: {tv_strategy.url}")
        script_data = get_pinescript(tv_strategy.url)

        if not script_data.get("source"):
            error = script_data.get("error", "Unknown error")
            raise RuntimeError(f"Failed to scrape PineScript: {error}")

        pinescript_source = script_data["source"]
        func_logger.info(f"Successfully scraped PineScript: {len(pinescript_source)} chars")

    except ImportError as e:
        raise RuntimeError(f"tradingview_scraper not installed: {e}")

    print("[DEBUG] About to create Strategy object")
    print(f"[DEBUG] Creating Strategy with name: {strategy_name}")
    try:
        strategy = Strategy(
            name=strategy_name,
            chat_status=ChatStatus.CHATTING,
        )
    except Exception as e:
        import traceback
        print("[DEBUG] Exception during Strategy creation:")
        print(traceback.format_exc())
        raise
    print("[DEBUG] Strategy object created, adding to database")
    db.add(strategy)
    print("[DEBUG] Strategy added to database, flushing...")
    db.flush()
    print("[DEBUG] Database flush successful")

    from control_plane.workspaces import init_strategy_workspace
    print("[DEBUG] About to call init_strategy_workspace")
    init_strategy_workspace("/workspaces", strategy.id)
    print("[DEBUG] Workspace initialized")

    print("[DEBUG] Creating StrategyVersion...")
    version = create_strategy_version(
        db,
        strategy_id=strategy.id,
        version=1,
        prompt=f"Auto-imported from TradingView trending: {tv_strategy.url}",
        llm_meta={
            "source": "trending_backtest",
            "tradingview_url": tv_strategy.url,
            "original_title": tv_strategy.title,
        },
        snapshot=True,
        workspaces_dir="/workspaces",
    )
    print("[DEBUG] StrategyVersion created and snapshotted")

    # Commit so strategy is visible to subsequent queries
    db.commit()
    func_logger.info(f"Committed new strategy {strategy.id}")

    # Skip member creation for temporary trending strategies (system user may not exist)
    # The strategy will be associated with the user who imports it from trending page

    func_logger.info(f"Created temporary strategy {strategy.id}")
    print(f"[DEBUG] About to return from create_temporary_strategy_from_tradingview: strategy={strategy.id}, version={version.id}")
    return strategy, version, pinescript_source


def trigger_llm_conversion(
    db: Session,
    rds: redis.Redis,
    strategy: Strategy,
    version: StrategyVersion,
    pinescript_source: str,
    tv_strategy: TradingViewTrendingStrategy,
) -> Job | None:
    """Create GENERATE_STRATEGY job.

    Returns:
        Job object if conversion was triggered, None if reusing existing strategy
    """
    print(f"[DEBUG] Entered trigger_llm_conversion: strategy={strategy.id}")
    func_logger = logging.getLogger(__name__)

    # If pinescript_source is empty, we're reusing an existing strategy
    if not pinescript_source:
        func_logger.info("Skipping LLM conversion - reusing existing strategy code")
        return None

    conversion_prompt = _build_pinescript_conversion_prompt(
        pinescript_source=pinescript_source,
        script_name=tv_strategy.title,
        script_description=tv_strategy.description or "",
    )

    job = Job(
        type=JobType.GENERATE_STRATEGY.value,
        status=JobStatus.QUEUED.value,
        payload={
            "strategy_id": strategy.id,
            "version_id": version.id,
            "prompt": conversion_prompt,
            "llm_meta": {
                "source": "trending_backtest",
                "trending_strategy_id": tv_strategy.id,
                "tradingview_url": tv_strategy.url,
            },
        },
    )
    db.add(job)
    db.flush()
    db.commit()  # Commit so other workers can see this job

    from control_plane.queue import enqueue_job
    from worker.settings import settings
    enqueue_job(settings.app_workspaces_dir, job.id, job.type, job.payload, priority="batch", redis_client=rds)

    func_logger.info(f"Created conversion job {job.id}")
    return job


def create_backtest_datasets(
    db: Session,
    strategy: Strategy,
    version: StrategyVersion,
    symbols: list[str],
    interval: str = "1h",
    duration_days: int = 90,
) -> list[tuple[Dataset, BacktestRun]]:
    """Create Dataset and BacktestRun records."""
    func_logger = logging.getLogger(__name__)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=duration_days)

    datasets = []
    for symbol in symbols[:3]:
        dataset = Dataset(
            exchange="binance",
            symbol=symbol,
            interval=interval,
            start_ms=int(start_time.timestamp() * 1000),
            end_ms=int(end_time.timestamp() * 1000),
        )
        db.add(dataset)
        db.flush()

        run = BacktestRun(
            strategy_id=strategy.id,
            strategy_version_id=version.id,
            dataset_id=dataset.id,
            status="queued",
            run_path=f"runs/{str(uuid.uuid4())[:10]}/",
            params={
                "symbol": symbol,
                "interval": interval,
                "duration_days": duration_days,
            }
        )
        db.add(run)
        db.flush()

        datasets.append((dataset, run))

    func_logger.info(f"Created {len(datasets)} backtest runs")
    return datasets


def create_backtest_jobs(
    db: Session,
    rds: redis.Redis,
    datasets: list[tuple[Dataset, BacktestRun]],
) -> list[Job]:
    """Create BACKTEST jobs."""
    func_logger = logging.getLogger(__name__)

    jobs = []
    for dataset, run in datasets:
        job = Job(
            type=JobType.BACKTEST.value,
            status=JobStatus.QUEUED.value,
            payload={
                "strategy_id": run.strategy_id,
                "version_id": run.strategy_version_id,
                "run_id": run.id,
                "dataset_id": dataset.id,
            }
        )
        db.add(job)
        db.flush()

        from control_plane.queue import enqueue_job
        from worker.settings import settings
        enqueue_job(settings.app_workspaces_dir, job.id, job.type, job.payload, priority="batch", redis_client=rds)
        jobs.append(job)

    db.commit()  # Commit so other workers can see these jobs
    func_logger.info(f"Created {len(jobs)} backtest jobs")
    return jobs


def wait_for_backtest_completion(
    db: Session,
    run_ids: list[str],
    timeout_seconds: int = 600,
) -> dict[str, dict]:
    """Wait for backtests to complete."""
    func_logger = logging.getLogger(__name__)
    start_time = time.time()
    results = {}

    func_logger.info(f"Waiting for {len(run_ids)} backtests to complete...")

    while time.time() - start_time < timeout_seconds:
        all_done = True

        # Clear session cache to ensure we get fresh data from database
        db.expire_all()

        for run_id in run_ids:
            if run_id in results:
                continue

            # Use query with refresh instead of db.get to ensure fresh data
            run = db.query(BacktestRun).filter_by(id=run_id).first()
            if not run:
                func_logger.warning(f"Backtest run {run_id} not found")
                continue

            func_logger.info(f"Backtest {run_id} status: {run.status}")

            # Handle both uppercase (DB) and lowercase (enum) status values
            status_normalized = run.status.lower() if run.status else ""

            if status_normalized == "succeeded":
                if run.metrics:
                    results[run_id] = run.metrics
                    func_logger.info(f"Backtest {run_id} succeeded with metrics")
                else:
                    results[run_id] = {}
                    func_logger.info(f"Backtest {run_id} succeeded without metrics")

            elif status_normalized == "failed":
                func_logger.error(f"Backtest {run_id} failed")
                results[run_id] = {"error": run.error_message}

            else:
                all_done = False

        if all_done:
            func_logger.info("All backtests completed!")
            break

        time.sleep(5)

    incomplete = [rid for rid in run_ids if rid not in results]
    if incomplete:
        func_logger.warning(f"Timeout: {incomplete}")

    return results


def update_trending_strategy_results(
    db: Session,
    tv_strategy: TradingViewTrendingStrategy,
    backtest_results: dict[str, dict],
) -> None:
    """Update trending strategy with results."""
    func_logger = logging.getLogger(__name__)
    parsed_results = {}

    for symbol, metrics in backtest_results.items():
        if "error" in metrics:
            continue

        total_return = metrics.get("total_return", 0)
        sharpe_ratio = metrics.get("sharpe_ratio", 0)
        win_rate = metrics.get("win_rate", 0)

        parsed_results[symbol] = {
            "total_return": total_return,
            "max_drawdown": metrics.get("max_drawdown", 0),
            "sharpe_ratio": sharpe_ratio,
            "win_rate": win_rate,
            "profit_factor": metrics.get("profit_factor"),
            "run_id": metrics.get("run_id", ""),
        }

    tv_strategy.backtest_results = parsed_results
    tv_strategy.backtest_status = "completed"
    db.flush()
    func_logger.info(f"Updated strategy {tv_strategy.id}: backtest_status=completed")
