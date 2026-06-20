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


def test_crest_progress_parser_reports_mtd_sampling_without_gaussian_steps() -> None:
    progress = parse_crest_log_progress(
        "Etot= -5.10\n"
        "Σ(t(MTD)) / ps : 70.0 (14 MTDs)\n"
        "Estimated runtime for one MTD (5.0 ps) on a single thread: 1 min 17 sec\n"
        "Estimated runtime for a batch of 14 MTDs on 1 threads: 17 min 57 sec\n"
        "*MTD   1 completed successfully ... 0 min, 54.899 sec\n"
        "::::::::::::: starting MTD    2 :::::::::::::\n"
        "Etot= -5.20\n"
    )

    assert progress["summary"] == "正在进行 CREST 构象采样：MTD 2/14（已完成 1 个）。"
    assert "optimization_steps" not in progress
    assert progress["crest_sampling"] == {
        "current_mtd": 2,
        "completed_mtd": 1,
        "total_mtd": 14,
        "energy_evaluations": 2,
    }
    assert progress["estimated_runtime"] == {
        "one_mtd_seconds": 77,
        "batch_seconds": 1077,
        "batch_mtd_count": 14,
        "threads": 1,
    }


def test_crest_progress_parser_reports_normal_completion() -> None:
    progress = parse_crest_log_progress("CREST runtime (total) 0 min, 1.857 sec\nCREST terminated normally.\n")

    assert progress["summary"] == "CREST 构象搜索已正常完成。"


def test_crest_snapshot_parses_cli_lifecycle_and_optimization_energy(tmp_path) -> None:
    work_dir = tmp_path / "crest-job"
    work_dir.mkdir()
    (work_dir / "crestopt.log").write_text("Etot= -5.20\n", encoding="utf-8")
    (work_dir / "crest_cli.log").write_text("CREST terminated normally.\n", encoding="utf-8")

    snapshot = job_queue._read_crest_log_snapshot(str(work_dir))

    assert snapshot["log_progress"]["summary"] == "CREST 构象搜索已正常完成。"
    assert snapshot["log_progress"]["crest_sampling"]["energy_evaluations"] == 1
