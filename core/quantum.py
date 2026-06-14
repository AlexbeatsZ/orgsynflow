from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.gaussian import GaussianResult, parse_gaussian_log
from core.temp_paths import orgsynflow_temp_dir


@dataclass(frozen=True)
class QuantumParseResult:
    method: str
    gaussian_result: GaussianResult
    cclib_data: dict[str, Any] | None
    warnings: list[str]

    def as_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "gaussian_result": self.gaussian_result.as_dict(),
            "cclib_data": self.cclib_data,
            "warnings": self.warnings,
        }


def parse_quantum_log(text: str) -> QuantumParseResult:
    gaussian = parse_gaussian_log(text)
    warnings = list(gaussian.warnings)
    try:
        import cclib
    except Exception:
        warnings.append("未安装 cclib；已使用内置 Gaussian parser fallback。")
        return QuantumParseResult("gaussian_fallback", gaussian, None, warnings)

    temp_path = _write_temp_log(text)
    try:
        data = cclib.io.ccread(str(temp_path))
    except Exception as exc:
        warnings.append(f"cclib 解析失败；已使用内置 Gaussian parser fallback：{exc}")
        return QuantumParseResult("gaussian_fallback", gaussian, None, warnings)

    if data is None:
        warnings.append("cclib 未识别该输出；已使用内置 Gaussian parser fallback。")
        return QuantumParseResult("gaussian_fallback", gaussian, None, warnings)

    return QuantumParseResult(
        method="cclib+gaussian_fallback",
        gaussian_result=gaussian,
        cclib_data={
            "charge": getattr(data, "charge", None),
            "mult": getattr(data, "mult", None),
            "natom": getattr(data, "natom", None),
            "metadata": getattr(data, "metadata", None),
        },
        warnings=warnings,
    )


def _write_temp_log(text: str) -> Path:
    root = orgsynflow_temp_dir("quantum_parse", "")
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = root / f"parse_{stamp}.log"
    path.write_text(text, encoding="utf-8")
    return path
