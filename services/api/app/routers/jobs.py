from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from control_plane.models import Job
from app.deps import get_db
from app.schemas import JobResponse

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job

