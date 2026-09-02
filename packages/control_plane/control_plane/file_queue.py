from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

INTERACTIVE_PRIORITY = "interactive"
BATCH_PRIORITY = "batch"
VALID_PRIORITIES = (INTERACTIVE_PRIORITY, BATCH_PRIORITY)

BATCH_JOB_TYPES = frozenset(
    {
        "trending_scrape",
        "trending_backtest",
        "template_performance_update",
        "template_backtest",
        "template_stable5_screening",
    }
)


def resolve_priority(job_type: str | None, priority: str | None = None) -> str:
    if priority and priority in VALID_PRIORITIES:
        return priority
    if job_type and str(job_type).lower() in BATCH_JOB_TYPES:
        return BATCH_PRIORITY
    return INTERACTIVE_PRIORITY


@dataclass
class QueueItem:
    job_id: str
    priority: str
    job_type: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    created_at: float = 0.0
    processing_path: Optional[str] = None


class FileJobQueue:
    """Zero-dependency, multi-priority file-based job queue using atomic directory operations."""

    def __init__(self, queue_dir: str):
        self.queue_dir = queue_dir
        self.interactive_dir = os.path.join(queue_dir, INTERACTIVE_PRIORITY)
        self.batch_dir = os.path.join(queue_dir, BATCH_PRIORITY)
        self.processing_dir = os.path.join(queue_dir, "processing")
        self.cancel_dir = os.path.join(queue_dir, "cancel")
        self.logs_dir = os.path.join(queue_dir, "logs")

        for d in (
            self.interactive_dir,
            self.batch_dir,
            self.processing_dir,
            self.cancel_dir,
            self.logs_dir,
        ):
            os.makedirs(d, exist_ok=True)

    def enqueue(
        self,
        job_id: str,
        job_type: str | None = None,
        payload: dict[str, Any] | None = None,
        priority: str | None = None,
    ) -> str:
        p = resolve_priority(job_type, priority)
        target_dir = self.interactive_dir if p == INTERACTIVE_PRIORITY else self.batch_dir

        now_ns = time.time_ns()
        filename = f"{now_ns}_{job_id}.json"
        tmp_path = os.path.join(self.queue_dir, f".tmp_{now_ns}_{job_id}.json")
        final_path = os.path.join(target_dir, filename)

        data = {
            "job_id": job_id,
            "job_type": job_type,
            "priority": p,
            "payload": payload or {},
            "created_at": time.time(),
        }

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, final_path)
        return final_path

    def dequeue(self, timeout_s: float = 0.5) -> Optional[QueueItem]:
        """Attempt to claim a job from interactive queue first, then batch queue."""
        deadline = time.monotonic() + max(0.0, timeout_s)

        while True:
            item = self._try_dequeue_from_dir(self.interactive_dir, INTERACTIVE_PRIORITY)
            if item is not None:
                return item

            item = self._try_dequeue_from_dir(self.batch_dir, BATCH_PRIORITY)
            if item is not None:
                return item

            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)

        return None

    def _try_dequeue_from_dir(self, source_dir: str, priority: str) -> Optional[QueueItem]:
        try:
            entries = sorted(os.listdir(source_dir))
        except FileNotFoundError:
            return None

        for filename in entries:
            if not filename.endswith(".json"):
                continue
            src_path = os.path.join(source_dir, filename)
            dst_path = os.path.join(self.processing_dir, filename)

            try:
                # Atomic claim
                os.replace(src_path, dst_path)
            except (FileNotFoundError, OSError):
                # Another worker picked it up concurrently
                continue

            # Successfully claimed
            try:
                with open(dst_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return QueueItem(
                    job_id=data.get("job_id", ""),
                    priority=priority,
                    job_type=data.get("job_type"),
                    payload=data.get("payload"),
                    created_at=data.get("created_at", 0.0),
                    processing_path=dst_path,
                )
            except Exception as e:
                logger.error(f"Failed to read claimed job file {dst_path}: {e}")
                job_id = filename.split("_", 1)[-1].replace(".json", "")
                return QueueItem(
                    job_id=job_id,
                    priority=priority,
                    processing_path=dst_path,
                )

        return None

    def mark_completed(self, item_or_path: QueueItem | str) -> None:
        path = item_or_path.processing_path if isinstance(item_or_path, QueueItem) else item_or_path
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    def mark_failed(self, item_or_path: QueueItem | str) -> None:
        self.mark_completed(item_or_path)

    def request_cancel(self, job_id: str) -> None:
        cancel_marker = os.path.join(self.cancel_dir, job_id)
        try:
            with open(cancel_marker, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        except Exception as e:
            logger.error(f"Failed to write cancel marker for job {job_id}: {e}")

    def is_cancel_requested(self, job_id: str) -> bool:
        cancel_marker = os.path.join(self.cancel_dir, job_id)
        return os.path.exists(cancel_marker)

    def clear_cancel(self, job_id: str) -> None:
        cancel_marker = os.path.join(self.cancel_dir, job_id)
        if os.path.exists(cancel_marker):
            try:
                os.remove(cancel_marker)
            except OSError:
                pass

    def get_job_log_path(self, job_id: str, run_dir: str | None = None) -> str:
        if run_dir:
            return os.path.join(run_dir, "live.log")
        return os.path.join(self.logs_dir, f"{job_id}.log")

    def recover_stale_processing_jobs(self) -> int:
        """Move uncompleted jobs from processing back to their respective priority queues on worker restart."""
        recovered = 0
        try:
            entries = os.listdir(self.processing_dir)
        except FileNotFoundError:
            return 0

        for filename in entries:
            if not filename.endswith(".json"):
                continue
            proc_path = os.path.join(self.processing_dir, filename)
            try:
                with open(proc_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                p = data.get("priority", INTERACTIVE_PRIORITY)
                dest_dir = self.interactive_dir if p == INTERACTIVE_PRIORITY else self.batch_dir
                dest_path = os.path.join(dest_dir, filename)
                os.replace(proc_path, dest_path)
                recovered += 1
            except Exception as e:
                logger.error(f"Error recovering processing job {proc_path}: {e}")
        return recovered
