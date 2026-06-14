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

    job = client.post(
        "/jobs/gaussian",
        json={"gjf_text": "%chk=test.chk\n# opt freq\n\nTest\n\n0 1\n\n"},
    ).json()
    assert job["status"] in {"queued", "running", "failed", "succeeded"}
    assert client.get(f"/jobs/{job['job_id']}").status_code == 200
    assert "jobs" in client.get("/jobs").json()


def test_route_predict_requires_real_aizynth_config() -> None:
    client = TestClient(app)

    response = client.post("/route/predict", json={"smiles": "CCO", "max_routes": 2}).json()

    assert response["available"] is False
    assert response["status"] == "disabled"
    assert response["candidates"] == []
