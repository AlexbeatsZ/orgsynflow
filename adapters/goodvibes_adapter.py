from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.temp_paths import orgsynflow_temp_dir


@dataclass(frozen=True)
class GoodVibesResult:
    available: bool
    status: str
    source: str
    data: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "status": self.status,
            "source": self.source,
            "data": self.data,
            "reason": self.reason,
        }


def find_goodvibes_executable() -> str | None:
    for name in ("goodvibes", "goodvibes.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def run_goodvibes(log_paths: list[str | Path], timeout_seconds: int = 120) -> GoodVibesResult:
    executable = find_goodvibes_executable()
    if executable is None:
        return GoodVibesResult(
            available=False,
            status="unavailable",
            source="GoodVibes CLI",
            reason="未在 PATH 中检测到 GoodVibes；热化学校正保持 Gaussian/cclib fallback。",
        )

    work_dir = orgsynflow_temp_dir("goodvibes_jobs", datetime.now().strftime("%Y%m%d_%H%M%S"))
    work_dir.mkdir(parents=True, exist_ok=True)
    command = [executable, *[str(Path(path).resolve()) for path in log_paths]]
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
        return GoodVibesResult(True, "failed", "GoodVibes CLI", reason=str(exc))

    return GoodVibesResult(
        available=True,
        status="available" if completed.returncode == 0 else "failed",
        source="GoodVibes CLI",
        data={"stdout": completed.stdout, "stderr": completed.stderr, "returncode": completed.returncode},
        reason=None if completed.returncode == 0 else (completed.stderr.strip() or completed.stdout.strip()),
    )
