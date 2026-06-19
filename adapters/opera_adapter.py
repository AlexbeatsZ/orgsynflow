from __future__ import annotations

import csv
import shutil
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.temp_paths import orgsynflow_temp_dir

WSL_OPERA = "/home/meta/.local/bin/opera"


@dataclass(frozen=True)
class OperaPrediction:
    available: bool
    status: str
    source: str
    properties: dict[str, Any] = field(default_factory=dict)
    applicability_domain: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "status": self.status,
            "source": self.source,
            "properties": self.properties,
            "applicability_domain": self.applicability_domain,
            "reason": self.reason,
        }


def find_opera_executable() -> str | None:
    for name in ("opera", "OPERA", "OPERA.exe"):
        found = shutil.which(name)
        if found:
            return found
    if _wsl_file_is_executable(WSL_OPERA):
        return f"wsl:{WSL_OPERA}"
    return None


def predict_with_opera(smiles: str, timeout_seconds: int = 120) -> OperaPrediction:
    executable = find_opera_executable()
    if executable is None:
        return OperaPrediction(
            available=False,
            status="unavailable",
            source="OPERA CLI",
            reason="未在 PATH 中检测到 OPERA；已跳过 QSAR 物性预测。",
        )

    work_dir = _default_job_dir()
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = work_dir / "input.smi"
    output_path = work_dir / "opera_output.csv"
    input_path.write_text(f"{smiles}\tquery\n", encoding="utf-8")

    if executable.startswith("wsl:"):
        return _predict_with_wsl_opera(executable.removeprefix("wsl:"), smiles, timeout_seconds)

    commands = [
        [
            executable,
            "--SMI",
            str(input_path),
            "-o",
            str(output_path),
            "-e",
            "MP",
            "BP",
            "logP",
            "WS",
            "VP",
            "-v",
            "0",
            "-c",
        ],
        [executable, str(input_path), str(output_path)],
        [executable, "-i", str(input_path), "-o", str(output_path)],
    ]
    last_error = ""
    for command in commands:
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
            last_error = str(exc)
            continue

        if completed.returncode == 0:
            csv_path = output_path if output_path.exists() else _latest_csv(work_dir)
            if csv_path:
                parsed = _parse_opera_csv(csv_path)
                return OperaPrediction(
                    available=True,
                    status="available",
                    source="OPERA CLI",
                    properties=parsed["properties"],
                    applicability_domain=parsed["applicability_domain"],
                )
        last_error = completed.stderr.strip() or completed.stdout.strip() or "OPERA 未生成可解析输出。"

    return OperaPrediction(
        available=True,
        status="failed",
        source="OPERA CLI",
        reason=last_error,
    )


def _parse_opera_csv(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"properties": {}, "applicability_domain": {}}

    row = rows[0]
    property_aliases = {
        "melting_point": ("MP_pred", "MP", "mp", "MeltingPoint", "Melting_Point"),
        "boiling_point": ("BP_pred", "BP", "bp", "BoilingPoint", "Boiling_Point"),
        "logp": ("LogP_pred", "LogP", "logP", "LOGP"),
        "water_solubility": ("LogWS_pred", "WS_pred", "WS", "WaterSolubility", "Water_Solubility"),
        "vapor_pressure": ("LogVP_pred", "VP_pred", "VP", "VaporPressure", "Vapor_Pressure"),
    }
    ad_aliases = {
        "melting_point_ad": ("MP_AD", "AD_MP"),
        "boiling_point_ad": ("BP_AD", "AD_BP"),
        "logp_ad": ("LogP_AD", "AD_LogP"),
        "water_solubility_ad": ("WS_AD", "AD_WS"),
        "vapor_pressure_ad": ("VP_AD", "AD_VP"),
    }
    return {
        "properties": {key: _first_present(row, aliases) for key, aliases in property_aliases.items()},
        "applicability_domain": {key: _first_present(row, aliases) for key, aliases in ad_aliases.items()},
    }


def _first_present(row: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        value = row.get(alias)
        if value not in (None, ""):
            return value
    return None


def _latest_csv(work_dir: Path) -> Path | None:
    candidates = sorted(work_dir.glob("*.csv"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _default_job_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return orgsynflow_temp_dir("opera_jobs", stamp)


def _predict_with_wsl_opera(executable: str, smiles: str, timeout_seconds: int) -> OperaPrediction:
    wsl_work_dir = f"/tmp/codex/orgsynflow/opera_jobs/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    script = "\n".join(
        [
            "set -u",
            f"work_dir={shlex.quote(wsl_work_dir)}",
            "rm -rf \"$work_dir\"",
            "mkdir -p \"$work_dir\"",
            "cat > \"$work_dir/input.smi\"",
            "cd \"$work_dir\"",
            f"{shlex.quote(executable)} --SMI input.smi -o opera_output.csv -e MP BP logP WS VP -v 0 -c",
        ]
    )
    try:
        completed = subprocess.run(
            ["wsl", "-e", "bash", "-lc", script],
            input=f"{smiles}\tquery\n",
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except Exception as exc:
        return OperaPrediction(
            available=True,
            status="failed",
            source="OPERA CLI via WSL",
            reason=str(exc),
        )

    if completed.returncode != 0:
        return OperaPrediction(
            available=True,
            status="failed",
            source="OPERA CLI via WSL",
            reason=(completed.stderr or completed.stdout or "OPERA WSL run failed.").strip(),
        )

    copy_dir = _default_job_dir()
    copy_dir.mkdir(parents=True, exist_ok=True)
    csv_path = copy_dir / "opera_output.csv"
    fetch = subprocess.run(
        ["wsl", "-e", "cat", f"{wsl_work_dir}/opera_output.csv"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if fetch.returncode != 0 or not fetch.stdout.strip():
        return OperaPrediction(
            available=True,
            status="failed",
            source="OPERA CLI via WSL",
            reason=(fetch.stderr or "OPERA completed but no CSV output was readable.").strip(),
        )
    csv_path.write_text(fetch.stdout, encoding="utf-8")
    parsed = _parse_opera_csv(csv_path)
    return OperaPrediction(
        available=True,
        status="available",
        source="OPERA CLI via WSL",
        properties=parsed["properties"],
        applicability_domain=parsed["applicability_domain"],
    )


def _wsl_file_is_executable(path: str) -> bool:
    wsl = shutil.which("wsl")
    if not wsl:
        return False
    try:
        completed = subprocess.run(
            [wsl, "-e", "test", "-x", path],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except Exception:
        return False
    return completed.returncode == 0
