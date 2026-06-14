from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SemiempiricalJobResult:
    available: bool
    status: str
    source: str
    work_dir: str | None = None
    stdout: str = ""
    stderr: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "status": self.status,
            "source": self.source,
            "work_dir": self.work_dir,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "data": self.data,
            "reason": self.reason,
        }


def find_xtb_executable() -> str | None:
    return _which(("xtb", "xtb.exe"))


def find_crest_executable() -> str | None:
    return _which(("crest", "crest.exe"))


def run_xtb_job(xyz_text: str, timeout_seconds: int = 300) -> SemiempiricalJobResult:
    executable = find_xtb_executable()
    if executable is None:
        return SemiempiricalJobResult(
            available=False,
            status="unavailable",
            source="xTB CLI",
            reason="未在 PATH 中检测到 xTB；无法运行半经验量化 job。",
        )
    work_dir = _default_job_dir("xtb_jobs")
    work_dir.mkdir(parents=True, exist_ok=True)
    xyz_path = work_dir / "input.xyz"
    xyz_path.write_text(xyz_text, encoding="utf-8")
    return _run([executable, str(xyz_path)], work_dir, "xTB CLI", timeout_seconds)


def run_crest_job(xyz_text: str, timeout_seconds: int = 1800) -> SemiempiricalJobResult:
    executable = find_crest_executable()
    if executable is None:
        return SemiempiricalJobResult(
            available=False,
            status="unavailable",
            source="CREST CLI",
            reason="未在 PATH 中检测到 CREST；无法运行构象搜索 job。",
        )
    work_dir = _default_job_dir("crest_jobs")
    work_dir.mkdir(parents=True, exist_ok=True)
    xyz_path = work_dir / "input.xyz"
    xyz_path.write_text(xyz_text, encoding="utf-8")
    return _run([executable, str(xyz_path)], work_dir, "CREST CLI", timeout_seconds)


def _run(command: list[str], work_dir: Path, source: str, timeout_seconds: int) -> SemiempiricalJobResult:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(work_dir),
        )
    except Exception as exc:
        return SemiempiricalJobResult(
            available=True,
            status="failed",
            source=source,
            work_dir=str(work_dir),
            reason=str(exc),
        )
    return SemiempiricalJobResult(
        available=True,
        status="available" if completed.returncode == 0 else "failed",
        source=source,
        work_dir=str(work_dir),
        stdout=completed.stdout,
        stderr=completed.stderr,
        data={"returncode": completed.returncode},
        reason=None if completed.returncode == 0 else (completed.stderr.strip() or completed.stdout.strip()),
    )


def _which(names: tuple[str, ...]) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _default_job_dir(kind: str) -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Temp" / "codex" / "orgsynflow" / kind
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return root / stamp
