from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from control_plane.models import Job
from app.deps import get_db, get_session_factory
from app.schemas import JobResponse
from app.settings import settings

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job


def _detect_step_from_line(line: str) -> str | None:
    """Helper to detect logical pipeline step from worker/agent log line."""
    if not line:
        return None
    lower = line.lower()
    if "seeded workspace with" in lower or "tau provider=" in lower:
        return "initializing_agent"
    if "backtest dataset=" in lower or "backtest subprocess" in lower:
        return "running_backtest"
    if "ast audit passed" in lower or "ast audit detected" in lower:
        return "auditing_code"
    if "session summary" in lower or "wrote strategy.py" in lower:
        return "finalizing_strategy"
    if "backtest.log" in lower or "metrics.json" in lower:
        return "evaluating_metrics"
    return None


@router.get("/jobs/{job_id}/stream")
async def stream_job_events(
    job_id: str,
    request: Request,
    session_factory=Depends(get_session_factory),
) -> StreamingResponse:
    """Stream real-time log lines and pipeline steps for a job via Server-Sent Events."""
    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        # Both columns are plain Strings, so a loaded row yields a str.
        initial_status = getattr(job.status, "value", job.status) or "queued"
        job_type = getattr(job.type, "value", job.type) or ""

    log_path = os.path.join(settings.workspaces_dir, ".queue", "logs", f"{job_id}.log")
    done_marker = f"{log_path}.done"

    async def event_generator() -> AsyncGenerator[str, None]:
        # Send initial status
        yield f"event: status\ndata: {json.dumps({'status': initial_status, 'job_id': job_id, 'job_type': job_type})}\n\n"

        # Wait up to 30s for the job log file to appear
        wait_count = 0
        while not os.path.exists(log_path) and wait_count < 300:
            if await request.is_disconnected():
                return
            if os.path.exists(done_marker):
                break
            await asyncio.sleep(0.1)
            wait_count += 1

        idle_ticks = 0
        file_pos = 0

        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                while True:
                    if await request.is_disconnected():
                        return

                    line = f.readline()
                    if line:
                        idle_ticks = 0
                        clean_line = line.rstrip("\r\n")
                        yield f"event: log\ndata: {json.dumps({'line': clean_line})}\n\n"

                        step = _detect_step_from_line(clean_line)
                        if step:
                            yield f"event: step\ndata: {json.dumps({'step': step, 'detail': clean_line})}\n\n"
                    else:
                        if os.path.exists(done_marker):
                            # Drain any remaining lines
                            tail_line = f.readline()
                            while tail_line:
                                clean_tail = tail_line.rstrip("\r\n")
                                yield f"event: log\ndata: {json.dumps({'line': clean_tail})}\n\n"
                                tail_line = f.readline()
                            break

                        await asyncio.sleep(0.15)
                        idle_ticks += 1
                        if idle_ticks > 4000:  # Timeout after 10 min idle
                            break

        # Check final job status from database
        with session_factory() as db:
            final_job = db.get(Job, job_id)
            final_status = (
                getattr(final_job.status, "value", final_job.status)
                if (final_job and final_job.status)
                else "unknown"
            )
            error_message = final_job.error_message if final_job else None

        yield f"event: finish\ndata: {json.dumps({'status': final_status, 'error_message': error_message})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

