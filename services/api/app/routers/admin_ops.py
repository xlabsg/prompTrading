from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin import require_admin
from app.deps import get_db, get_redis
from control_plane.enums import JobStatus, JobType
from control_plane.models import Job, StrategyTemplate, TradingViewTrendingStrategy
from control_plane.queue import QUEUE_NAME

router = APIRouter()

LOG_TAIL_KEY_PREFIX = "jobs:logtail:v1:"
LAST_LOG_KEY_PREFIX = "jobs:lastlog:v1:"
CANCEL_KEY_PREFIX = "jobs:cancel:v1:"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AdminQueueResponse(BaseModel):
    queue_name: str = QUEUE_NAME
    length: int
    head: list[str] = Field(default_factory=list)


class AdminJobRow(BaseModel):
    id: str
    type: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    last_log: Optional[str] = None


class AdminJobsResponse(BaseModel):
    jobs: list[AdminJobRow]


class AdminLogTailResponse(BaseModel):
    job_id: str
    lines: list[str]


class AdminCancelResponse(BaseModel):
    job_id: str
    status: JobStatus


class AdminTrendingStrategyRow(BaseModel):
    id: str
    source_type: str
    tradingview_id: str
    title: str
    url: str
    likes: int
    views: int
    comments: int
    scraped_at: datetime
    backtest_status: str
    template_id: Optional[str] = None


class AdminTrendingStrategiesResponse(BaseModel):
    items: list[AdminTrendingStrategyRow]


class AdminDeleteTrendingStrategyRequest(BaseModel):
    tradingview_id: str


@router.get("/admin/queue", response_model=AdminQueueResponse)
def admin_queue(
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
    head_n: int = Query(10, ge=0, le=50),
) -> AdminQueueResponse:
    require_admin(request, db=db)
    length = int(rds.llen(QUEUE_NAME))
    head_raw = rds.lrange(QUEUE_NAME, 0, max(0, head_n - 1)) if head_n else []
    head: list[str] = []
    for raw in head_raw or []:
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict) and payload.get("job_id"):
                head.append(str(payload["job_id"]))
            elif isinstance(payload, str):
                head.append(payload)
        except Exception:
            head.append(str(raw))
    return AdminQueueResponse(length=length, head=head)


@router.get("/admin/jobs", response_model=AdminJobsResponse)
def admin_jobs(
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
    limit: int = Query(50, ge=1, le=200),
    types: Optional[str] = Query(None, description="Comma-separated job types"),
) -> AdminJobsResponse:
    require_admin(request, db=db)
    type_list: list[str] | None = None
    if types:
        type_list = [t.strip() for t in types.split(",") if t.strip()]

    q = select(Job).order_by(Job.created_at.desc()).limit(limit)
    if type_list:
        q = q.where(Job.type.in_(type_list))
    rows = db.execute(q).scalars().all()

    jobs: list[AdminJobRow] = []
    for job in rows:
        last_log = rds.get(f"{LAST_LOG_KEY_PREFIX}{job.id}")
        jobs.append(
            AdminJobRow(
                id=job.id,
                type=job.type,
                status=JobStatus(job.status),
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                error_message=job.error_message,
                last_log=last_log,
            )
        )
    return AdminJobsResponse(jobs=jobs)


@router.get("/admin/jobs/{job_id}/logs", response_model=AdminLogTailResponse)
def admin_job_logs(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
    tail: int = Query(120, ge=1, le=500),
) -> AdminLogTailResponse:
    require_admin(request, db=db)
    key = f"{LOG_TAIL_KEY_PREFIX}{job_id}"
    lines = rds.lrange(key, max(0, -tail), -1) or []
    return AdminLogTailResponse(job_id=job_id, lines=[str(x) for x in lines])


@router.post("/admin/jobs/{job_id}/cancel", response_model=AdminCancelResponse)
def admin_cancel_job(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
) -> AdminCancelResponse:
    require_admin(request, db=db)
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")

    try:
        status = JobStatus(str(job.status))
    except Exception:
        # Unknown/legacy states: treat as not cancellable to avoid unsafe transitions.
        raise HTTPException(status_code=409, detail=f"job_not_cancellable:{job.status}")

    if status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(status_code=409, detail=f"job_not_cancellable:{status.value}")

    # Signal cancel to workers (running jobs) and remove from queue (queued jobs).
    rds.setex(f"{CANCEL_KEY_PREFIX}{job_id}", 3600, "1")
    try:
        # Producers sometimes push a raw job_id string, and sometimes push a JSON object
        # with extra fields (type/payload). Remove any queue entries pointing to this job.
        rds.lrem(QUEUE_NAME, 0, job_id)
        for raw in rds.lrange(QUEUE_NAME, 0, -1) or []:
            try:
                payload = json.loads(raw)
                if isinstance(payload, dict) and str(payload.get("job_id") or "") == job_id:
                    rds.lrem(QUEUE_NAME, 0, raw)
            except Exception:
                continue
    except Exception:
        pass

    # If not started yet, cancel immediately in DB.
    if status == JobStatus.QUEUED:
        job.status = JobStatus.CANCELLED.value
        job.finished_at = _utcnow()
        job.error_message = "cancelled_by_admin"
        db.flush()
        db.commit()
        return AdminCancelResponse(job_id=job_id, status=JobStatus.CANCELLED)

    # Running: let worker observe cancel flag and finalize status.
    return AdminCancelResponse(job_id=job_id, status=status)


@router.get("/admin/trending/strategies", response_model=AdminTrendingStrategiesResponse)
def admin_trending_strategies(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
) -> AdminTrendingStrategiesResponse:
    require_admin(request, db=db)
    rows = (
        db.execute(select(TradingViewTrendingStrategy).order_by(TradingViewTrendingStrategy.scraped_at.desc()).limit(limit))
        .scalars()
        .all()
    )
    template_ids_by_source: dict[str, str] = {}
    if rows:
        source_ids = [row.id for row in rows]
        template_rows = (
            db.execute(
                select(StrategyTemplate.id, StrategyTemplate.source_id)
                .where(StrategyTemplate.source_id.in_(source_ids))
            )
            .all()
        )
        template_ids_by_source = {
            str(row.source_id): str(row.id)
            for row in template_rows
            if row.source_id
        }

    items = [
        AdminTrendingStrategyRow(
            id=row.id,
            source_type=row.source_type,
            tradingview_id=row.tradingview_id,
            title=row.title,
            url=row.url,
            likes=int(row.likes or 0),
            views=int(row.views or 0),
            comments=int(row.comments or 0),
            scraped_at=row.scraped_at,
            backtest_status=row.backtest_status,
            template_id=template_ids_by_source.get(str(row.id)),
        )
        for row in rows
    ]
    return AdminTrendingStrategiesResponse(items=items)


@router.delete("/admin/trending/strategies", response_model=dict)
def admin_delete_trending_strategy_body(
    payload: AdminDeleteTrendingStrategyRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Delete a scraped TradingView strategy row by tradingview_id.

    This endpoint uses a request body so tradingview_id can safely include characters
    that don't work well in a URL path (e.g. slashes in legacy ids).
    """
    require_admin(request, db=db)
    tradingview_id = payload.tradingview_id.strip()
    if not tradingview_id:
        raise HTTPException(status_code=422, detail="tradingview_id_required")
    row = db.execute(
        select(TradingViewTrendingStrategy).where(TradingViewTrendingStrategy.tradingview_id == tradingview_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="trending_strategy_not_found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.delete("/admin/trending/strategies/{tradingview_id}", response_model=dict)
def admin_delete_trending_strategy(
    tradingview_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_admin(request, db=db)
    row = db.execute(
        select(TradingViewTrendingStrategy).where(TradingViewTrendingStrategy.tradingview_id == tradingview_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="trending_strategy_not_found")
    db.delete(row)
    db.commit()
    return {"ok": True}
