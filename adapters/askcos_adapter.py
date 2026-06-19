from __future__ import annotations

import os
import requests
from dataclasses import dataclass
from core.route import Route, route_from_dict

@dataclass(frozen=True)
class AskCosResult:
    routes: list[Route]
    used_fallback: bool
    status: str

def get_askcos_url() -> str:
    return os.environ.get("ASKCOS_URL", "http://127.0.0.1:9100")

def check_askcos_available(url: str | None = None) -> bool:
    if not url:
        url = get_askcos_url()
    try:
        response = requests.get(f"{url}/docs", timeout=2.0)
        return response.status_code == 200
    except Exception:
        if "127.0.0.1" in url or "localhost" in url:
            try:
                response = requests.get("http://100.106.169.46:9100/docs", timeout=2.0)
                if response.status_code == 200:
                    return True
            except Exception:
                pass
        return False

def predict_routes_with_askcos(
    smiles: str,
    fallback_routes: list[Route],
    max_routes: int = 3,
    askcos_url: str | None = None,
) -> AskCosResult:
    url = askcos_url or get_askcos_url()
    
    if (not askcos_url) and (not check_askcos_available(url)):
        remote_url = "http://100.106.169.46:9100"
        if check_askcos_available(remote_url):
            url = remote_url

    if not check_askcos_available(url):
        mock_routes = []
        for index, r in enumerate(fallback_routes[:max_routes], start=1):
            mock_routes.append(
                Route(
                    id=f"askcos-route-{index}",
                    title=f"ASKCOS Mock Route {index}",
                    target_id=r.target_id,
                    molecules=r.molecules,
                    steps=r.steps,
                    source="askcos",
                    metadata={**r.metadata, "is_mock": True}
                )
            )
        return AskCosResult(
            routes=mock_routes,
            used_fallback=True,
            status=f"ASKCOS 服务未在线（URL: {url}），已使用 Mock/演示路线进行流程展示。",
        )

    try:
        api_url = f"{url}/api/tree-search/mcts/call-sync-without-token"
        payload = {
            "smiles": smiles,
            "max_depth": 5,
            "max_branching": 25,
            "time_limit": 30
        }
        response = requests.post(api_url, json=payload, timeout=60)
        if response.status_code != 200:
            raise Exception(f"ASKCOS returned status code {response.status_code}: {response.text}")
        
        data = response.json()
        routes = parse_askcos_response(data, max_routes)
        if not routes:
            raise Exception("No retrosynthesis routes found in ASKCOS response.")
            
        return AskCosResult(
            routes=routes[:max_routes],
            used_fallback=False,
            status=f"成功从 ASKCOS ({url}) 加载了 {min(len(routes), max_routes)} 条路线。"
        )
    except Exception as exc:
        mock_routes = []
        for index, r in enumerate(fallback_routes[:max_routes], start=1):
            mock_routes.append(
                Route(
                    id=f"askcos-route-{index}",
                    title=f"ASKCOS Mock Route {index}",
                    target_id=r.target_id,
                    molecules=r.molecules,
                    steps=r.steps,
                    source="askcos",
                    metadata={**r.metadata, "is_mock": True, "error": str(exc)}
                )
            )
        return AskCosResult(
            routes=mock_routes,
            used_fallback=True,
            status=f"ASKCOS 执行失败 ({exc})，已使用 Mock/演示路线进行流程展示。",
        )

def parse_askcos_response(data: dict, max_routes: int) -> list[Route]:
    results = data.get("result", {}).get("output", []) if isinstance(data, dict) else []
    if not results and isinstance(data, dict):
        results = data.get("output", [])
    if not results and isinstance(data, list):
        results = data
        
    routes: list[Route] = []
    for index, item in enumerate(results, start=1):
        tree = item.get("reaction_tree") if isinstance(item, dict) else None
        if not tree and isinstance(item, dict):
            tree = item.get("tree", item)
        if isinstance(tree, dict):
            routes.append(_route_from_tree(tree, index, item))
            
    return routes

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
                "in_stock": bool(node.get("in_stock") or node.get("is_solved") or node.get("as_stock", False)),
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
                    "policy_score": node.get("policy_score") or raw.get("score") or node.get("score"),
                    "template": node.get("template") or "ASKCOS step",
                }
            )
        return molecule_id

    target_id = visit(tree)
    return route_from_dict(
        {
            "id": f"askcos-route-{index}",
            "title": f"ASKCOS Route {index}",
            "target_id": target_id,
            "molecules": list(molecules.values()),
            "steps": steps,
            "metadata": {"raw_score": raw.get("score") if isinstance(raw, dict) else None},
        },
        source="askcos",
    )
