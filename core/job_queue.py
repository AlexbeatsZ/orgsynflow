from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.gaussian import parse_gaussian_log_progress
from core.gaussian_runner import run_gaussian_job
from core.temp_paths import orgsynflow_temp_dir


@dataclass
class GaussianJob:
    job_id: str
    gjf_text: str
    workspace_id: str | None = None
    cell_id: str | None = None
    object_id: str | None = None
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    work_dir: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        log_snapshot = _read_log_snapshot(self.work_dir)
        return {
            "job_id": self.job_id,
            "workspace_id": self.workspace_id,
            "cell_id": self.cell_id,
            "object_id": self.object_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "work_dir": self.work_dir,
            "result": self.result,
            "error": self.error,
            **log_snapshot,
        }


class GaussianJobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, GaussianJob] = {}
        self._queue: deque[str] = deque()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def submit(
        self,
        gjf_text: str,
        workspace_id: str | None = None,
        cell_id: str | None = None,
        object_id: str | None = None,
    ) -> dict[str, Any]:
        job = GaussianJob(
            job_id=f"gj-{uuid.uuid4().hex[:10]}",
            gjf_text=gjf_text,
            workspace_id=workspace_id,
            cell_id=cell_id,
            object_id=object_id,
        )
        with self._lock:
            self._jobs[job.job_id] = job
            self._queue.append(job.job_id)
            self._ensure_worker_locked()
        return job.as_dict()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [job.as_dict() for job in sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.as_dict() if job else None

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status == "queued":
                job.status = "cancelled"
                job.finished_at = _now()
                try:
                    self._queue.remove(job_id)
                except ValueError:
                    pass
            elif job.status == "running":
                job.error = "Running Gaussian jobs cannot be cancelled in this first queue implementation."
            return job.as_dict()

    def _ensure_worker_locked(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._run_loop, name="orgsynflow-gaussian-queue", daemon=True)
        self._worker.start()

    def _run_loop(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    return
                job_id = self._queue.popleft()
                job = self._jobs[job_id]
                if job.status != "queued":
                    continue
                job.status = "running"
                job.started_at = _now()
                job.work_dir = str(orgsynflow_temp_dir("gaussian_jobs", job.job_id))

            try:
                result = run_gaussian_job(job.gjf_text, work_dir=job.work_dir)
                with self._lock:
                    job.result = result.as_dict()
                    job.status = "succeeded" if result.success else "failed"
                    job.finished_at = _now()
                    job.error = None if result.success else result.message
            except Exception as exc:
                with self._lock:
                    job.status = "failed"
                    job.error = str(exc)
                    job.finished_at = _now()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_log_snapshot(work_dir: str | None) -> dict[str, Any]:
    if not work_dir:
        return {}
    directory = Path(work_dir)
    if not directory.exists():
        return {}
    candidates = sorted(
        [*directory.glob("*.log"), *directory.glob("*.out")],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return {}
    log_path = candidates[0]
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    tail = text[-12000:]
    return {
        "log_path": str(log_path),
        "log_tail": tail,
        "log_progress": parse_gaussian_log_progress(text),
    }


gaussian_job_queue = GaussianJobQueue()
