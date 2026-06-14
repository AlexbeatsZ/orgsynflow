from __future__ import annotations

from dataclasses import dataclass

from core.reaction_explain import explain_reaction
from core.route import Route


@dataclass(frozen=True)
class YieldEstimate:
    heuristic_yield_percent: float
    confidence: str
    factors: list[str]
    note: str

    def as_dict(self) -> dict[str, object]:
        return {
            "heuristic_yield_percent": self.heuristic_yield_percent,
            "predicted_yield_percent": self.heuristic_yield_percent,
            "confidence": self.confidence,
            "factors": self.factors,
            "note": self.note,
        }


@dataclass(frozen=True)
class RouteFeasibility:
    route_id: str
    heuristic_overall_yield_percent: float
    heuristic_feasibility_score: float
    risk_flags: list[str]
    note: str

    def as_dict(self) -> dict[str, object]:
        return {
            "route_id": self.route_id,
            "heuristic_overall_yield_percent": self.heuristic_overall_yield_percent,
            "heuristic_feasibility_score": self.heuristic_feasibility_score,
            "estimated_overall_yield_percent": self.heuristic_overall_yield_percent,
            "route_feasibility_score": self.heuristic_feasibility_score,
            "risk_flags": self.risk_flags,
            "note": self.note,
        }


def estimate_reaction_yield(reaction_smiles: str | None, template: str | None = None) -> YieldEstimate:
    explanation = explain_reaction(reaction_smiles, template)
    factors: list[str] = []
    base = 62.0
    confidence = "低"

    if explanation.reaction_type == "酰化/乙酰化":
        base = 78.0
        confidence = "中"
        factors.append("乙酰化通常是教学演示中较稳健的官能团转化。")
    elif explanation.reaction_type == "酯水解":
        base = 70.0
        confidence = "中"
        factors.append("酯水解条件成熟，但实际收率受酸碱条件和后处理影响。")
    else:
        factors.append("当前反应类型未匹配到专门规则。")

    text = f"{reaction_smiles or ''} {template or ''}".lower()
    if any(flag in text for flag in ("cl", "br", "i")):
        base -= 5.0
        factors.append("存在卤素或潜在离去基，需关注副反应。")
    if "." in (reaction_smiles or "").split(">>", 1)[0]:
        base += 3.0
        factors.append("多组分前体明确，适合做单步路线验证。")

    return YieldEstimate(
        heuristic_yield_percent=round(max(5.0, min(base, 95.0)), 1),
        confidence=confidence,
        factors=factors,
        note="规则演示估计：用于相对排序和课堂展示，不是 DRFP/HTE 真实产率模型，不能替代实验测定。",
    )


def score_route_feasibility(route: Route) -> RouteFeasibility:
    if not route.steps:
        return RouteFeasibility(route.id, 0.0, 0.0, ["路线没有反应步骤"], "无法评分。")

    overall_fraction = 1.0
    risk_flags: list[str] = []
    for step in route.steps:
        estimate = estimate_reaction_yield(step.reaction_smiles, step.template)
        overall_fraction *= estimate.heuristic_yield_percent / 100
        if estimate.confidence == "低":
            risk_flags.append(f"{step.id}: 反应类型置信度低")

    stock_bonus = route.stock_count / max(route.precursor_count, 1)
    step_penalty = 1 / route.depth
    feasibility_score = 0.55 * overall_fraction + 0.30 * stock_bonus + 0.15 * step_penalty

    return RouteFeasibility(
        route_id=route.id,
        heuristic_overall_yield_percent=round(overall_fraction * 100, 1),
        heuristic_feasibility_score=round(feasibility_score, 3),
        risk_flags=risk_flags,
        note="规则可行性评分综合了规则估计产率、叶子前体可购买性和路线步数；不是物理化学或机器学习精确结论。",
    )
