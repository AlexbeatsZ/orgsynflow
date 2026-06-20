from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from adapters import chemformer_adapter
from adapters.chemformer_adapter import ChemformerResult, parse_chemformer_response
from api.main import app


SAMPLE_RESPONSE = {
    "input": "CC(=O)Oc1ccccc1C(=O)O",
    "predictions": [
        {"rank": 1, "reactants": "CC(=O)O.O=C(O)c1ccccc1O", "log_likelihood": -0.25},
        {"rank": 2, "reactants": "O=C(O)c1ccccc1O.CC(=O)O", "log_likelihood": -0.5},
        {"rank": 3, "reactants": "not-a-smiles", "log_likelihood": -0.75},
        {"rank": 4, "reactants": "CC(=O)Cl.O=C(O)c1ccccc1O", "log_likelihood": -1.0},
        {"rank": 5, "reactants": "CC(=O)Oc1ccccc1C(=O)O", "log_likelihood": -1.5},
        {"rank": 6, "reactants": "CC(=O)Oc1ccccc1C(=O)O.N", "log_likelihood": -2.0},
    ],
}


def test_parse_chemformer_response_builds_forward_single_step_routes() -> None:
    routes = parse_chemformer_response(SAMPLE_RESPONSE, max_routes=5)

    assert len(routes) == 2
    route = routes[0]
    assert route.source == "chemformer"
    assert route.depth == 1
    assert route.metadata == {"rank": 1, "log_likelihood": -0.25, "prediction_type": "single_step"}
    assert len(route.steps[0].precursor_ids) == 2
    assert route.steps[0].reaction_smiles == "CC(=O)O.O=C(O)c1ccccc1O>>CC(=O)Oc1ccccc1C(=O)O"
    assert route.molecule_by_id[route.target_id].smiles == "CC(=O)Oc1ccccc1C(=O)O"


def test_predict_chemformer_returns_unavailable_without_demo_fallback(monkeypatch) -> None:
    def fail_post(*args, **kwargs):
        request = httpx.Request("POST", "http://127.0.0.1:8000/api/predict")
        raise httpx.ConnectError("offline", request=request)

    monkeypatch.setattr(chemformer_adapter.httpx, "post", fail_post)
    result = chemformer_adapter.predict_routes_with_chemformer("CCO")

    assert result.available is False
    assert result.used_fallback is False
    assert result.routes == []
    assert "调用失败" in result.status


def test_route_predict_dispatches_chemformer_and_serializes_metadata(monkeypatch) -> None:
    routes = parse_chemformer_response(SAMPLE_RESPONSE, max_routes=1)

    def fake_predict(*args, **kwargs):
        assert kwargs["max_routes"] == 5
        return ChemformerResult(routes=routes, available=True, used_fallback=False, status="ok")

    monkeypatch.setattr("services.workbench.predict_routes_with_chemformer", fake_predict)
    response = TestClient(app).post(
        "/route/predict",
        json={"smiles": SAMPLE_RESPONSE["input"], "max_routes": 5, "engine": "chemformer"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["used_fallback"] is False
    assert payload["engine"] == "chemformer"
    assert payload["candidates"][0]["metadata"]["prediction_type"] == "single_step"


def test_route_predict_rejects_unknown_engine() -> None:
    response = TestClient(app).post(
        "/route/predict",
        json={"smiles": "CCO", "engine": "unknown"},
    )
    assert response.status_code == 422
