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

from rdkit import Chem

from core.route import Route, route_from_dict

WSL_AIZYNTHCLI = "/home/meta/.local/opt/miniforge3/envs/orgsynflow-chem/bin/aizynthcli"
WSL_TEMP_ROOT = "/tmp/codex/orgsynflow"


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
    molecule_ids_by_smiles: dict[str, str] = {}
    expanded_molecule_ids: set[str] = set()

    def add_molecule(node: dict, is_target: bool = False) -> str:
        raw_smiles = node.get("smiles") or node.get("mol") or node.get("smiles_str") or f"unknown-{len(molecules)}"
        try:
            mol = Chem.MolFromSmiles(raw_smiles)
            smiles = Chem.MolToSmiles(mol) if mol else raw_smiles
        except Exception:
            smiles = raw_smiles

        existing_id = molecule_ids_by_smiles.get(smiles)
        if existing_id:
            if node.get("in_stock") or node.get("is_solved"):
                molecules[existing_id]["in_stock"] = True
            return existing_id

        molecule_id = f"m{len(molecules) + 1}"
        molecule_ids_by_smiles[smiles] = molecule_id
        molecules[molecule_id] = {
            "id": molecule_id,
            "name": node.get("name") or ("Target" if is_target else f"Mol {len(molecules) + 1}"),
            "smiles": smiles,
            "in_stock": bool(node.get("in_stock") or node.get("is_solved")),
        }
        return molecule_id

    def add_step(product_id: str, precursor_ids: list[str], reaction_node: dict, path_ids: set[str]) -> None:
        if not precursor_ids:
            return
        
        # Deduplicate redundant nodes/cycles: if a precursor is already in the ancestral path
        if any(p_id in path_ids for p_id in precursor_ids):
            return
            
        product_smiles = molecules[product_id]["smiles"]
        precursor_smiles = ".".join(molecules[item]["smiles"] for item in precursor_ids)
        metadata = reaction_node.get("metadata") if isinstance(reaction_node.get("metadata"), dict) else {}
        classification = metadata.get("classification")
        template = reaction_node.get("template") or classification
        if not template or str(template).startswith("0.0 "):
            template = "AiZynth step"
        policy_score = reaction_node.get("policy_score")
        if policy_score is None:
            policy_score = metadata.get("policy_probability")
        if policy_score is None:
            policy_score = raw.get("score")
        steps.append(
            {
                "id": f"s{len(steps) + 1}",
                "product_id": product_id,
                "precursor_ids": precursor_ids,
                # AiZynth reaction nodes are stored in retrosynthetic direction.
                # Build the forward reaction from their molecule children instead.
                "reaction_smiles": f"{precursor_smiles}>>{product_smiles}",
                "policy_score": policy_score,
                "template": template,
            }
        )

    def visit_molecule(node: dict, path_ids: set[str], is_target: bool = False) -> str:
        molecule_id = add_molecule(node, is_target=is_target)
        if molecule_id in expanded_molecule_ids:
            return molecule_id
        expanded_molecule_ids.add(molecule_id)
        
        new_path_ids = path_ids | {molecule_id}

        children = [child for child in (node.get("children") or node.get("precursors") or []) if isinstance(child, dict)]
        reaction_children = [child for child in children if child.get("is_reaction") or child.get("type") == "reaction"]
        if reaction_children:
            for reaction_node in reaction_children:
                precursor_nodes = [
                    child
                    for child in (reaction_node.get("children") or reaction_node.get("precursors") or [])
                    if isinstance(child, dict) and not (child.get("is_reaction") or child.get("type") == "reaction")
                ]
                precursor_ids = [visit_molecule(child, new_path_ids) for child in precursor_nodes]
                add_step(molecule_id, precursor_ids, reaction_node, new_path_ids)
        else:
            # Retain support for simplified trees that attach precursor molecules
            # directly to their product without an explicit reaction node.
            precursor_nodes = [
                child for child in children if not (child.get("is_reaction") or child.get("type") == "reaction")
            ]
            precursor_ids = [visit_molecule(child, new_path_ids) for child in precursor_nodes]
            if precursor_ids:
                add_step(molecule_id, precursor_ids, node, new_path_ids)
        return molecule_id

    target_id = visit_molecule(tree, set(), is_target=True)
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
    wsl_output_path = f"{WSL_TEMP_ROOT}/aizynth_routes_{uuid.uuid4().hex}.json"
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
    script = f"mkdir -p {shlex.quote(WSL_TEMP_ROOT)} && " + " ".join(command)
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
