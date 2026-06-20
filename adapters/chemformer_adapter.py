from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx
from rdkit import Chem

from core.route import Route, route_from_dict


@dataclass(frozen=True)
class ChemformerResult:
    routes: list[Route]
    available: bool
    used_fallback: bool
    status: str


def get_chemformer_url() -> str:
    return os.environ.get("CHEMFORMER_URL", "http://127.0.0.1:8000").rstrip("/")


def check_chemformer_available(url: str | None = None) -> bool:
    endpoint = (url or get_chemformer_url()).rstrip("/")
    try:
        response = httpx.get(f"{endpoint}/api/health", timeout=2.0)
        if response.status_code != 200:
            return False
        payload = response.json()
        return isinstance(payload, dict) and payload.get("status") == "ok"
    except (httpx.HTTPError, ValueError):
        return False


def predict_routes_with_chemformer(
    smiles: str,
    max_routes: int = 5,
    chemformer_url: str | None = None,
    timeout_seconds: float = 300.0,
) -> ChemformerResult:
    url = (chemformer_url or get_chemformer_url()).rstrip("/")
    requested_predictions = min(20, max(max_routes, max_routes * 3))
    try:
        response = httpx.post(
            f"{url}/api/predict",
            json={"smiles": smiles, "top_k": requested_predictions},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        routes = parse_chemformer_response(response.json(), max_routes=max_routes)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        return ChemformerResult(
            routes=[],
            available=False,
            used_fallback=False,
            status=f"Chemformer 单步逆合成服务调用失败（{url}）：{exc}",
        )

    if not routes:
        return ChemformerResult(
            routes=[],
            available=True,
            used_fallback=False,
            status="Chemformer 已完成计算，但没有返回可解析的单步候选。",
        )
    return ChemformerResult(
        routes=routes,
        available=True,
        used_fallback=False,
        status=f"Chemformer 已返回 {len(routes)} 个单步逆合成候选。",
    )


def parse_chemformer_response(payload: dict[str, Any], max_routes: int = 5) -> list[Route]:
    target = _canonicalize(payload.get("input"))
    if target is None:
        raise ValueError("Chemformer response does not contain a valid input SMILES")
    predictions = payload.get("predictions")
    if not isinstance(predictions, list):
        raise ValueError("Chemformer response does not contain a predictions list")

    routes: list[Route] = []
    seen: set[tuple[str, ...]] = set()
    for raw_index, prediction in enumerate(predictions, start=1):
        if not isinstance(prediction, dict):
            continue
        reactants = prediction.get("reactants")
        if not isinstance(reactants, str):
            continue
        precursor_smiles = [_canonicalize(part) for part in reactants.split(".") if part.strip()]
        if not precursor_smiles or any(item is None for item in precursor_smiles):
            continue
        canonical_precursors = [item for item in precursor_smiles if item is not None]
        if target in canonical_precursors:
            continue
        candidate_key = tuple(sorted(canonical_precursors))
        if candidate_key in seen:
            continue
        seen.add(candidate_key)

        route_number = len(routes) + 1
        target_id = f"chemformer-{route_number}-target"
        precursor_ids = [f"chemformer-{route_number}-precursor-{index}" for index in range(1, len(canonical_precursors) + 1)]
        rank = prediction.get("rank") if isinstance(prediction.get("rank"), int) else raw_index
        raw_log_likelihood = prediction.get("log_likelihood")
        log_likelihood = float(raw_log_likelihood) if isinstance(raw_log_likelihood, (int, float)) else None
        routes.append(
            route_from_dict(
                {
                    "id": f"chemformer-route-{route_number}",
                    "title": f"Chemformer 单步候选 #{rank}",
                    "target_id": target_id,
                    "molecules": [
                        {"id": target_id, "name": "目标产物", "smiles": target, "in_stock": False},
                        *[
                            {
                                "id": precursor_id,
                                "name": f"反应物 {index}",
                                "smiles": precursor,
                                "in_stock": False,
                            }
                            for index, (precursor_id, precursor) in enumerate(
                                zip(precursor_ids, canonical_precursors), start=1
                            )
                        ],
                    ],
                    "steps": [
                        {
                            "id": f"chemformer-step-{route_number}",
                            "product_id": target_id,
                            "precursor_ids": precursor_ids,
                            "reaction_smiles": f"{'.'.join(canonical_precursors)}>>{target}",
                            "policy_score": None,
                            "template": "Chemformer 单步逆合成",
                        }
                    ],
                    "metadata": {
                        "rank": rank,
                        "log_likelihood": log_likelihood,
                        "prediction_type": "single_step",
                    },
                },
                source="chemformer",
            )
        )
        if len(routes) >= max_routes:
            break
    return routes


def _canonicalize(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    molecule = Chem.MolFromSmiles(value.strip())
    return Chem.MolToSmiles(molecule) if molecule is not None else None
