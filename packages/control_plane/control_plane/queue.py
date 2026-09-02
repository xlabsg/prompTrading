from __future__ import annotations

import json
import os
from typing import Any, Optional
from control_plane.file_queue import (
    FileJobQueue,
    QueueItem,
    INTERACTIVE_PRIORITY,
    BATCH_PRIORITY,
    resolve_priority,
)

QUEUE_NAME = "jobs:queue:v1"
JOB_LOG_CHANNEL_PREFIX = "jobs:log:v1:"

_DEFAULT_QUEUE_CACHE: dict[str, FileJobQueue] = {}


def job_log_channel(job_id: str) -> str:
    return f"{JOB_LOG_CHANNEL_PREFIX}{job_id}"


def get_file_queue(workspaces_dir: str) -> FileJobQueue:
    queue_dir = os.path.join(workspaces_dir, ".queue")
    if queue_dir not in _DEFAULT_QUEUE_CACHE:
        _DEFAULT_QUEUE_CACHE[queue_dir] = FileJobQueue(queue_dir)
    return _DEFAULT_QUEUE_CACHE[queue_dir]


def enqueue_job(
    workspaces_dir: str,
    job_id: str,
    job_type: str | None = None,
    payload: dict[str, Any] | None = None,
    priority: str | None = None,
    redis_client: Any = None,
) -> str:
    q = get_file_queue(workspaces_dir)
    res = q.enqueue(job_id=job_id, job_type=job_type, payload=payload, priority=priority)
    if redis_client is not None:
        try:
            redis_client.rpush(QUEUE_NAME, json.dumps({"job_id": job_id}))
        except Exception:
            pass
    return res


def request_cancel_job(workspaces_dir: str, job_id: str, redis_client: Any = None) -> None:
    q = get_file_queue(workspaces_dir)
    q.request_cancel(job_id)
    if redis_client is not None:
        try:
            redis_client.setex(f"jobs:cancel:v1:{job_id}", 86400, "1")
        except Exception:
            pass


def is_job_cancelled(workspaces_dir: str, job_id: str, redis_client: Any = None) -> bool:
    q = get_file_queue(workspaces_dir)
    if q.is_cancel_requested(job_id):
        return True
    if redis_client is not None:
        try:
            return str(redis_client.get(f"jobs:cancel:v1:{job_id}") or "") == "1"
        except Exception:
            pass
    return False
