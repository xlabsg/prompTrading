"""
Worker job handler for template performance updates.

This module handles the generation of performance data for strategy templates
by running the TEMPLATE_PERFORMANCE_UPDATE job type.
"""

import logging

from sqlalchemy.orm import Session

from control_plane.enums import JobType
from control_plane.models import (
    StrategyTemplate,
    TemplatePerformanceRun,
    TemplateSignal,
    TemplatePerformanceSchedule,
    Job,
)

logger = logging.getLogger(__name__)


def generate_template_performance_data(
    db: Session,
    rds,
    job: Job,
) -> None:
    """
    Generate performance data for templates.

    Process:
    1. Fetch schedule configuration
    2. Select templates that need updates
    3. Generate backtest runs and signals
    4. Save to database

    Args:
        db: Database session
        rds: Redis client for publishing logs
        job: Job instance with payload
    """

    schedule = db.query(TemplatePerformanceSchedule).first()
    if not schedule or not schedule.enabled:
        _publish_log(rds, job.id, "Template performance schedule is disabled or not configured")
        return

    _publish_log(rds, job.id, f"Starting template performance update (batch size: {schedule.templates_per_batch})")

    # Get templates that need updates (public templates)
    templates = db.query(StrategyTemplate).filter(
        StrategyTemplate.is_public == True,
    ).order_by(
        StrategyTemplate.updated_at.asc()  # Update oldest first
    ).limit(schedule.templates_per_batch).all()

    if not templates:
        _publish_log(rds, job.id, "No templates found matching criteria")
        return

    _publish_log(rds, job.id, f"Found {len(templates)} templates to update")

    # Import generator to avoid circular dependency
    import sys
    import os
    # Add API services path to import generator
    api_services_path = os.path.join(os.path.dirname(__file__), '..', '..', 'api', 'app', 'services')
    if api_services_path not in sys.path:
        sys.path.insert(0, api_services_path)

    from template_performance_generator import TemplatePerformanceGenerator

    # Generate data for each template
    updated_count = 0
    for template in templates:
        try:
            generator = TemplatePerformanceGenerator()

            _publish_log(rds, job.id, f"Processing template: {template.name}")

            runs, signals = generator.generate_performance_data(
                db=db,
                template=template,
                days_history=schedule.backtest_days_history,
                run_count=10,  # 10 historical runs
            )

            # Save runs (avoid duplicates)
            runs_added = 0
            for run in runs:
                existing = db.query(TemplatePerformanceRun).filter_by(
                    template_id=template.id,
                    run_date=run.run_date,
                ).first()
                if not existing:
                    db.add(run)
                    runs_added += 1

            # Save signals (limit to max_signals_per_template)
            current_signal_count = db.query(TemplateSignal).filter_by(
                template_id=template.id
            ).count()

            signals_to_add = schedule.max_signals_per_template - current_signal_count
            if signals_to_add > 0:
                new_signals = signals[:signals_to_add]
                for signal in new_signals:
                    db.add(signal)
                _publish_log(rds, job.id, f"  Added {len(new_signals)} signals")
            else:
                _publish_log(rds, job.id, f"  Signal limit reached ({current_signal_count})")

            # Update template's updated_at timestamp
            template.updated_at = template.updated_at  # Trigger onupdate

            db.flush()
            updated_count += 1

            _publish_log(rds, job.id, f"  Completed: {runs_added} backtest runs, {min(signals_to_add, len(signals))} signals")

        except Exception as e:
            logger.error(f"Error generating performance for template {template.id}: {e}", exc_info=True)
            _publish_log(rds, job.id, f"  ERROR: {str(e)}")
            continue

    # Update schedule
    schedule.last_run_at = schedule.last_run_at  # This will trigger update
    db.commit()

    _publish_log(rds, job.id, f"Template performance update completed: {updated_count}/{len(templates)} templates updated")


def _publish_log(rds, job_id: str, message: str) -> None:
    """Publish a log message to Redis."""
    if rds is None:
        return
    try:
        import redis
        import json

        channel = f"job:{job_id}:logs"
        log_entry = {
            "job_id": job_id,
            "message": message,
            "timestamp": None,  # Will be set by subscriber
            "level": "info",
        }
        rds.publish(channel, json.dumps(log_entry))
    except Exception as e:
        # Don't fail the job if logging fails
        logger.warning(f"Failed to publish log: {e}")
