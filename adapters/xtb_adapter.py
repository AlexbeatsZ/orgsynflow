from __future__ import annotations

import os
import shutil
import shlex
import signal
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


def run_xtb_job(xyz_text: str, timeout_seconds: int = 300, cancel_event: Any = None) -> SemiempiricalJobResult:
    executable = find_xtb_executable()
    if executable is None:
        return SemiempiricalJobResult(
            available=False,
            status="unavailable",
            source="xTB CLI",
            reason="未在 PATH 中检测到 xTB；无法运行半经验量化 job。",
        )
    if executable.startswith("wsl:"):
        return _run_wsl(executable.removeprefix("wsl:"), xyz_text, "xtb_jobs", "xTB CLI via WSL", timeout_seconds, cancel_event=cancel_event)
    work_dir = _default_job_dir("xtb_jobs")
    work_dir.mkdir(parents=True, exist_ok=True)
    xyz_path = work_dir / "input.xyz"
    xyz_path.write_text(xyz_text, encoding="utf-8")
    return _run([executable, str(xyz_path)], work_dir, "xTB CLI", timeout_seconds, cancel_event=cancel_event)


def run_crest_job(xyz_text: str, timeout_seconds: int = 1800, cancel_event: Any = None) -> SemiempiricalJobResult:
    executable = find_crest_executable()
    if executable is None:
        return SemiempiricalJobResult(
            available=False,
            status="unavailable",
            source="CREST CLI",
            reason="未在 PATH 中检测到 CREST；无法运行构象搜索 job。",
        )
    if executable.startswith("wsl:"):
        return _run_wsl(executable.removeprefix("wsl:"), xyz_text, "crest_jobs", "CREST CLI via WSL", timeout_seconds, cancel_event=cancel_event)
    work_dir = _default_job_dir("crest_jobs")
    work_dir.mkdir(parents=True, exist_ok=True)
    xyz_path = work_dir / "input.xyz"
    xyz_path.write_text(xyz_text, encoding="utf-8")
    return _run([executable, str(xyz_path), "--gfn2", "--chrg", "0"], work_dir, "CREST CLI", timeout_seconds, cancel_event=cancel_event)


def _run(
    command: list[str],
    work_dir: Path,
    source: str,
    timeout_seconds: int,
    cancel_event: Any = None,
) -> SemiempiricalJobResult:
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(work_dir),
        )
        try:
            stdout_data, stderr_data = _wait_with_cancel(process, timeout_seconds, cancel_event)
        except _CancelledError:
            _terminate_process(process)
            return SemiempiricalJobResult(
                available=True,
                status="cancelled",
                source=source,
                work_dir=str(work_dir),
                reason="用户已强制终止 CREST 进程。",
            )
        except subprocess.TimeoutExpired:
            _terminate_process(process)
            return SemiempiricalJobResult(
                available=True,
                status="failed",
                source=source,
                work_dir=str(work_dir),
                reason=f"进程超时（{timeout_seconds}秒），已强制终止。",
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
        status="available" if process.returncode == 0 else "failed",
        source=source,
        work_dir=str(work_dir),
        stdout=stdout_data or "",
        stderr=stderr_data or "",
        data={"returncode": process.returncode, **_parse_cli_output(stdout_data or "")},
        reason=None if process.returncode == 0 else ((stderr_data or "").strip() or (stdout_data or "").strip()),
    )


def _run_wsl(
    executable: str,
    xyz_text: str,
    kind: str,
    source: str,
    timeout_seconds: int,
    cancel_event: Any = None,
) -> SemiempiricalJobResult:
    wsl_work_dir = f"/tmp/codex/orgsynflow/{kind}/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    cmd_args = shlex.quote(executable)
    if kind == "crest_jobs":
        cmd_args += " input.xyz --gfn2 --chrg 0"
    else:
        cmd_args += " input.xyz"

    script = (
        f"work_dir={shlex.quote(wsl_work_dir)}\n"
        'mkdir -p "$work_dir"\n'
        'cat > "$work_dir/input.xyz"\n'
        f"{cmd_args}\n"
    )

    try:
        process = subprocess.Popen(
            ["wsl", "-e", "bash", "-c", script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            stdout_data, stderr_data = process.communicate(input=xyz_text, timeout=timeout_seconds)
        except _CancelledError:
            _terminate_process(process)
            return SemiempiricalJobResult(
                available=True,
                status="cancelled",
                source=source,
                work_dir=wsl_work_dir,
                reason="用户已强制终止 CREST 进程。",
            )
        except subprocess.TimeoutExpired:
            _terminate_process(process)
            return SemiempiricalJobResult(
                available=True,
                status="failed",
                source=source,
                work_dir=wsl_work_dir,
                reason=f"进程超时（{timeout_seconds}秒），已强制终止。",
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
        status="available" if process.returncode == 0 else "failed",
        source=source,
        work_dir=wsl_work_dir,
        stdout=stdout_data or "",
        stderr=stderr_data or "",
        data={"returncode": process.returncode, **_parse_cli_output(stdout_data or "")},
        reason=None if process.returncode == 0 else ((stderr_data or "").strip() or (stdout_data or "").strip()),
    )


class _CancelledError(Exception):
    pass


def _wait_with_cancel(
    process: subprocess.Popen[str],
    timeout_seconds: int,
    cancel_event: Any,
) -> tuple[str, str]:
    cancelled = threading_imported = False
    try:
        import threading
        threading_imported = True
    except ImportError:
        pass
    if cancel_event is not None and threading_imported and isinstance(cancel_event, threading.Event):
        deadline = datetime.now().timestamp() + timeout_seconds
        remaining = timeout_seconds
        while remaining > 0:
            if cancel_event.is_set():
                cancelled = True
                raise _CancelledError()
            poll_timeout = min(remaining, 1.0)
            try:
                stdout_data, stderr_data = process.communicate(timeout=poll_timeout)
                return stdout_data, stderr_data
            except subprocess.TimeoutExpired:
                remaining = deadline - datetime.now().timestamp()
                continue
        try:
            process.kill()
        except Exception:
            pass
        stdout_data, stderr_data = process.communicate()
        return stdout_data, stderr_data
    try:
        stdout_data, stderr_data = process.communicate(timeout=timeout_seconds)
        return stdout_data, stderr_data
    except subprocess.TimeoutExpired:
        raise


def _terminate_process(process: subprocess.Popen) -> None:
    try:
        process.terminate()
    except Exception:
        pass
    try:
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=5)
        except Exception:
            pass


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
