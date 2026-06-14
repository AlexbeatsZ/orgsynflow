from __future__ import annotations

from dataclasses import dataclass

from core.reaction_explain import explain_reaction


@dataclass(frozen=True)
class ReactionMapping:
    reaction_smiles: str
    mapped_reaction_smiles: str | None
    method: str
    status: str
    confidence: str
    reaction_center: list[str]
    formed_bonds: list[str]
    broken_bonds: list[str]
    note: str

    def as_dict(self) -> dict[str, object]:
        return {
            "reaction_smiles": self.reaction_smiles,
            "mapped_reaction_smiles": self.mapped_reaction_smiles,
            "method": self.method,
            "status": self.status,
            "confidence": self.confidence,
            "reaction_center": self.reaction_center,
            "formed_bonds": self.formed_bonds,
            "broken_bonds": self.broken_bonds,
            "note": self.note,
        }


def map_reaction(reaction_smiles: str) -> ReactionMapping:
    try:
        from rxnmapper import RXNMapper
    except Exception:
        explanation = explain_reaction(reaction_smiles)
        return ReactionMapping(
            reaction_smiles=reaction_smiles,
            mapped_reaction_smiles=None,
            method="heuristic_without_rxnmapper",
            status="unavailable",
            confidence="低",
            reaction_center=explanation.reaction_center,
            formed_bonds=explanation.formed_bonds,
            broken_bonds=explanation.broken_bonds,
            note="未安装 RXNMapper；当前返回规则反应中心占位，不用于自动 TS 判定。",
        )

    try:
        result = RXNMapper().get_attention_guided_atom_maps([reaction_smiles])[0]
    except Exception as exc:
        explanation = explain_reaction(reaction_smiles)
        return ReactionMapping(
            reaction_smiles=reaction_smiles,
            mapped_reaction_smiles=None,
            method="rxnmapper",
            status="failed",
            confidence="低",
            reaction_center=explanation.reaction_center,
            formed_bonds=explanation.formed_bonds,
            broken_bonds=explanation.broken_bonds,
            note=f"RXNMapper 调用失败：{exc}",
        )

    explanation = explain_reaction(reaction_smiles)
    confidence_score = float(result.get("confidence", 0.0) or 0.0)
    confidence = "高" if confidence_score >= 0.8 else "中" if confidence_score >= 0.5 else "低"
    return ReactionMapping(
        reaction_smiles=reaction_smiles,
        mapped_reaction_smiles=result.get("mapped_rxn"),
        method="rxnmapper",
        status="mapped",
        confidence=confidence,
        reaction_center=explanation.reaction_center,
        formed_bonds=explanation.formed_bonds,
        broken_bonds=explanation.broken_bonds,
        note=f"RXNMapper confidence={confidence_score:.3f}；成键/断键仍需后续结构差异分析复核。",
    )
