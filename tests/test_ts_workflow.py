from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from core.gaussian import parse_gaussian_log
from core.ts_workflow import (
    TsWorkflowManager,
    build_refinement_grid,
    build_scan_grid,
    extract_mapped_bond_changes,
    infer_charge_and_multiplicity,
    irc_endpoints_match,
    rank_saddle_candidates,
    generate_candidate_geometries,
    set_xyz_distances,
    suggest_scan_coordinates,
)


def test_mapped_sn2_produces_forming_and_breaking_coordinates() -> None:
    changes = extract_mapped_bond_changes(
        "[CH3:1][Br:2].[Cl-:3]",
        "[CH3:1][Cl:3].[Br-:2]",
    )
    assert {change["kind"] for change in changes} == {"formed", "broken"}
    coordinates = suggest_scan_coordinates(changes)
    assert len(coordinates) == 2
    assert all(coordinate["atom1"] > 0 and coordinate["atom2"] > 0 for coordinate in coordinates)
    broken = next(coordinate for coordinate in coordinates if coordinate["kind"] == "broken")
    assert broken["start"] > 1.8  # C-Br covalent-radius estimate, not a hard-coded 1.5 Å.
    assert infer_charge_and_multiplicity("CBr.[Cl-]")[:2] == (-1, 1)


def test_scan_geometry_is_moved_to_requested_distances() -> None:
    xyz = "3\nx\nC 0 0 0\nBr 1.95 0 0\nCl 3.5 0 0\n"
    adjusted = set_xyz_distances(
        xyz,
        [{"atom1": 1, "atom2": 2}, {"atom1": 1, "atom2": 3}],
        [1.96, 3.0],
    )
    lines = adjusted.splitlines()[2:]
    assert float(lines[1].split()[1]) == 1.96
    assert float(lines[2].split()[1]) == 3.0


def test_scan_grid_and_refinement_respect_planned_budget() -> None:
    coordinates = [
        {"atom1": 1, "atom2": 2, "kind": "formed", "start": 3.0, "end": 1.5},
        {"atom1": 1, "atom2": 3, "kind": "broken", "start": 1.5, "end": 3.0},
    ]
    grid = build_scan_grid(coordinates)
    assert len(grid) == 25
    for point in grid:
        point["status"] = "succeeded"
        point["energy_hartree"] = -100.0 + 0.02 * min(point["indices"][0], point["indices"][1])
        point["final_xyz"] = "3\npoint\nC 0 0 0\nBr 1.5 0 0\nCl 3 0 0\n"
    ranked = rank_saddle_candidates(grid, coordinates)
    assert ranked
    refinement = build_refinement_grid(coordinates, ranked[0], grid)
    assert len(grid) + len(refinement) <= 40


def test_one_coordinate_uses_nine_points() -> None:
    grid = build_scan_grid([{"atom1": 1, "atom2": 2, "kind": "formed", "start": 3.0, "end": 1.5}])
    assert len(grid) == 9
    assert grid[0]["values"] == [3.0]
    assert grid[-1]["values"] == [1.5]


def test_candidate_generation_separates_disconnected_fragments() -> None:
    candidates = generate_candidate_geometries("CBr.[Cl-]", count=2)

    assert candidates
    assert all(candidate["minimum_interfragment_distance"] >= 1.25 for candidate in candidates)


def test_frequency_parser_extracts_mode_displacements_and_final_geometry() -> None:
    log = """
 Frequencies --  -321.0000   110.0000   220.0000
 Red. masses --     1.0000     1.0000     1.0000
 Atom  AN      X      Y      Z        X      Y      Z        X      Y      Z
   1    6     0.10   0.00   0.00     0.00   0.00   0.00     0.00   0.00   0.00
   2   17    -0.10   0.00   0.00     0.00   0.00   0.00     0.00   0.00   0.00

 Standard orientation:
 ---------------------------------------------------------------------
 Center     Atomic      Atomic             Coordinates (Angstroms)
 Number     Number       Type             X           Y           Z
 ---------------------------------------------------------------------
      1          6           0        0.000000    0.000000    0.000000
      2         17           0        1.800000    0.000000    0.000000
 ---------------------------------------------------------------------
 SCF Done:  E(RB3LYP) =  -100.123456
 Normal termination of Gaussian 16
 """
    result = parse_gaussian_log(log)
    assert result.frequencies_cm1[0] == -321.0
    assert result.vibration_modes[0]["displacements"][0] == [0.1, 0.0, 0.0]
    assert result.final_coordinates_xyz is not None
    assert "Cl" in result.final_coordinates_xyz


def test_irc_endpoint_matching_accepts_reversed_directions() -> None:
    reactant = "3\nr\nC 0 0 0\nBr 1.5 0 0\nCl 3.2 0 0\n"
    product = "3\np\nC 0 0 0\nBr 3.2 0 0\nCl 1.5 0 0\n"
    coordinates = [
        {"atom1": 1, "atom2": 3, "kind": "formed"},
        {"atom1": 1, "atom2": 2, "kind": "broken"},
    ]
    assert irc_endpoints_match(product, reactant, coordinates) is True


def test_recovery_preserves_manifest_and_marks_active_workflow_paused(tmp_path: Path) -> None:
    manager = TsWorkflowManager(tmp_path)
    manager._save({"workflow_id": "ts-recovery1", "status": "scanning", "stage": "scanning", "created_at": "2026-01-01", "warnings": []})
    manager.recover()
    recovered = manager.get("ts-recovery1")
    assert recovered is not None
    assert recovered["status"] == "paused"
    assert recovered["stage"] == "interrupted"


def test_ts_workflow_api_contract(monkeypatch) -> None:
    prepared = {
        "workflow_id": "ts-api1",
        "reaction_smiles": "CBr.[Cl-]>>CCl.[Br-]",
        "status": "preparing",
        "stage": "preparing",
        "validation_level": "未验证",
        "coordinates": [],
        "candidates": [],
        "grid_points": [],
        "config": {},
    }
    monkeypatch.setattr("api.main.ts_workflow_manager.create", lambda *args, **kwargs: prepared)
    monkeypatch.setattr("api.main.ts_workflow_manager.get", lambda workflow_id: prepared if workflow_id == "ts-api1" else None)
    client = TestClient(app)
    response = client.post("/ts-workflows", json={"reaction_smiles": prepared["reaction_smiles"]})
    assert response.status_code == 200
    assert response.json()["workflow_id"] == "ts-api1"
    assert client.get("/ts-workflows/ts-api1").status_code == 200
    assert client.get("/ts-workflows/missing").status_code == 404
