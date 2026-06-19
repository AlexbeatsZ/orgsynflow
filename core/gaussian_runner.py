from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path

from core.temp_paths import orgsynflow_temp_dir
from core.gaussian import GaussianResult, parse_gaussian_log


@dataclass(frozen=True)
class GaussianRunResult:
    success: bool
    executable: str | None
    input_path: str
    log_path: str | None
    stdout: str
    stderr: str
    message: str
    parsed_result: GaussianResult | None

    def as_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "executable": self.executable,
            "input_path": self.input_path,
            "log_path": self.log_path,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "message": self.message,
            "parsed_result": self.parsed_result.as_dict() if self.parsed_result else None,
        }


def find_gaussian_executable() -> str | None:
    for name in ("g16.exe", "g16", "g09.exe", "g09", "gaussian.exe", "gaussian"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in _gaussian_executable_candidates():
        if candidate.is_file():
            return str(candidate)
    return None


def _gaussian_executable_candidates() -> list[Path]:
    candidates: list[Path] = []
    gauss_exedir = os.environ.get("GAUSS_EXEDIR")
    if gauss_exedir:
        root = Path(_windows_path_to_wsl(gauss_exedir))
        candidates.extend(root / name for name in ("g16.exe", "g16", "g09.exe", "g09"))

    wsl_user_roots = Path("/mnt/c/Users")
    if wsl_user_roots.exists():
        candidates.extend(wsl_user_roots.glob("*/AppData/Local/Programs/g16w/g16.exe"))
        candidates.extend(wsl_user_roots.glob("*/AppData/Local/Programs/Gaussian*/g16.exe"))

    for root in (Path("/mnt/c/Program Files"), Path("/mnt/c/Program Files (x86)")):
        if root.exists():
            candidates.extend(root.glob("Gaussian*/**/g16.exe"))
            candidates.extend(root.glob("g16*/g16.exe"))

    return candidates


def _windows_path_to_wsl(path: str) -> str:
    if len(path) >= 3 and path[1:3] == ":\\":
        drive = path[0].lower()
        rest = path[3:].replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    return path


def run_gaussian_job(
    gjf_text: str,
    work_dir: str | Path | None = None,
    executable: str | None = None,
    timeout_seconds: int = 3600,
) -> GaussianRunResult:
    exe = executable or find_gaussian_executable()
    job_dir = Path(work_dir) if work_dir else _default_job_dir()
    job_dir.mkdir(parents=True, exist_ok=True)
    input_path = job_dir / "job.gjf"
    input_path.write_text(gjf_text, encoding="utf-8")

    if exe is None:
        return GaussianRunResult(
            success=False,
            executable=None,
            input_path=str(input_path),
            log_path=None,
            stdout="",
            stderr="",
            message="未检测到 Gaussian 可执行文件。请确认 g16/g09 已加入 PATH。",
            parsed_result=None,
        )

    try:
        completed = subprocess.run(
            [exe, input_path.name],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(job_dir),
        )
    except subprocess.TimeoutExpired as exc:
        return GaussianRunResult(
            success=False,
            executable=exe,
            input_path=str(input_path),
            log_path=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            message=f"Gaussian 运行超时：{timeout_seconds} 秒。",
            parsed_result=None,
        )
    except Exception as exc:
        return GaussianRunResult(
            success=False,
            executable=exe,
            input_path=str(input_path),
            log_path=None,
            stdout="",
            stderr=str(exc),
            message=f"Gaussian 调用失败：{exc}",
            parsed_result=None,
        )

    log_path = _find_log(job_dir)
    parsed = None
    if log_path and log_path.exists():
        parsed = parse_gaussian_log(log_path.read_text(encoding="utf-8", errors="ignore"))

    success = completed.returncode == 0 and parsed is not None and parsed.normal_termination
    return GaussianRunResult(
        success=success,
        executable=exe,
        input_path=str(input_path),
        log_path=str(log_path) if log_path else None,
        stdout=completed.stdout,
        stderr=completed.stderr,
        message="Gaussian 计算完成。" if success else "Gaussian 已返回，但未确认正常结束；请查看 stdout/stderr/log。",
        parsed_result=parsed,
    )


def _default_job_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return orgsynflow_temp_dir("gaussian_jobs", stamp)


def _find_log(job_dir: Path) -> Path | None:
    candidates = sorted(job_dir.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    out_candidates = sorted(job_dir.glob("*.out"), key=lambda item: item.stat().st_mtime, reverse=True)
    return out_candidates[0] if out_candidates else None
