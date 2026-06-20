from pathlib import Path

from core.route import load_demo_routes
from core.yield_predictor import estimate_reaction_yield, score_route_feasibility


def test_estimate_reaction_yield_returns_reasonable_range() -> None:
    result = estimate_reaction_yield(
        "O=C(O)c1ccccc1O.CC(=O)OC(C)=O>>CC(=O)Oc1ccccc1C(=O)O",
        template="Phenol acetylation",
    )

    assert 0 <= result.heuristic_yield_percent <= 100
    assert result.confidence in {"低", "中", "高"}
    assert "规则估计" in result.note


def test_route_feasibility_scores_short_route_higher_than_longer_route() -> None:
    routes = load_demo_routes(Path("data/demo_routes/aspirin.json"))

    short_score = score_route_feasibility(routes[0])
    longer_score = score_route_feasibility(routes[1])

    assert short_score.heuristic_feasibility_score > longer_score.heuristic_feasibility_score
    assert short_score.heuristic_overall_yield_percent > longer_score.heuristic_overall_yield_percent
