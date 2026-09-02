"""
Template Backtest Service

Runs real backtests for strategy templates using their built-in code.
"""
import os
import uuid
import shutil
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from control_plane.models import (
    StrategyTemplate,
    Strategy,
    StrategyVersion,
    Job,
    BacktestRun,
    Dataset,
    TemplatePerformanceRun,
    TemplateSignal,
)
from control_plane.enums import JobStatus, JobType, StrategyTemplateType
from control_plane.workspaces import (
    init_strategy_workspace,
)
from app.settings import settings


class TemplateBacktestService:
    """Service for running real backtests on templates."""

    # Default backtest configuration
    DEFAULT_EXCHANGE = "okx"
    DEFAULT_SYMBOL = "BTCUSDT"
    DEFAULT_INTERVAL = "1h"
    DEFAULT_DAYS = 90
    MAX_SIGNALS_PER_TEMPLATE = 100

    def __init__(self, db: Session, redis_client=None):
        self.db = db
        self.redis = redis_client

    def run_backtest_for_template(
        self,
        template: StrategyTemplate,
        days: int = DEFAULT_DAYS,
    ) -> Optional[BacktestRun]:
        """
        Run a real backtest for a builtin template.

        Uses the strategy code embedded in the template's prompt field.
        """
        # Only works for builtin templates with embedded code
        if template.template_type != StrategyTemplateType.BUILTIN.value:
            return None

        # Extract code from prompt
        code = self._extract_code_from_prompt(template.prompt)
        if not code:
            return None

        # Calculate date range
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        # Get trading parameters from config or use defaults
        config = template.config_snapshot or {}
        symbol = config.get("symbols", [self.DEFAULT_SYMBOL])[0] if config.get("symbols") else self.DEFAULT_SYMBOL
        exchange = config.get("exchange", self.DEFAULT_EXCHANGE)
        interval = config.get("intervals", [self.DEFAULT_INTERVAL])[0] if config.get("intervals") else self.DEFAULT_INTERVAL

        # Create temporary strategy from template
        temp_strategy = self._create_temp_strategy(template, code)
        if not temp_strategy:
            return None

        try:
            # Create backtest job
            job = self._create_backtest_job(
                strategy_id=temp_strategy.id,
                exchange=exchange,
                symbol=symbol,
                interval=interval,
                start_ms=start_ms,
                end_ms=end_ms,
            )

            # Wait for job to complete (with timeout)
            backtest_run = self._wait_for_backtest(job.id, timeout_seconds=600)

            if backtest_run and backtest_run.status == "succeeded":
                # Store results in template_performance_runs
                self._store_performance_run(
                    template_id=template.id,
                    backtest_run=backtest_run,
                    exchange=exchange,
                    symbol=symbol,
                    interval=interval,
                )

                # Extract and store signals
                self._extract_and_store_signals(
                    template_id=template.id,
                    backtest_run=backtest_run,
                )

                return backtest_run

        finally:
            # Cleanup temp strategy
            self._cleanup_temp_strategy(temp_strategy.id)

        return None

    def run_backtests_for_all_templates(
        self,
        days: int = DEFAULT_DAYS,
        limit: int = 5,
    ) -> dict[str, str]:
        """
        Run backtests for multiple templates (oldest updated first).

        Returns a dict mapping template_id to status.
        """
        # Get builtin templates that need updating, sorted by oldest updated_at
        templates = self.db.execute(
            select(StrategyTemplate)
            .where(StrategyTemplate.template_type == StrategyTemplateType.BUILTIN.value)
            .where(StrategyTemplate.is_public == True)
            .order_by(StrategyTemplate.updated_at.asc())
            .limit(limit)
        ).scalars().all()

        results = {}
        for template in templates:
            try:
                backtest_run = self.run_backtest_for_template(template, days=days)
                if backtest_run:
                    results[template.id] = "success"
                else:
                    results[template.id] = "failed"
            except Exception as e:
                results[template.id] = f"error: {str(e)}"

        return results

    def _extract_code_from_prompt(self, prompt: str) -> Optional[str]:
        """Extract Python code from template prompt."""
        if not prompt:
            return None

        # The prompt already contains the full class definition
        # Just wrap it in the necessary structure
        code = f'''{prompt}

# Required imports
from strategy_sdk import *
'''

        return code

    def _create_temp_strategy(
        self,
        template: StrategyTemplate,
        code: str,
    ) -> Optional[Strategy]:
        """Create a temporary strategy from template code."""
        strategy_id = str(uuid.uuid4())
        strategy = Strategy(
            id=strategy_id,
            name=f"[TEMP-BT] {template.name}",
            chat_status="done",
        )
        self.db.add(strategy)
        self.db.flush()

        # Create version with code
        version_id = str(uuid.uuid4())
        workspace_path = f"temp/template_bt/{version_id}/"

        # Initialize workspace and write code
        full_workspace_path = os.path.join(settings.workspaces_dir, workspace_path)
        os.makedirs(full_workspace_path, exist_ok=True)

        strategy_file = os.path.join(full_workspace_path, "strategy.py")
        with open(strategy_file, "w") as f:
            f.write(code)

        version = StrategyVersion(
            id=version_id,
            strategy_id=strategy_id,
            version=1,
            workspace_path=workspace_path,
            prompt=template.prompt,
            llm_meta={
                "source": "template_backtest",
                "template_id": template.id,
                "template_version": template.version,
            },
        )
        self.db.add(version)
        self.db.commit()

        return strategy

    def _create_backtest_job(
        self,
        strategy_id: str,
        exchange: str,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
    ) -> Job:
        """Create and queue a backtest job."""
        # Create dataset
        dataset = Dataset(
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        self.db.add(dataset)
        self.db.flush()

        # Get the strategy version
        versions = self.db.execute(
            select(StrategyVersion).where(StrategyVersion.strategy_id == strategy_id)
        ).scalars().all()

        if not versions:
            raise RuntimeError(f"No version found for strategy {strategy_id}")

        version_id = versions[0].id

        # Create backtest run
        backtest_run = BacktestRun(
            strategy_id=strategy_id,
            status="queued",
            run_path=f"runs/{uuid.uuid4()}/",
            params={
                "dataset": {
                    "exchange": exchange,
                    "symbol": symbol,
                    "interval": interval,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                }
            },
        )
        self.db.add(backtest_run)
        self.db.flush()

        # Create job
        job = Job(
            type=JobType.BACKTEST,
            status=JobStatus.QUEUED,
            payload={
                "strategy_id": strategy_id,
                "version_id": version_id,
                "run_id": backtest_run.id,
                "dataset_id": dataset.id,
            },
        )
        self.db.add(job)
        self.db.commit()

        from control_plane.queue import enqueue_job
        enqueue_job(
            settings.workspaces_dir,
            job.id,
            job.type.value if hasattr(job.type, "value") else str(job.type),
            job.payload,
            priority="batch",
            redis_client=self.redis,
        )

        return job

    def _wait_for_backtest(
        self,
        job_id: str,
        timeout_seconds: int = 600,
        check_interval: int = 5,
    ) -> Optional[BacktestRun]:
        """Wait for backtest job to complete."""
        import time
        from sqlalchemy import select

        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            job = self.db.get(Job, job_id)
            if not job:
                return None

            if job.status in [JobStatus.SUCCEEDED, JobStatus.FAILED]:
                # Get backtest run
                backtest_run_id = job.payload.get("backtest_run_id")
                if backtest_run_id:
                    return self.db.get(BacktestRun, backtest_run_id)
                return None

            # Refresh database session
            self.db.expire_all()
            time.sleep(check_interval)

        return None

    def _store_performance_run(
        self,
        template_id: str,
        backtest_run: BacktestRun,
        exchange: str,
        symbol: str,
        interval: str,
    ):
        """Store backtest results in template_performance_runs."""
        performance_run = TemplatePerformanceRun(
            id=str(uuid.uuid4()),
            template_id=template_id,
            run_date=datetime.now(timezone.utc),
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start_ms=backtest_run.params.get("dataset", {}).get("start_ms"),
            end_ms=backtest_run.params.get("dataset", {}).get("end_ms"),
            metrics=backtest_run.metrics or {},
            status="succeeded" if backtest_run.status == "succeeded" else "failed",
        )
        self.db.add(performance_run)
        self.db.commit()

    def _extract_and_store_signals(
        self,
        template_id: str,
        backtest_run: BacktestRun,
    ):
        """Extract trading signals from backtest and store them."""
        # Get trades from backtest results
        metrics = backtest_run.metrics or {}
        trades = metrics.get("trades", [])

        if not trades:
            return

        # Count existing signals
        existing_count = self.db.execute(
            select(func.count(TemplateSignal.id)).where(TemplateSignal.template_id == template_id)
        ).scalar() or 0

        # Calculate how many new signals we can add
        slots_available = self.MAX_SIGNALS_PER_TEMPLATE - existing_count

        # Delete oldest signals if we're at capacity
        if slots_available < len(trades) and existing_count > 0:
            to_delete = min(existing_count, len(trades) - slots_available)
            old_signals = self.db.execute(
                select(TemplateSignal)
                .where(TemplateSignal.template_id == template_id)
                .order_by(TemplateSignal.created_at.asc())
                .limit(to_delete)
            ).scalars().all()
            for sig in old_signals:
                self.db.delete(sig)

        # Add new signals (most recent last)
        for trade in trades[-slots_available:] if slots_available > 0 else []:
            signal = TemplateSignal(
                id=str(uuid.uuid4()),
                template_id=template_id,
                symbol=trade.get("symbol", "BTCUSDT"),
                side=trade.get("side", "buy"),
                price=trade.get("entry_price", 0),
                confidence=0.75,  # Default confidence
                status="executed",
                entry_price=trade.get("entry_price"),
                exit_price=trade.get("exit_price"),
                pnl=trade.get("return_pct"),
                hold_duration_hours=trade.get("duration_hours"),
                created_at=datetime.now(timezone.utc),
                executed_at=datetime.now(timezone.utc),
            )
            self.db.add(signal)

        self.db.commit()

    def _cleanup_temp_strategy(self, strategy_id: str):
        """Clean up temporary strategy and its files."""
        # Get strategy and versions
        strategy = self.db.get(Strategy, strategy_id)
        if not strategy:
            return

        versions = self.db.execute(
            select(StrategyVersion).where(StrategyVersion.strategy_id == strategy_id)
        ).scalars().all()

        # Delete workspace files
        for version in versions:
            workspace_path = os.path.join(settings.workspaces_dir, version.workspace_path)
            if os.path.exists(workspace_path):
                shutil.rmtree(workspace_path, ignore_errors=True)

        # Delete database records
        self.db.delete(strategy)
        self.db.commit()
