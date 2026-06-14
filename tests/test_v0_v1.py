from pathlib import Path

from adapters.aizynth_adapter import predict_routes_with_fallback
from core.molecule import summarize_molecule
from core.report import render_report
from core.route import load_demo_routes
from core.scoring import score_route


def test_demo_routes_have_leaf_precursor_stock_scores() -> None:
    routes = load_demo_routes(Path("data/demo_routes/aspirin.json"))

    assert len(routes) == 2
    assert routes[0].precursor_count == 2
    assert routes[0].stock_count == 2
    assert score_route(routes[0]).stock_score == 1.0


def test_report_renders_target_and_route() -> None:
    routes = load_demo_routes(Path("data/demo_routes/paracetamol.json"))
    target = summarize_molecule("CC(=O)Nc1ccc(O)cc1")
    scores = {route.id: score_route(route) for route in routes}

    report = render_report(target, routes, scores, "测试状态")

    assert "路线分析报告" in report
    assert "Paracetamol" in report
    assert "测试状态" in report


def test_aizynth_fallback_is_testable_without_cli() -> None:
    routes = load_demo_routes(Path("data/demo_routes/aspirin.json"))

    result = predict_routes_with_fallback("CC(=O)Oc1ccccc1C(=O)O", routes, max_routes=1)

    assert len(result.routes) == 1
    assert result.used_fallback is True
    assert "demo routes" in result.status
