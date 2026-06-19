from __future__ import annotations

import importlib.util
import shlex
import shutil
import subprocess
from pathlib import Path

from adapters.xtb_adapter import (
    WSL_CHEM_BIN,
    find_crest_executable,
    find_xtb_executable,
    run_crest_job,
    run_xtb_job,
)
from adapters.registry import list_adapter_statuses
from adapters.aizynth_adapter import find_aizynthcli, predict_routes_with_fallback
from adapters.askcos_adapter import predict_routes_with_askcos
from adapters.opera_adapter import find_opera_executable
from core.gaussian import coordinates_from_smiles, generate_gaussian_input, parse_gaussian_log
from core.gaussian_runner import find_gaussian_executable, run_gaussian_job
from core.kinetics import analyze_energy_profile
from core.molecule import summarize_molecule
from core.properties import calculate_descriptors, predict_properties
from core.quantum import parse_quantum_log
from core.reaction_features import featurize_reaction
from core.reaction_explain import explain_reaction
from core.reaction_mapping import map_reaction
from core.report import render_report
from core.route import Route, load_demo_routes
from core.route_layout import layout_route
from core.scoring import score_route
from core.transition_state import plan_transition_state_search
from core.yield_predictor import estimate_reaction_yield, estimate_reaction_yield_layered, score_route_feasibility


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


def predict_molecule_properties(smiles: str, include_opera: bool = False) -> dict[str, object]:
    return predict_properties(smiles, include_opera=include_opera).as_dict()


def calculate_molecule_descriptors(smiles: str) -> dict[str, object]:
    return calculate_descriptors(smiles).as_dict()


def analyze_target(
    smiles: str,
    demo_target: str = "Aspirin",
    use_aizynth: bool = False,
    engine: str = "aizynthfinder",
    max_routes: int = 3,
    aizynth_config: str | None = None,
    aizynth_stock: str | None = None,
    aizynth_policy: str | None = None,
    askcos_url: str | None = None,
) -> dict[str, object]:
    fallback_routes = load_demo_routes(DEMO_TARGETS.get(demo_target, DEMO_TARGETS["Aspirin"]))
    if engine == "askcos":
        result = predict_routes_with_askcos(
            smiles,
            fallback_routes,
            max_routes=max_routes,
            askcos_url=askcos_url,
        )
        routes = result.routes
        status = result.status
        used_fallback = result.used_fallback
    elif use_aizynth or engine == "aizynthfinder":
        result = predict_routes_with_fallback(
            smiles,
            fallback_routes,
            max_routes=max_routes,
            config_path=aizynth_config,
            stock_path=aizynth_stock,
            policy_path=aizynth_policy,
        )
        routes = result.routes
        status = _zh_status(result.status)
        used_fallback = result.used_fallback
    else:
        routes = fallback_routes[:max_routes]
        status = "已加载内置演示路线。"
        used_fallback = True

    target = summarize_molecule(smiles)
    route_scores = {route.id: score_route(route) for route in routes}
    feasibility = {route.id: score_route_feasibility(route) for route in routes}
    report = render_report(target, routes, route_scores, status)

    return {
        "status": status,
        "used_fallback": used_fallback,
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


def map_single_reaction(reaction_smiles: str) -> dict[str, object]:
    return map_reaction(reaction_smiles).as_dict()


def plan_single_transition_state(reaction_smiles: str) -> dict[str, object]:
    return plan_transition_state_search(reaction_smiles).as_dict()


def estimate_single_reaction_yield(reaction_smiles: str, template: str | None = None) -> dict[str, object]:
    return estimate_reaction_yield_layered(reaction_smiles, template)


def calculate_reaction_features(reaction_smiles: str) -> dict[str, object]:
    return featurize_reaction(reaction_smiles).as_dict()


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
        "source": _executable_source(executable),
    }


def compute_backend_status() -> dict[str, object]:
    return {
        "gaussian": gaussian_status(),
        "aizynthfinder": _command_status("AiZynthFinder", find_aizynthcli()),
        "opera": _command_status("OPERA", find_opera_executable()),
        "xtb": _command_status("xTB", find_xtb_executable()),
        "crest": _command_status("CREST", find_crest_executable()),
        "openbabel": _command_status("Open Babel", _find_command(("obabel", "obabel.exe"))),
        "goodvibes": _python_package_status("GoodVibes", "goodvibes"),
        "pyscf": _python_package_status("PySCF", "pyscf"),
        "psi4": _command_status("Psi4", _find_command(("psi4", "psi4.exe"))),
        "geometric": _command_status("geomeTRIC", _find_command(("geometric-optimize", "geometric-optimize.exe"))),
        "ase": _python_package_status("ASE", "ase"),
    }


def run_xtb_for_smiles(smiles: str, timeout_seconds: int = 300) -> dict[str, object]:
    return run_xtb_job(_xyz_from_smiles(smiles), timeout_seconds=timeout_seconds).as_dict()


def run_crest_for_smiles(smiles: str, timeout_seconds: int = 1800) -> dict[str, object]:
    return run_crest_job(_xyz_from_smiles(smiles), timeout_seconds=timeout_seconds).as_dict()


def parse_gaussian_text(text: str) -> dict[str, object]:
    quantum = parse_quantum_log(text).as_dict()
    gaussian = quantum["gaussian_result"]
    if isinstance(gaussian, dict):
        return {
            **gaussian,
            "quantum_parse": quantum,
        }
    return {"quantum_parse": quantum}


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
        "layout": _route_layout_to_dict(route),
    }


def _route_layout_to_dict(route: Route) -> dict[str, object]:
    graph = layout_route(route)
    return {
        "nodes": {key: node.__dict__ for key, node in graph.nodes.items()},
        "edges": [edge.__dict__ for edge in graph.edges],
    }


def _zh_status(status: str) -> str:
    replacements = {
        "AiZynthFinder CLI not found; using bundled demo routes.": "未找到 AiZynthFinder CLI，已回退到内置演示路线。",
        "AiZynthFinder CLI found but no config/model stock was configured; using bundled demo routes.": "已检测到 AiZynthFinder，但尚未配置 policy/stock/config，当前显示内置演示候选路线。",
        "using bundled demo routes": "已回退到内置演示路线",
    }
    return replacements.get(status, status)


def _xyz_from_smiles(smiles: str) -> str:
    coordinates = coordinates_from_smiles(smiles)
    coordinate_lines = [line for line in coordinates.splitlines() if line.strip()]
    return "\n".join([str(len(coordinate_lines)), smiles, *coordinate_lines, ""])


def _command_status(name: str, executable: str | None) -> dict[str, object]:
    return {
        "name": name,
        "available": executable is not None,
        "executable": executable,
        "source": _executable_source(executable),
    }


def _python_package_status(name: str, package: str) -> dict[str, object]:
    available = importlib.util.find_spec(package) is not None
    source = "python" if available else None
    executable: str | None = None
    if not available:
        wsl_available = _wsl_python_package_available(package)
        available = wsl_available
        source = "wsl-python" if wsl_available else None
        executable = f"wsl:{WSL_CHEM_BIN}/python" if wsl_available else None
    return {
        "name": name,
        "available": available,
        "executable": executable,
        "source": source,
    }


def _find_command(names: tuple[str, ...]) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    for name in names:
        wsl_path = _find_wsl_command(name.removesuffix(".exe"))
        if wsl_path:
            return wsl_path
    return None


def _find_wsl_command(name: str) -> str | None:
    wsl = shutil.which("wsl")
    if not wsl:
        return None
    candidate = f"{WSL_CHEM_BIN}/{name}"
    try:
        completed = subprocess.run(
            [wsl, "-e", "test", "-x", candidate],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except Exception:
        return None
    return f"wsl:{candidate}" if completed.returncode == 0 else None


def _wsl_python_package_available(package: str) -> bool:
    wsl = shutil.which("wsl")
    if not wsl:
        return False
    snippet = f"import importlib.util; raise SystemExit(0 if importlib.util.find_spec({package!r}) else 1)"
    script = f"{shlex.quote(f'{WSL_CHEM_BIN}/python')} -c {shlex.quote(snippet)}"
    try:
        completed = subprocess.run(
            [wsl, "-e", "bash", "-lc", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception:
        return False
    return completed.returncode == 0


def _executable_source(executable: str | None) -> str | None:
    if executable is None:
        return None
    if executable.startswith("wsl:"):
        return "wsl"
    if executable.lower().endswith(".exe") or executable.startswith("/mnt/c/"):
        return "windows"
    return "path"
