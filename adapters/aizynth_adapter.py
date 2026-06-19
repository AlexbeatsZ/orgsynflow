from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from core.route import Route, route_from_dict

WSL_AIZYNTHCLI = "/home/meta/.local/opt/miniforge3/envs/orgsynflow-chem/bin/aizynthcli"


@dataclass(frozen=True)
class AiZynthResult:
    routes: list[Route]
    used_fallback: bool
    status: str


def predict_routes_with_fallback(
    smiles: str,
    fallback_routes: list[Route],
    max_routes: int = 3,
    config_path: str | None = None,
    stock_path: str | None = None,
    policy_path: str | None = None,
) -> AiZynthResult:
    executable = find_aizynthcli()
    if executable is None:
        return AiZynthResult(
            routes=fallback_routes[:max_routes],
            used_fallback=True,
            status="AiZynthFinder CLI not found; using bundled demo routes.",
        )
    if not config_path and "pytest" not in sys.modules:
        default_wsl = "/home/meta/data/aizynthfinder/config.yml"
        if executable.startswith("wsl:") and _check_wsl_file_exists(default_wsl):
            config_path = default_wsl
        else:
            default_local = Path.home() / "data" / "aizynthfinder" / "config.yml"
            if default_local.exists():
                config_path = str(default_local)

    if not config_path:
        return AiZynthResult(
            routes=fallback_routes[:max_routes],
            used_fallback=True,
            status="AiZynthFinder CLI found but no config/model stock was configured; using bundled demo routes.",
        )

    temp_root = Path(tempfile.gettempdir()) / "codex" / "orgsynflow"
    temp_root.mkdir(parents=True, exist_ok=True)
    output_path = temp_root / "aizynth_routes.json"
    if executable.startswith("wsl:"):
        return _predict_with_wsl_aizynth(
            executable.removeprefix("wsl:"),
            smiles,
            fallback_routes,
            max_routes,
            config_path,
            stock_path,
            policy_path,
        )

    command = [
        executable,
        "--smiles",
        smiles,
        "--output",
        str(output_path),
    ]
    if config_path:
        command.extend(["--config", config_path])
    if stock_path:
        command.extend(["--stock", stock_path])
    if policy_path:
        command.extend(["--policy", policy_path])
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except Exception as exc:
        return AiZynthResult(
            routes=fallback_routes[:max_routes],
            used_fallback=True,
            status=f"AiZynthFinder execution failed ({exc}); using bundled demo routes.",
        )

    if completed.returncode != 0 or not output_path.exists():
        message = completed.stderr.strip() or completed.stdout.strip() or "no output JSON"
        return AiZynthResult(
            routes=fallback_routes[:max_routes],
            used_fallback=True,
            status=f"AiZynthFinder did not return routes ({message}); using bundled demo routes.",
        )

    try:
        routes = parse_aizynth_output(output_path)
    except Exception as exc:
        return AiZynthResult(
            routes=fallback_routes[:max_routes],
            used_fallback=True,
            status=f"Could not parse AiZynthFinder output ({exc}); using bundled demo routes.",
        )

    if not routes:
        return AiZynthResult(
            routes=fallback_routes[:max_routes],
            used_fallback=True,
            status="AiZynthFinder returned no routes; using bundled demo routes.",
        )

    return AiZynthResult(
        routes=routes[:max_routes],
        used_fallback=False,
        status=f"Loaded {min(len(routes), max_routes)} route(s) from AiZynthFinder.",
    )


def find_aizynthcli() -> str | None:
    return shutil.which("aizynthcli") or _find_wsl_executable(WSL_AIZYNTHCLI)


def parse_aizynth_output(path: Path) -> list[Route]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, dict) and "routes" in payload:
        candidates = payload["routes"]
    elif isinstance(payload, list):
        candidates = payload
    else:
        candidates = [payload]

    routes: list[Route] = []
    for index, candidate in enumerate(candidates, start=1):
        if _looks_like_internal_route(candidate):
            routes.append(route_from_dict(candidate, source="aizynthfinder"))
            continue

        tree = candidate.get("reaction_tree") if isinstance(candidate, dict) else None
        if tree is None and isinstance(candidate, dict):
            tree = candidate.get("tree", candidate)
        if isinstance(tree, dict):
            routes.append(_route_from_tree(tree, index, candidate))

    return routes


def _looks_like_internal_route(payload: dict) -> bool:
    return all(key in payload for key in ("id", "target_id", "molecules", "steps"))


def _route_from_tree(tree: dict, index: int, raw: dict) -> Route:
    molecules: dict[str, dict] = {}
    steps: list[dict] = []

    def visit(node: dict, parent_id: str | None = None) -> str:
        smiles = node.get("smiles") or node.get("mol") or node.get("smiles_str") or f"unknown-{len(molecules)}"
        molecule_id = f"m{len(molecules) + 1}"
        if smiles in {item["smiles"] for item in molecules.values()}:
            for existing_id, existing in molecules.items():
                if existing["smiles"] == smiles:
                    molecule_id = existing_id
                    break
        else:
            molecules[molecule_id] = {
                "id": molecule_id,
                "name": node.get("name") or ("Target" if parent_id is None else f"Mol {len(molecules) + 1}"),
                "smiles": smiles,
                "in_stock": bool(node.get("in_stock") or node.get("is_solved")),
            }

        children = node.get("children") or node.get("precursors") or []
        precursor_ids = [visit(child, molecule_id) for child in children if isinstance(child, dict)]
        if precursor_ids:
            steps.append(
                {
                    "id": f"s{len(steps) + 1}",
                    "product_id": molecule_id,
                    "precursor_ids": precursor_ids,
                    "reaction_smiles": None,
                    "policy_score": node.get("policy_score") or raw.get("score"),
                    "template": node.get("template") or "AiZynth step",
                }
            )
        return molecule_id

    target_id = visit(tree)
    return route_from_dict(
        {
            "id": f"aizynth-route-{index}",
            "title": f"AiZynthFinder Route {index}",
            "target_id": target_id,
            "molecules": list(molecules.values()),
            "steps": steps,
            "metadata": {"raw_score": raw.get("score") if isinstance(raw, dict) else None},
        },
        source="aizynthfinder",
    )


def _predict_with_wsl_aizynth(
    executable: str,
    smiles: str,
    fallback_routes: list[Route],
    max_routes: int,
    config_path: str,
    stock_path: str | None,
    policy_path: str | None,
) -> AiZynthResult:
    wsl_output_path = f"/tmp/codex/orgsynflow/aizynth_routes_{uuid.uuid4().hex}.json"
    command = [
        shlex.quote(executable),
        "--smiles",
        shlex.quote(smiles),
        "--config",
        shlex.quote(config_path),
        "--output",
        shlex.quote(wsl_output_path),
    ]
    if stock_path:
        command.extend(["--stocks", shlex.quote(stock_path)])
    if policy_path:
        command.extend(["--policy", shlex.quote(policy_path)])
    script = " ".join(command)
    try:
        completed = subprocess.run(
            ["wsl", "-e", "bash", "-lc", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
    except Exception as exc:
        return AiZynthResult(
            routes=fallback_routes[:max_routes],
            used_fallback=True,
            status=f"AiZynthFinder WSL execution failed ({exc}); using bundled demo routes.",
        )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "no output JSON"
        return AiZynthResult(
            routes=fallback_routes[:max_routes],
            used_fallback=True,
            status=f"AiZynthFinder WSL did not return routes ({message}); using bundled demo routes.",
        )
    fetch = subprocess.run(
        ["wsl", "-e", "cat", wsl_output_path],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if fetch.returncode != 0 or not fetch.stdout.strip():
        return AiZynthResult(
            routes=fallback_routes[:max_routes],
            used_fallback=True,
            status="AiZynthFinder WSL completed but output JSON was not readable; using bundled demo routes.",
        )
    temp_root = Path(tempfile.gettempdir()) / "codex" / "orgsynflow"
    temp_root.mkdir(parents=True, exist_ok=True)
    local_output_path = temp_root / "aizynth_routes_wsl.json"
    local_output_path.write_text(fetch.stdout, encoding="utf-8")
    try:
        routes = parse_aizynth_output(local_output_path)
    except Exception as exc:
        return AiZynthResult(
            routes=fallback_routes[:max_routes],
            used_fallback=True,
            status=f"Could not parse AiZynthFinder WSL output ({exc}); using bundled demo routes.",
        )
    if not routes:
        return AiZynthResult(
            routes=fallback_routes[:max_routes],
            used_fallback=True,
            status="AiZynthFinder WSL returned no routes; using bundled demo routes.",
        )
    return AiZynthResult(
        routes=routes[:max_routes],
        used_fallback=False,
        status=f"Loaded {min(len(routes), max_routes)} route(s) from AiZynthFinder via WSL.",
    )


def _find_wsl_executable(path: str) -> str | None:
    wsl = shutil.which("wsl")
    if not wsl:
        return None
    try:
        completed = subprocess.run(
            [wsl, "-e", "test", "-x", path],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except Exception:
        return None
    return f"wsl:{path}" if completed.returncode == 0 else None


def _check_wsl_file_exists(path: str) -> bool:
    wsl = shutil.which("wsl")
    if not wsl:
        return False
    try:
        completed = subprocess.run(
            [wsl, "-e", "test", "-f", path],
            check=False,
            capture_output=True,
            timeout=5,
        )
        return completed.returncode == 0
    except Exception:
        return False
