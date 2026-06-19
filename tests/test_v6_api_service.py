from fastapi.testclient import TestClient

from api.main import app
from services.workbench import analyze_target, explain_single_reaction


def test_service_analyze_target_returns_all_feature_blocks() -> None:
    result = analyze_target("CC(=O)Oc1ccccc1C(=O)O", demo_target="Aspirin")

    assert result["target"]["SMILES"] == "CC(=O)Oc1ccccc1C(=O)O"
    assert result["routes"]
    assert result["route_scores"]
    assert result["feasibility"]
    assert result["report_markdown"]


def test_service_explain_single_reaction() -> None:
    result = explain_single_reaction(
        "Nc1ccc(O)cc1.CC(=O)OC(C)=O>>CC(=O)Nc1ccc(O)cc1",
        "Amine acetylation",
    )

    assert result["reaction_type"] == "酰化/乙酰化"


def test_api_health_and_analysis_endpoints() -> None:
    client = TestClient(app)

    assert client.get("/health").json()["status"] == "ok"
    response = client.post(
        "/analyze",
        json={"smiles": "CC(=O)Nc1ccc(O)cc1", "demo_target": "Paracetamol"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["routes"]
    assert payload["status"]


def test_api_exposes_gaussian_status() -> None:
    client = TestClient(app)

    response = client.get("/gaussian/status")

    assert response.status_code == 200
    assert "available" in response.json()


def test_api_exposes_compute_backend_status() -> None:
    client = TestClient(app)

    response = client.get("/compute/status")

    assert response.status_code == 200
    payload = response.json()
    assert {"gaussian", "xtb", "crest", "pyscf", "psi4"}.issubset(payload)
    assert "available" in payload["xtb"]


def test_api_route_predict_with_engines() -> None:
    client = TestClient(app)

    # Test aizynthfinder engine
    response_aizynth = client.post(
        "/route/predict",
        json={"smiles": "CCO", "max_routes": 1, "engine": "aizynthfinder"}
    )
    assert response_aizynth.status_code == 200
    payload_aizynth = response_aizynth.json()
    assert payload_aizynth["engine"] == "aizynthfinder"
    assert payload_aizynth["used_fallback"] is True

    # Test askcos engine
    response_askcos = client.post(
        "/route/predict",
        json={"smiles": "CCO", "max_routes": 1, "engine": "askcos"}
    )
    assert response_askcos.status_code == 200
    payload_askcos = response_askcos.json()
    assert payload_askcos["engine"] == "askcos"
    assert payload_askcos["used_fallback"] is True
    assert "ASKCOS Mock Route" in payload_askcos["candidates"][0]["title"]

