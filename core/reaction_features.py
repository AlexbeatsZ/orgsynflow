from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReactionFeatures:
    reaction_smiles: str
    method: str
    status: str
    features: dict[str, Any]
    applicability_domain: str
    unavailable: list[str] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "reaction_smiles": self.reaction_smiles,
            "method": self.method,
            "status": self.status,
            "features": self.features,
            "applicability_domain": self.applicability_domain,
            "unavailable": self.unavailable,
            "note": self.note,
        }


def featurize_reaction(reaction_smiles: str) -> ReactionFeatures:
    try:
        from drfp import DrfpEncoder
    except Exception:
        wsl_features = _featurize_reaction_via_wsl(reaction_smiles)
        if wsl_features is not None:
            return wsl_features
        return _hashed_fallback(
            reaction_smiles,
            "未知；本地和 WSL 均无法调用 DRFP，仅可作为稳定测试特征。",
            ["drfp"],
            "DRFP 不可用；当前输出不是训练模型特征，不应用于真实产率预测。",
        )

    try:
        vector = DrfpEncoder.encode([reaction_smiles], n_folded_length=256)[0]
    except Exception as exc:
        return _hashed_fallback(
            reaction_smiles,
            "未知；DRFP 已安装但编码失败，仅可作为稳定测试特征。",
            ["drfp_runtime"],
            f"DRFP 编码失败：{exc}；当前输出不是训练模型特征，不应用于真实产率预测。",
        )
    return ReactionFeatures(
        reaction_smiles=reaction_smiles,
        method="drfp",
        status="available",
        features={f"drfp_{index}": int(value) for index, value in enumerate(vector)},
        applicability_domain="取决于后续训练数据；DRFP 只提供反应指纹，不单独构成产率模型。",
        note="DRFP 特征已生成；需要配套训练模型才能输出 ML 产率。",
    )


def _featurize_reaction_via_wsl(reaction_smiles: str) -> ReactionFeatures | None:
    wsl = shutil.which("wsl")
    if not wsl:
        return None
    python_exe = "/home/meta/.local/opt/miniforge3/envs/orgsynflow-chem/bin/python"
    script = """
import json
import sys
from drfp import DrfpEncoder
rxn = sys.argv[1]
vector = DrfpEncoder.encode([rxn], n_folded_length=256)[0]
print(json.dumps({"features": {f"drfp_{i}": int(v) for i, v in enumerate(vector)}}))
"""
    try:
        completed = subprocess.run(
            [wsl, "-e", python_exe, "-c", script, reaction_smiles],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        features = payload.get("features")
        if isinstance(features, dict):
            return ReactionFeatures(
                reaction_smiles=reaction_smiles,
                method="drfp",
                status="available",
                features=features,
                applicability_domain="取决于后续训练数据；DRFP 只提供反应指纹，不单独构成产率模型。",
                note="已通过 WSL chem 环境生成 DRFP 特征；需要配套训练模型才能输出 ML 产率。",
            )
    return None


def _hashed_fallback(
    reaction_smiles: str,
    applicability_domain: str,
    unavailable: list[str],
    note: str,
) -> ReactionFeatures:
    return ReactionFeatures(
        reaction_smiles=reaction_smiles,
        method="hashed_reaction_smiles_fallback",
        status="fallback",
        features=_hashed_fingerprint(reaction_smiles),
        applicability_domain=applicability_domain,
        unavailable=unavailable,
        note=note,
    )


def _hashed_fingerprint(reaction_smiles: str, length: int = 32) -> dict[str, int]:
    digest = hashlib.sha256(reaction_smiles.encode("utf-8")).digest()
    values: dict[str, int] = {}
    for index in range(length):
        values[f"hash_{index}"] = digest[index % len(digest)] % 2
    return values
