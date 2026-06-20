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


def _duration_seconds(minutes: str | None, seconds: str) -> int:
    return round(int(minutes or 0) * 60 + float(seconds))


def parse_crest_log_progress(text: str) -> dict[str, Any]:
    optimization_steps = []

    for match in _CREST_ETOT_RE.finditer(text):
        try:
            energy = float(match.group(1))
            optimization_steps.append({
                "step": len(optimization_steps) + 1,
                "energy_hartree": energy,
                "max_force": None
            })
        except ValueError:
            continue

    summary = "等待 CREST 写入日志。"
    if optimization_steps:
        summary = f"正在进行构象搜索与采样，当前已提取 {len(optimization_steps)} 步能量计算。"

    progress: dict[str, Any] = {
        "summary": summary,
        "optimization_steps": optimization_steps[-100:],
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
