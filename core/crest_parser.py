import re
from typing import Any

_CREST_ETOT_RE = re.compile(r"Etot=\s*(-?[\d.]+)")


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

    return {"summary": summary, "optimization_steps": optimization_steps[-100:]}
