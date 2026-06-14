from __future__ import annotations

import hashlib
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
        return ReactionFeatures(
            reaction_smiles=reaction_smiles,
            method="hashed_reaction_smiles_fallback",
            status="fallback",
            features=_hashed_fingerprint(reaction_smiles),
            applicability_domain="未知；DRFP/RXNFP 未安装，仅可作为稳定测试特征。",
            unavailable=["drfp", "rxnfp"],
            note="未安装 DRFP/RXNFP；当前输出不是训练模型特征，不应用于真实产率预测。",
        )

    try:
        vector = DrfpEncoder.encode([reaction_smiles], n_folded_length=256)[0]
    except Exception as exc:
        return ReactionFeatures(
            reaction_smiles=reaction_smiles,
            method="hashed_reaction_smiles_fallback",
            status="fallback",
            features=_hashed_fingerprint(reaction_smiles),
            applicability_domain="未知；DRFP 已安装但编码失败，仅可作为稳定测试特征。",
            unavailable=["drfp_runtime"],
            note=f"DRFP 编码失败：{exc}；当前输出不是训练模型特征，不应用于真实产率预测。",
        )
    return ReactionFeatures(
        reaction_smiles=reaction_smiles,
        method="drfp",
        status="available",
        features={f"drfp_{index}": int(value) for index, value in enumerate(vector)},
        applicability_domain="取决于后续训练数据；DRFP 只提供反应指纹，不单独构成产率模型。",
        note="DRFP 特征已生成；需要配套训练模型才能输出 ML 产率。",
    )


def _hashed_fingerprint(reaction_smiles: str, length: int = 32) -> dict[str, int]:
    digest = hashlib.sha256(reaction_smiles.encode("utf-8")).digest()
    values: dict[str, int] = {}
    for index in range(length):
        values[f"hash_{index}"] = digest[index % len(digest)] % 2
    return values
