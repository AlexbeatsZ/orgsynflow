from fastapi.testclient import TestClient

from api.main import app
from core.workspaces import WORKSPACE_DIR


def test_workspace_crud_and_cell_creation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("core.workspaces.WORKSPACE_DIR", tmp_path)
    client = TestClient(app)

    created = client.post("/workspaces", json={"title": "Notebook Demo"}).json()
    assert created["id"] == "notebook-demo"

    listed = client.get("/workspaces").json()
    assert listed["workspaces"][0]["id"] == created["id"]

    cell = client.post(
        f"/workspaces/{created['id']}/cells",
        json={
            "cell_type": "molecule",
            "title": "Ethanol",
            "objects": {"molecules": [{"id": "mol-1", "smiles": "CCO"}]},
        },
    ).json()
    assert cell["type"] == "molecule"

    loaded = client.get(f"/workspaces/{created['id']}").json()
    assert loaded["cells"][0]["objects"]["molecules"][0]["smiles"] == "CCO"

    task_record = {
        "task_id": "molecule-properties",
        "task_label": "计算分子性质（RDKit + OPERA）",
        "object_id": "mol-1",
        "object_kind": "molecule",
        "engine": "RDKit + OPERA",
        "status": "running",
        "updated_at": "2026-06-19T00:00:00+00:00",
        "payload": None,
    }
    result_key = "molecule:mol-1:molecule-properties"
    stored = client.put(
        f"/workspaces/{created['id']}/cells/{cell['id']}/results/{result_key}",
        json={"record": task_record},
    ).json()
    assert stored == task_record

    loaded = client.get(f"/workspaces/{created['id']}").json()
    assert loaded["cells"][0]["results"][result_key]["status"] == "running"
    assert loaded["cells"][0]["objects"]["molecules"][0]["smiles"] == "CCO"

    saved = client.put(f"/workspaces/{created['id']}", json={"workspace": {**loaded, "title": "Renamed"}}).json()
    assert saved["title"] == "Renamed"

    deleted = client.delete(f"/workspaces/{created['id']}").json()
    assert deleted["deleted"] is True
    assert not (WORKSPACE_DIR / f"{created['id']}.json").exists()


def test_reaction_validation_reports_balance_and_feasibility() -> None:
    client = TestClient(app)

    valid = client.post("/chem/validate/reaction", json={"reaction_smiles": "CCO>>CC=O"}).json()

    assert valid["valid"] is True
    assert valid["element_balance"]["available"] is True
    assert valid["feasibility"]["method"] == "layered_heuristic_plus_optional_features"

    invalid = client.post("/chem/validate/reaction", json={"reaction_smiles": "CCO"}).json()
    assert invalid["valid"] is False
    assert invalid["errors"]


def test_molecule_svg_and_gaussian_job_submission() -> None:
    client = TestClient(app)

    svg = client.post("/chem/render/molecule-svg", json={"smiles": "CCO"}).json()
    assert svg["available"] is True
    assert "<svg" in svg["svg"]

    formula_svg = client.post("/chem/render/molecule-svg", json={"smiles": "CO2.H2O"}).json()
    assert formula_svg["available"] is True
    assert "<svg" in formula_svg["svg"]
    assert "component structures: CO2, H2O" in formula_svg["svg"]
    assert "formula notation" not in formula_svg["svg"]

    unresolved_formula_svg = client.post("/chem/render/molecule-svg", json={"smiles": "CuSO4.5H2O"}).json()
    assert unresolved_formula_svg["available"] is True
    assert "formula notation" in unresolved_formula_svg["svg"]

    job = client.post(
        "/jobs/gaussian",
        json={"gjf_text": "%chk=test.chk\n# opt freq\n\nTest\n\n0 1\n\n"},
    ).json()
    assert job["status"] in {"queued", "running", "failed", "succeeded"}
    assert client.get(f"/jobs/{job['job_id']}").status_code == 200
    assert "jobs" in client.get("/jobs").json()


def test_route_predict_returns_visible_fallback_candidates_without_config() -> None:
    client = TestClient(app)

    response = client.post("/route/predict", json={"smiles": "CCO", "max_routes": 2}).json()

    assert response["available"] is False
    assert response["used_fallback"] is True
    assert response["candidates"]
    assert "routes" not in response
