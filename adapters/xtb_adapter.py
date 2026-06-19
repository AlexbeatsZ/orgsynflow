from __future__ import annotations

import shutil
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.temp_paths import orgsynflow_temp_dir

WSL_CHEM_BIN = "/home/meta/.local/opt/miniforge3/envs/orgsynflow-chem/bin"


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
    return _which(("xtb", "xtb.exe")) or _find_wsl_executable("xtb")


def find_crest_executable() -> str | None:
    return _which(("crest", "crest.exe")) or _find_wsl_executable("crest")


def run_xtb_job(xyz_text: str, timeout_seconds: int = 300) -> SemiempiricalJobResult:
    executable = find_xtb_executable()
    if executable is None:
        return SemiempiricalJobResult(
            available=False,
            status="unavailable",
            source="xTB CLI",
            reason="未在 PATH 中检测到 xTB；无法运行半经验量化 job。",
        )
    if executable.startswith("wsl:"):
        return _run_wsl(executable.removeprefix("wsl:"), xyz_text, "xtb_jobs", "xTB CLI via WSL", timeout_seconds)
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
    if executable.startswith("wsl:"):
        return _run_wsl(executable.removeprefix("wsl:"), xyz_text, "crest_jobs", "CREST CLI via WSL", timeout_seconds)
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
            encoding="utf-8",
            errors="replace",
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
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        data={"returncode": completed.returncode, **_parse_cli_output(completed.stdout or "")},
        reason=None if completed.returncode == 0 else ((completed.stderr or "").strip() or (completed.stdout or "").strip()),
    )


def _run_wsl(
    executable: str,
    xyz_text: str,
    kind: str,
    source: str,
    timeout_seconds: int,
) -> SemiempiricalJobResult:
    wsl_work_dir = f"/tmp/codex/orgsynflow/{kind}/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    script = "\n".join(
        [
            "set -u",
            f"work_dir={shlex.quote(wsl_work_dir)}",
            'mkdir -p "$work_dir"',
            'cat > "$work_dir/input.xyz"',
            'cd "$work_dir"',
            f"{shlex.quote(executable)} input.xyz",
        ]
    )
    try:
        completed = subprocess.run(
            ["wsl", "-e", "bash", "-lc", script],
            input=xyz_text,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except Exception as exc:
        return SemiempiricalJobResult(
            available=True,
            status="failed",
            source=source,
            work_dir=wsl_work_dir,
            reason=str(exc),
        )
    return SemiempiricalJobResult(
        available=True,
        status="available" if completed.returncode == 0 else "failed",
        source=source,
        work_dir=wsl_work_dir,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        data={"returncode": completed.returncode, **_parse_cli_output(completed.stdout or "")},
        reason=None if completed.returncode == 0 else ((completed.stderr or "").strip() or (completed.stdout or "").strip()),
    )


def _which(names: tuple[str, ...]) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _find_wsl_executable(name: str) -> str | None:
    wsl = shutil.which("wsl")
    if not wsl:
        return None
    candidate = f"{WSL_CHEM_BIN}/{name}"
    try:
        completed = subprocess.run(
            [wsl, "-e", "test", "-x", candidate],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except Exception:
        return None
    return f"wsl:{candidate}" if completed.returncode == 0 else None


def _default_job_dir(kind: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return orgsynflow_temp_dir(kind, stamp)


def _parse_cli_output(stdout: str) -> dict[str, object]:
    data: dict[str, object] = {}
    for line in stdout.splitlines():
        if "TOTAL ENERGY" in line:
            parts = line.split()
            for part in parts:
                try:
                    data["total_energy_hartree"] = float(part)
                    break
                except ValueError:
                    continue
    return data
