from __future__ import annotations

import threading
import uuid
from collections import OrderedDict, deque
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
            "engine": "Gaussian",
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
        self._cancel_events: dict[str, threading.Event] = {}
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
                job.error = "Gaussian 作业已取消，尚未启动进程。"
                try:
                    self._queue.remove(job_id)
                except ValueError:
                    pass
            elif job.status == "running":
                self._cancel_events.setdefault(job_id, threading.Event()).set()
                job.status = "cancelled"
                job.finished_at = _now()
                job.error = "已请求强制结束 Gaussian 进程。"
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
                cancel_event = self._cancel_events.setdefault(job.job_id, threading.Event())

            try:
                result = run_gaussian_job(job.gjf_text, work_dir=job.work_dir, cancel_event=cancel_event)
                with self._lock:
                    if cancel_event.is_set():
                        job.result = result.as_dict()
                        job.status = "cancelled"
                        job.finished_at = job.finished_at or _now()
                        job.error = "Gaussian 进程已被强制结束。"
                        continue
                    job.result = result.as_dict()
                    job.status = "succeeded" if result.success else "failed"
                    job.finished_at = _now()
                    job.error = None if result.success else result.message
            except Exception as exc:
                with self._lock:
                    if self._cancel_events.setdefault(job.job_id, threading.Event()).is_set():
                        job.status = "cancelled"
                        job.error = "Gaussian 进程已被强制结束。"
                        job.finished_at = job.finished_at or _now()
                        continue
                    job.status = "failed"
                    job.error = str(exc)
                    job.finished_at = _now()
            finally:
                with self._lock:
                    self._cancel_events.pop(job.job_id, None)


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
    stat = log_path.stat()
    cache_key = str(log_path.resolve())
    cached = _log_snapshot_cache.get(cache_key)
    if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        _log_snapshot_cache.move_to_end(cache_key)
        return cached[2]
    with log_path.open("rb") as stream:
        if stat.st_size > _LOG_SNAPSHOT_PARSE_BYTES:
            stream.seek(-_LOG_SNAPSHOT_PARSE_BYTES, 2)
        text = stream.read().decode("utf-8", errors="ignore")
    snapshot = {
        "log_path": str(log_path),
        "log_tail": text[-12000:],
        "log_progress": parse_gaussian_log_progress(text),
    }
    _log_snapshot_cache[cache_key] = (stat.st_mtime_ns, stat.st_size, snapshot)
    _log_snapshot_cache.move_to_end(cache_key)
    while len(_log_snapshot_cache) > _LOG_SNAPSHOT_CACHE_LIMIT:
        _log_snapshot_cache.popitem(last=False)
    return snapshot


gaussian_job_queue = GaussianJobQueue()


class CrestJob:
    def __init__(self, xyz_text: str, timeout_seconds: int = 1800):
        self.job_id = str(uuid.uuid4())[:8]
        self.xyz_text = xyz_text
        self.timeout_seconds = timeout_seconds
        self.status: str = "queued"
        self.created_at: str = datetime.now(timezone.utc).isoformat()
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.result: dict[str, Any] | None = None
        self.error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "engine": "CREST",
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
            "work_dir": self.result.get("work_dir") if self.result else None,
        }


class CrestJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, CrestJob] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._compute_slot = threading.Semaphore(1)

    def submit(self, xyz_text: str, timeout_seconds: int = 1800) -> dict[str, Any]:
        job = CrestJob(xyz_text, timeout_seconds=timeout_seconds)
        with self._lock:
            self._jobs[job.job_id] = job
        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        thread.start()
        return job.as_dict()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return job.as_dict()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [job.as_dict() for job in sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)]

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status == "queued":
                job.status = "cancelled"
                job.finished_at = datetime.now(timezone.utc).isoformat()
                job.error = "用户已取消。"
            elif job.status == "running":
                cancel_event = self._cancel_events.get(job_id)
                if cancel_event:
                    cancel_event.set()
                job.status = "cancelled"
                job.finished_at = datetime.now(timezone.utc).isoformat()
                job.error = "已请求强制终止 CREST 进程。"
            return job.as_dict()

    def _run(self, job: CrestJob) -> None:
        with self._compute_slot:
            self._run_in_slot(job)

    def _run_in_slot(self, job: CrestJob) -> None:
        cancel_event = threading.Event()
        with self._lock:
            if job.status != "queued":
                return
            job.status = "running"
            job.started_at = datetime.now(timezone.utc).isoformat()
            self._cancel_events[job.job_id] = cancel_event

        try:
            from adapters.xtb_adapter import run_crest_job  # deferred import to avoid circular dependency
            result = run_crest_job(job.xyz_text, timeout_seconds=job.timeout_seconds, cancel_event=cancel_event)
        except Exception as exc:
            with self._lock:
                job.finished_at = datetime.now(timezone.utc).isoformat()
                if cancel_event.is_set() or job.status == "cancelled":
                    job.status = "cancelled"
                else:
                    job.status = "failed"
                    job.error = str(exc)
                self._cancel_events.pop(job.job_id, None)
            return

        with self._lock:
            job.finished_at = datetime.now(timezone.utc).isoformat()
            job.result = result.as_dict()
            if cancel_event.is_set() or job.status == "cancelled" or result.status == "cancelled":
                job.status = "cancelled"
                job.error = result.reason or job.error or "用户已强制终止 CREST 进程。"
            elif result.status == "failed" or result.status == "unavailable":
                job.status = "failed"
                job.error = result.reason or "CREST 计算失败。"
            else:
                job.status = "succeeded"
            self._cancel_events.pop(job.job_id, None)


crest_manager = CrestJobManager()


_LOG_SNAPSHOT_CACHE_LIMIT = 128
_LOG_SNAPSHOT_PARSE_BYTES = 2_000_000
_log_snapshot_cache: OrderedDict[str, tuple[int, int, dict[str, Any]]] = OrderedDict()

