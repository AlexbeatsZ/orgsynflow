from __future__ import annotations

from dataclasses import dataclass

from core.route import Route


@dataclass(frozen=True)
class RouteScore:
    route_id: str
    route_score: float
    model_score: float
    stock_score: float
    step_score: float
    explanation: str

    def as_dict(self) -> dict[str, object]:
        return {
            "route_id": self.route_id,
            "route_score": self.route_score,
            "model_score": self.model_score,
            "stock_score": self.stock_score,
            "step_score": self.step_score,
            "explanation": self.explanation,
        }


def score_route(route: Route) -> RouteScore:
    model_score = route.mean_policy_score if route.mean_policy_score is not None else 0.55
    stock_score = route.stock_count / max(route.precursor_count, 1)
    step_score = 1 / (1 + max(route.depth - 1, 0))
    route_score = 0.45 * model_score + 0.35 * stock_score + 0.20 * step_score
    explanation = (
        f"model={model_score:.2f}, stock={stock_score:.2f}, steps={step_score:.2f}; "
        "V1 score uses model confidence, purchasable precursors, and route length."
    )
    return RouteScore(
        route_id=route.id,
        route_score=round(route_score, 3),
        model_score=round(model_score, 3),
        stock_score=round(stock_score, 3),
        step_score=round(step_score, 3),
        explanation=explanation,
    )
