from __future__ import annotations

import os

from core import job_queue
from core.temp_paths import orgsynflow_temp_root


def test_unchanged_gaussian_log_is_parsed_once(monkeypatch, tmp_path) -> None:
    work_dir = tmp_path / "job"
    work_dir.mkdir()
    (work_dir / "job.log").write_text("SCF Done: E(RHF) = -1.0\n", encoding="utf-8")
    calls = 0

    def fake_parse(text: str) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"summary": text.strip()}

    monkeypatch.setattr(job_queue, "parse_gaussian_log_progress", fake_parse)

    job_queue._read_log_snapshot(str(work_dir))
    job_queue._read_log_snapshot(str(work_dir))

    assert calls == 1


def test_windows_temp_root_uses_agents_directory() -> None:
    if os.name == "nt":
        assert orgsynflow_temp_root().parts[-2:] == (".agents", "orgsynflow")
