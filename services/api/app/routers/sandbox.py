from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import select

from control_plane.enums import JobStatus, JobType, SandboxStatus, StrategyRole
from control_plane.models import Job, SandboxSession, Strategy
from control_plane.queue import QUEUE_NAME
from app.auth import require_strategy_member
from app.deps import get_db, get_redis
from app.schemas import JobResponse, SandboxCreateResponse, TriggerJobResponse
from app.settings import settings

router = APIRouter()


@router.post("/strategies/{strategy_id}/sandbox", response_model=TriggerJobResponse)
def start_sandbox(
    strategy_id: str,
    request: Request,
    db: Session = Depends(get_db),
    rds=Depends(get_redis),
) -> TriggerJobResponse:
    require_strategy_member(request, db, strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")

    session = SandboxSession(
        strategy_id=strategy_id,
        status=SandboxStatus.STARTING,
        secret_token=secrets.token_hex(32),
        url_path="",
    )
    db.add(session)
    db.flush()
    # Put token into the path so that all static asset requests carry it too.
    session.url_path = f"/sandbox/{session.id}/{session.secret_token}"

    job = Job(
        type=JobType.START_SANDBOX,
        status=JobStatus.QUEUED,
        payload={"strategy_id": strategy_id, "session_id": session.id},
    )
    db.add(job)
    db.flush()

    db.commit()
    rds.rpush(QUEUE_NAME, json.dumps({"job_id": job.id}))

    sandbox_url = f"{settings.sandbox_base_url}{session.url_path}/"
    db.refresh(job)
    return TriggerJobResponse(job=job, sandbox_url=sandbox_url)


@router.delete("/sandbox/{session_id}", response_model=JobResponse)
def stop_sandbox(session_id: str, request: Request, db: Session = Depends(get_db), rds=Depends(get_redis)) -> JobResponse:
    session = db.get(SandboxSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="sandbox_not_found")
    require_strategy_member(request, db, session.strategy_id, [StrategyRole.ADMIN, StrategyRole.EDITOR])

    job = Job(
        type=JobType.STOP_SANDBOX,
        status=JobStatus.QUEUED,
        payload={"strategy_id": session.strategy_id, "session_id": session.id},
    )
    db.add(job)
    db.flush()
    db.commit()
    rds.rpush(QUEUE_NAME, json.dumps({"job_id": job.id}))
    db.refresh(job)
    return job


@router.get("/sandbox/{session_id}", response_model=SandboxCreateResponse)
def get_sandbox(session_id: str, request: Request, db: Session = Depends(get_db)) -> SandboxCreateResponse:
    session = db.get(SandboxSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="sandbox_not_found")
    require_strategy_member(request, db, session.strategy_id)
    return session


@router.get("/strategies/{strategy_id}/sandboxes", response_model=list[SandboxCreateResponse])
def list_sandboxes(strategy_id: str, request: Request, db: Session = Depends(get_db)) -> list[SandboxCreateResponse]:
    require_strategy_member(request, db, strategy_id)
    rows = (
        db.execute(select(SandboxSession).where(SandboxSession.strategy_id == strategy_id).order_by(SandboxSession.created_at.desc()))
        .scalars()
        .all()
    )
    return rows
