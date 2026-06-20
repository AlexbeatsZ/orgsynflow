from __future__ import annotations

import os

from core import job_queue
from core.crest_parser import parse_crest_log_progress
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


def test_crest_progress_parser_extracts_recent_optimization_energies() -> None:
    progress = parse_crest_log_progress(
        "Etot= -5.10\n"
        "Estimated runtime for one MTD (5.0 ps) on a single thread: 1 min 17 sec\n"
        "Estimated runtime for a batch of 14 MTDs on 1 threads: 17 min 57 sec\n"
        "Etot= -5.20\n"
    )

    assert progress["summary"] == "正在进行构象搜索与采样，当前已提取 2 步能量计算。"
    assert progress["optimization_steps"] == [
        {"step": 1, "energy_hartree": -5.1, "max_force": None},
        {"step": 2, "energy_hartree": -5.2, "max_force": None},
    ]
    assert progress["estimated_runtime"] == {
        "one_mtd_seconds": 77,
        "batch_seconds": 1077,
        "batch_mtd_count": 14,
        "threads": 1,
    }
