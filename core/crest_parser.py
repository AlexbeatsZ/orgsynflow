import re
from typing import Any

_CREST_ETOT_RE = re.compile(r"Etot=\s*(-?[\d.]+)")
_DURATION_RE = r"(?:(\d+)\s*min\s*)?(\d+(?:\.\d+)?)\s*sec"
_ONE_MTD_RUNTIME_RE = re.compile(
    rf"Estimated runtime for one MTD .*?:\s*{_DURATION_RE}",
)
_BATCH_RUNTIME_RE = re.compile(
    rf"Estimated runtime for a batch of (\d+) MTDs on (\d+) threads?:\s*{_DURATION_RE}",
)
_TOTAL_MTD_RE = re.compile(r"Σ\(t\(MTD\)\).*?\((\d+)\s+MTDs?\)")
_STARTED_MTD_RE = re.compile(r"starting MTD\s+(\d+)", re.IGNORECASE)
_COMPLETED_MTD_RE = re.compile(r"\*MTD\s+(\d+)\s+completed successfully", re.IGNORECASE)


def _duration_seconds(minutes: str | None, seconds: str) -> int:
    return round(int(minutes or 0) * 60 + float(seconds))


def parse_crest_log_progress(text: str) -> dict[str, Any]:
    energy_evaluations = sum(1 for _ in _CREST_ETOT_RE.finditer(text))
    total_matches = list(_TOTAL_MTD_RE.finditer(text))
    started_matches = list(_STARTED_MTD_RE.finditer(text))
    completed_matches = list(_COMPLETED_MTD_RE.finditer(text))
    total_mtd = int(total_matches[-1].group(1)) if total_matches else None
    current_mtd = int(started_matches[-1].group(1)) if started_matches else None
    completed_mtd = max((int(match.group(1)) for match in completed_matches), default=0)

    summary = "等待 CREST 写入日志。"
    if "CREST terminated normally" in text:
        summary = "CREST 构象搜索已正常完成。"
    elif current_mtd is not None:
        total_label = str(total_mtd) if total_mtd is not None else "?"
        summary = f"正在进行 CREST 构象采样：MTD {current_mtd}/{total_label}（已完成 {completed_mtd} 个）。"
    elif "Initial Geometry Optimization" in text:
        summary = "正在进行 CREST 初始几何优化。"

    progress: dict[str, Any] = {
        "summary": summary,
        "crest_sampling": {
            "current_mtd": current_mtd,
            "completed_mtd": completed_mtd,
            "total_mtd": total_mtd,
            "energy_evaluations": energy_evaluations,
        },
    }
    one_mtd_match = _ONE_MTD_RUNTIME_RE.search(text)
    batch_match = _BATCH_RUNTIME_RE.search(text)
    if one_mtd_match or batch_match:
        estimate: dict[str, int] = {}
        if one_mtd_match:
            estimate["one_mtd_seconds"] = _duration_seconds(*one_mtd_match.groups())
        if batch_match:
            batch_count, threads, minutes, seconds = batch_match.groups()
            estimate.update(
                batch_seconds=_duration_seconds(minutes, seconds),
                batch_mtd_count=int(batch_count),
                threads=int(threads),
            )
        progress["estimated_runtime"] = estimate

    return progress
