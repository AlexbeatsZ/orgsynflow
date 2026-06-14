from __future__ import annotations

import csv
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.temp_paths import orgsynflow_temp_dir


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

    commands = [
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
        "melting_point": ("MP", "mp", "MeltingPoint", "Melting_Point"),
        "boiling_point": ("BP", "bp", "BoilingPoint", "Boiling_Point"),
        "logp": ("LogP", "logP", "LOGP"),
        "water_solubility": ("WS", "WaterSolubility", "Water_Solubility"),
        "vapor_pressure": ("VP", "VaporPressure", "Vapor_Pressure"),
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
