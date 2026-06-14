from __future__ import annotations

from pathlib import Path

from adapters.registry import list_adapter_statuses
from adapters.aizynth_adapter import predict_routes_with_fallback
from core.gaussian import generate_gaussian_input, parse_gaussian_log
from core.gaussian_runner import find_gaussian_executable, run_gaussian_job
from core.kinetics import analyze_energy_profile
from core.molecule import summarize_molecule
from core.reaction_explain import explain_reaction
from core.report import render_report
from core.route import Route, load_demo_routes
from core.scoring import score_route
from core.yield_predictor import estimate_reaction_yield, score_route_feasibility


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "data" / "demo_routes"
DEMO_TARGETS = {
    "Aspirin": DEMO_DIR / "aspirin.json",
    "Paracetamol": DEMO_DIR / "paracetamol.json",
}


def list_adapters() -> list[dict[str, object]]:
    return [status.as_dict() for status in list_adapter_statuses()]


def summarize_target_molecule(smiles: str) -> dict[str, object]:
    return summarize_molecule(smiles).as_display_dict()


def analyze_target(
    smiles: str,
    demo_target: str = "Aspirin",
    use_aizynth: bool = False,
    max_routes: int = 3,
) -> dict[str, object]:
    fallback_routes = load_demo_routes(DEMO_TARGETS.get(demo_target, DEMO_TARGETS["Aspirin"]))
    if use_aizynth:
        result = predict_routes_with_fallback(smiles, fallback_routes, max_routes=max_routes)
        routes = result.routes
        status = _zh_status(result.status)
    else:
        routes = fallback_routes[:max_routes]
        status = "已加载内置演示路线。"

    target = summarize_molecule(smiles)
    route_scores = {route.id: score_route(route) for route in routes}
    feasibility = {route.id: score_route_feasibility(route) for route in routes}
    report = render_report(target, routes, route_scores, status)

    return {
        "status": status,
        "target": target.as_display_dict(),
        "routes": [_route_to_dict(route) for route in routes],
        "route_scores": {key: value.as_dict() for key, value in route_scores.items()},
        "feasibility": {key: value.as_dict() for key, value in feasibility.items()},
        "report_markdown": report,
    }


def explain_single_reaction(reaction_smiles: str, template: str | None = None) -> dict[str, object]:
    explanation = explain_reaction(reaction_smiles, template)
    yield_estimate = estimate_reaction_yield(reaction_smiles, template)
    return {
        **explanation.as_dict(),
        "yield_estimate": yield_estimate.as_dict(),
    }


def make_gaussian_input(payload: dict[str, object]) -> str:
    return generate_gaussian_input(
        smiles=str(payload["smiles"]),
        title=str(payload.get("title", "OrgSynFlow Gaussian job")),
        method=str(payload.get("method", "B3LYP")),
        basis=str(payload.get("basis", "6-31G(d)")),
        job_type=str(payload.get("job_type", "opt freq")),
        charge=int(payload.get("charge", 0)),
        multiplicity=int(payload.get("multiplicity", 1)),
    )


def run_local_gaussian(payload: dict[str, object]) -> dict[str, object]:
    gjf = make_gaussian_input(payload)
    timeout_seconds = int(payload.get("timeout_seconds", 3600))
    executable = payload.get("executable")
    result = run_gaussian_job(
        gjf,
        executable=str(executable) if executable else None,
        timeout_seconds=timeout_seconds,
    )
    return result.as_dict()


def gaussian_status() -> dict[str, object]:
    executable = find_gaussian_executable()
    return {
        "available": executable is not None,
        "executable": executable,
    }


def parse_gaussian_text(text: str) -> dict[str, object]:
    return parse_gaussian_log(text).as_dict()


def analyze_profile_from_logs(reactant_log: str, product_log: str, ts_log: str) -> dict[str, object]:
    reactants = parse_gaussian_log(reactant_log)
    products = parse_gaussian_log(product_log)
    ts = parse_gaussian_log(ts_log)
    return analyze_energy_profile(reactants, products, ts).as_dict()


def _route_to_dict(route: Route) -> dict[str, object]:
    return {
        "id": route.id,
        "title": route.title,
        "target_id": route.target_id,
        "source": route.source,
        "depth": route.depth,
        "precursor_count": route.precursor_count,
        "stock_count": route.stock_count,
        "molecules": [molecule.__dict__ for molecule in route.molecules],
        "steps": [step.__dict__ for step in route.steps],
    }


def _zh_status(status: str) -> str:
    replacements = {
        "AiZynthFinder CLI not found; using bundled demo routes.": "未找到 AiZynthFinder CLI，已回退到内置演示路线。",
        "using bundled demo routes": "已回退到内置演示路线",
    }
    return replacements.get(status, status)
