"""
Template Backtest API endpoints

Provides endpoints for running real backtests on strategy templates.
"""
from datetime import datetime, timezone
from typing import Any, Optional
import json
import os
from fastapi import APIRouter, Depends, HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.models import StrategyTemplate, Job, BacktestRun
from control_plane.enums import JobType, JobStatus
from control_plane.queue import QUEUE_NAME
from control_plane.workspaces import get_run_dir
from app.admin import require_admin
from app.deps import get_db, get_redis
from app.schemas import BacktestRunResponse
from app.settings import settings


router = APIRouter()


def _normalize_equity_curve_payload(base_dir: str, payload: dict) -> dict:
    """Normalize equity curve timestamps to milliseconds for frontend charting."""
    if not isinstance(payload, dict):
        return payload
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return payload

    timestamps: list[int] = []
    for point in data:
        if isinstance(point, dict):
            ts = point.get("timestamp")
            if isinstance(ts, (int, float)):
                timestamps.append(int(ts))
    if not timestamps:
        return payload

    max_ts = max(timestamps)

    if max_ts < 1_000_000_000:
        equity_parquet = os.path.join(base_dir, "equity.parquet")
        if os.path.isfile(equity_parquet):
            try:
                import pandas as pd

                df = pd.read_parquet(equity_parquet, columns=["timestamp", "equity", "drawdown"])
                rebuilt = [
                    {
                        "timestamp": int(row["timestamp"]),
                        "equity": round(float(row["equity"]), 2),
                        "drawdown": round(abs(float(row["drawdown"])) * 100, 2),
                    }
                    for _, row in df.iterrows()
                ]
                return {"data": rebuilt}
            except Exception:
                return payload
        return payload

    if max_ts < 1_000_000_000_000:
        normalized = []
        for point in data:
            if not isinstance(point, dict):
                continue
            ts = point.get("timestamp")
            if isinstance(ts, (int, float)):
                next_point = dict(point)
                next_point["timestamp"] = int(ts * 1000)
                normalized.append(next_point)
            else:
                normalized.append(point)
        return {"data": normalized}

    return payload


# ============== Request/Response Schemas ==============


class RunBacktestRequest(BaseModel):
    """Request to run a backtest for a template."""
    days: int = Field(default=30, ge=7, le=90, description="Number of days of historical data (7-90)")


class RunBacktestResponse(BaseModel):
    """Response after triggering a backtest."""
    message: str
    template_id: str
    template_name: str
    job_id: str


class RunStable5ScreeningRequest(BaseModel):
    """Request to run Stable5 screening for templates."""
    limit: int = Field(default=20, ge=1, le=200, description="Max templates to screen")
    template_ids: Optional[list[str]] = Field(default=None, description="Optional explicit template IDs to screen")


class RunStable5ScreeningResponse(BaseModel):
    message: str
    job_id: str


class Stable5RecommendationItem(BaseModel):
    id: str
    name: str
    description: str | None
    template_type: str
    author: str | None
    tags: list[str] | None
    subscriber_count: int
    is_featured: bool
    stable5: dict


# ============== API Endpoints ==============


@router.post("/templates/{template_id}/backtest", response_model=RunBacktestResponse)
async def run_template_backtest(
    template_id: str,
    req: RunBacktestRequest,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
) -> RunBacktestResponse:
    """
    Run a real backtest for a template.

    This will:
    1. Create a job to run the backtest
    2. The worker will process it and store results

    Only works for builtin templates with embedded code.
    """
    template = db.query(StrategyTemplate).filter_by(id=template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if template.template_type != "builtin":
        raise HTTPException(
            status_code=400,
            detail="Real backtests only supported for builtin templates"
        )

    # Create job
    job = Job(
        type=JobType.TEMPLATE_BACKTEST,
        status=JobStatus.QUEUED,
        payload={
            "template_id": template_id,
            "days": req.days,
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Queue job in Redis
    import json
    rds.rpush(QUEUE_NAME, json.dumps({
        "job_id": job.id,
        "type": job.type,
        "payload": job.payload,
    }))

    return RunBacktestResponse(
        message=f"Backtest job queued for template '{template.name}'",
        template_id=template.id,
        template_name=template.name,
        job_id=job.id,
    )


@router.get("/templates/{template_id}/backtests", response_model=list[BacktestRunResponse])
async def list_template_backtests(
    template_id: str,
    db: Session = Depends(get_db),
) -> list[BacktestRunResponse]:
    template = db.query(StrategyTemplate).filter_by(id=template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    rows = (
        db.execute(
            select(BacktestRun)
            .where(BacktestRun.params["template_id"].astext == template_id)
            .order_by(BacktestRun.created_at.desc())
        )
        .scalars()
        .all()
    )
    return rows


def _get_template_run_or_404(db: Session, template_id: str, run_id: str) -> BacktestRun:
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest_run_not_found")
    if (run.params or {}).get("template_id") != template_id:
        raise HTTPException(status_code=404, detail="backtest_run_not_found")
    return run


@router.get("/templates/{template_id}/backtests/{run_id}", response_model=BacktestRunResponse)
async def get_template_backtest_run(
    template_id: str,
    run_id: str,
    db: Session = Depends(get_db),
) -> BacktestRunResponse:
    return _get_template_run_or_404(db, template_id, run_id)


@router.get("/templates/{template_id}/backtests/{run_id}/artifacts", response_model=list[str])
async def list_template_backtest_artifacts(
    template_id: str,
    run_id: str,
    db: Session = Depends(get_db),
) -> list[str]:
    run = _get_template_run_or_404(db, template_id, run_id)
    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    try:
        return sorted([name for name in os.listdir(base_dir) if not name.startswith(".")])
    except FileNotFoundError:
        return []


@router.get("/templates/{template_id}/backtests/{run_id}/artifacts/{artifact_name}")
async def download_template_backtest_artifact(
    template_id: str,
    run_id: str,
    artifact_name: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    run = _get_template_run_or_404(db, template_id, run_id)
    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    path = os.path.join(base_dir, artifact_name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="artifact_not_found")
    return FileResponse(path)


@router.get("/templates/{template_id}/backtests/{run_id}/equity_curve")
async def get_template_equity_curve(
    template_id: str,
    run_id: str,
    db: Session = Depends(get_db),
):
    run = _get_template_run_or_404(db, template_id, run_id)
    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    equity_file = os.path.join(base_dir, "equity_curve.json")
    if not os.path.isfile(equity_file):
        raise HTTPException(status_code=404, detail="equity_curve_not_found")
    with open(equity_file, "r") as f:
        payload = json.load(f)
    return _normalize_equity_curve_payload(base_dir, payload)


@router.get("/templates/{template_id}/backtests/{run_id}/trades")
async def get_template_trades(
    template_id: str,
    run_id: str,
    db: Session = Depends(get_db),
):
    run = _get_template_run_or_404(db, template_id, run_id)
    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    trades_file = os.path.join(base_dir, "trades.json")
    if not os.path.isfile(trades_file):
        raise HTTPException(status_code=404, detail="trades_not_found")
    with open(trades_file, "r") as f:
        return json.load(f)


@router.get("/templates/{template_id}/backtests/{run_id}/orders")
async def get_template_orders(
    template_id: str,
    run_id: str,
    db: Session = Depends(get_db),
):
    run = _get_template_run_or_404(db, template_id, run_id)
    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    path = os.path.join(base_dir, "orders.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="orders_not_found")
    with open(path, "r") as f:
        return json.load(f)


@router.get("/templates/{template_id}/backtests/{run_id}/positions")
async def get_template_positions(
    template_id: str,
    run_id: str,
    db: Session = Depends(get_db),
):
    run = _get_template_run_or_404(db, template_id, run_id)
    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    path = os.path.join(base_dir, "positions.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="positions_not_found")
    with open(path, "r") as f:
        return json.load(f)


@router.get("/templates/{template_id}/backtests/{run_id}/signals")
async def get_template_signals(
    template_id: str,
    run_id: str,
    db: Session = Depends(get_db),
):
    run = _get_template_run_or_404(db, template_id, run_id)
    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    path = os.path.join(base_dir, "signals.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="signals_not_found")
    with open(path, "r") as f:
        return json.load(f)


@router.get("/templates/{template_id}/backtests/{run_id}/signals/events")
async def get_template_signal_events(
    template_id: str,
    run_id: str,
    db: Session = Depends(get_db),
):
    run = _get_template_run_or_404(db, template_id, run_id)
    base_dir = get_run_dir(settings.workspaces_dir, run.strategy_id, run.id)
    path = os.path.join(base_dir, "signal_events.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="signal_events_not_found")
    with open(path, "r") as f:
        return json.load(f)


@router.post("/templates/screening/stable5", response_model=RunStable5ScreeningResponse)
async def run_stable5_screening(
    req: RunStable5ScreeningRequest,
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
) -> RunStable5ScreeningResponse:
    """Run Stable5 screening on OKX BTC/ETH perpetuals (1h + 4h, ≥1y)."""
    require_admin(request, db=db)
    job = Job(
        type=JobType.TEMPLATE_STABLE5_SCREENING,
        status=JobStatus.QUEUED,
        payload={
            "limit": req.limit,
            "template_ids": req.template_ids,
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    import json

    rds.rpush(
        QUEUE_NAME,
        json.dumps(
            {
                "job_id": job.id,
                "type": job.type,
                "payload": job.payload,
            }
        ),
    )

    return RunStable5ScreeningResponse(message="Stable5 screening job queued", job_id=job.id)


@router.get("/templates/recommendations/stable5", response_model=list[Stable5RecommendationItem])
async def get_stable5_recommendations(
    limit: int = 10,
    db: Session = Depends(get_db),
) -> list[Stable5RecommendationItem]:
    """Return Stable5 recommendations.

    Preference order:
    1) Templates that pass Stable5 gate (qualifies=true), sorted by score
    2) If none qualify yet but some have Stable5 data, return top candidates by score
    """
    limit = max(1, min(int(limit), 50))
    templates = (
        db.query(StrategyTemplate)
        .filter(StrategyTemplate.is_public == True)
        .all()
    )

    qualifying: list[tuple[float, StrategyTemplate, dict[str, Any]]] = []
    candidates: list[tuple[float, StrategyTemplate, dict[str, Any]]] = []
    for t in templates:
        stable5 = (t.backtest_summary or {}).get("stable5")
        if not isinstance(stable5, dict):
            continue
        score = float(stable5.get("score") or 0.0)
        if bool(stable5.get("qualifies")):
            qualifying.append((score, t, stable5))
        else:
            candidates.append((score, t, stable5))

    rows = qualifying if qualifying else candidates
    rows.sort(key=lambda x: x[0], reverse=True)
    out: list[Stable5RecommendationItem] = []
    for score, t, stable5 in rows[:limit]:
        out.append(
            Stable5RecommendationItem(
                id=t.id,
                name=t.name,
                description=t.description,
                template_type=t.template_type,
                author=t.author,
                tags=t.tags or [],
                subscriber_count=int(t.subscriber_count or 0),
                is_featured=bool(t.is_featured),
                stable5=stable5,
            )
        )
    return out


@router.get("/templates/{template_id}/backtest/status")
async def get_backtest_status(
    template_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Get backtest status for a template."""
    template = db.query(StrategyTemplate).filter_by(id=template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Count performance runs
    from sqlalchemy import func
    from control_plane.models import TemplatePerformanceRun, TemplateSignal

    performance_count = db.query(func.count(TemplatePerformanceRun.id)).filter(
        TemplatePerformanceRun.template_id == template_id
    ).scalar() or 0

    signals_count = db.query(func.count(TemplateSignal.id)).filter(
        TemplateSignal.template_id == template_id
    ).scalar() or 0

    # Get latest performance run
    latest_run = db.query(TemplatePerformanceRun).filter(
        TemplatePerformanceRun.template_id == template_id
    ).order_by(TemplatePerformanceRun.run_date.desc()).first()

    return {
        "template_id": template_id,
        "template_name": template.name,
        "performance_runs_count": performance_count,
        "signals_count": signals_count,
        "latest_backtest_date": latest_run.run_date if latest_run else None,
        "last_updated": template.updated_at,
    }
