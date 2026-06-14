from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReactionExplanation:
    reaction_smiles: str
    reaction_type: str
    formed_bonds: list[str]
    broken_bonds: list[str]
    reaction_center: list[str]
    summary: str

    def as_dict(self) -> dict[str, object]:
        return {
            "reaction_smiles": self.reaction_smiles,
            "reaction_type": self.reaction_type,
            "formed_bonds": self.formed_bonds,
            "broken_bonds": self.broken_bonds,
            "reaction_center": self.reaction_center,
            "summary": self.summary,
        }


def explain_reaction(reaction_smiles: str | None, template: str | None = None) -> ReactionExplanation:
    text = f"{reaction_smiles or ''} {template or ''}".lower()
    rxn = reaction_smiles or ""

    if any(keyword in text for keyword in ("acetylation", "acylation", "酰化", "乙酰化")):
        if "n" in _product_part(rxn).lower():
            return ReactionExplanation(
                reaction_smiles=rxn,
                reaction_type="酰化/乙酰化",
                formed_bonds=["C-N"],
                broken_bonds=["酸酐 C-O"],
                reaction_center=["酰基碳", "胺氮"],
                summary="胺氮作为亲核中心进攻酸酐酰基碳，形成酰胺键；该步骤可视为亲核取代型乙酰化。",
            )
        return ReactionExplanation(
            reaction_smiles=rxn,
            reaction_type="酰化/乙酰化",
            formed_bonds=["C-O"],
            broken_bonds=["酸酐 C-O"],
            reaction_center=["酰基碳", "酚羟基氧"],
            summary="酚羟基氧作为亲核中心进攻酸酐酰基碳，形成酯键；该步骤可视为亲核取代型乙酰化。",
        )

    if any(keyword in text for keyword in ("hydrolysis", "水解")):
        return ReactionExplanation(
            reaction_smiles=rxn,
            reaction_type="酯水解",
            formed_bonds=["C-OH"],
            broken_bonds=["C-O"],
            reaction_center=["酯羰基碳", "离去烷氧基"],
            summary="酯羰基被水或氢氧根进攻，烷氧基离去，最终生成羧酸或羧酸盐。",
        )

    if ">>" not in rxn:
        return ReactionExplanation(
            reaction_smiles=rxn,
            reaction_type="未知",
            formed_bonds=[],
            broken_bonds=[],
            reaction_center=[],
            summary="缺少标准 reaction SMILES，当前只能保留为待解释步骤。",
        )

    return ReactionExplanation(
        reaction_smiles=rxn,
        reaction_type="通用转化",
        formed_bonds=["待原子映射确认"],
        broken_bonds=["待原子映射确认"],
        reaction_center=["反应物与产物结构差异区域"],
        summary="当前使用规则保底解释；后续可接入 RXNMapper 进行原子映射并精确定位成键和断键。",
    )


def _product_part(reaction_smiles: str) -> str:
    if ">>" not in reaction_smiles:
        return ""
    return reaction_smiles.split(">>", 1)[1]
