from __future__ import annotations

import time
from types import SimpleNamespace

from core.job_queue import GaussianJobQueue


class FakeRunResult:
    success = False
    message = "cancelled"

    def as_dict(self) -> dict[str, object]:
        return {"success": self.success, "message": self.message}


def test_running_gaussian_job_can_be_cancelled(monkeypatch, tmp_path) -> None:
    queue = GaussianJobQueue()

    def fake_run_gaussian_job(gjf_text, work_dir, cancel_event=None):
        deadline = time.time() + 2
        while time.time() < deadline:
            if cancel_event and cancel_event.is_set():
                return FakeRunResult()
            time.sleep(0.01)
        return SimpleNamespace(success=True, message="done", as_dict=lambda: {"success": True})

    monkeypatch.setattr("core.job_queue.run_gaussian_job", fake_run_gaussian_job)
    monkeypatch.setattr("core.job_queue.orgsynflow_temp_dir", lambda *parts: tmp_path.joinpath(*parts))

    job = queue.submit("%chk=x.chk\n# sp\n\nx\n\n0 1\n")
    job_id = job["job_id"]
    deadline = time.time() + 2
    while time.time() < deadline and queue.get(job_id)["status"] != "running":
        time.sleep(0.01)

    cancelled = queue.cancel(job_id)

    assert cancelled is not None
    assert cancelled["status"] == "cancelled"

    deadline = time.time() + 2
    while time.time() < deadline:
        current = queue.get(job_id)
        if current["result"]:
            break
        time.sleep(0.01)

    assert queue.get(job_id)["status"] == "cancelled"
    assert queue.get(job_id)["error"] == "Gaussian 进程已被强制结束。"
