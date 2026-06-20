import json
from pathlib import Path
from types import SimpleNamespace

from adapters import aizynth_adapter
from adapters.aizynth_adapter import parse_aizynth_output


def test_parse_aizynth_tree_skips_reaction_nodes_and_keeps_synthesis_direction(tmp_path: Path) -> None:
    output = tmp_path / "routes.json"
    output.write_text(
        json.dumps(
            [
                {
                    "type": "mol",
                    "smiles": "CC(=O)OC(C)=O",
                    "is_chemical": True,
                    "children": [
                        {
                            "type": "reaction",
                            "is_reaction": True,
                            "smiles": "[mapped-target]>>[mapped-precursors]",
                            "metadata": {
                                "classification": "0.0 Unrecognized",
                                "policy_probability": 0.25,
                            },
                            "children": [
                                {"type": "mol", "smiles": "CC(=O)O", "in_stock": True},
                                {"type": "mol", "smiles": "CCC(=O)OC(C)=O", "in_stock": True},
                            ],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    route = parse_aizynth_output(output)[0]

    assert [molecule.smiles for molecule in route.molecules] == [
        "CC(=O)OC(C)=O",
        "CC(=O)O",
        "CCC(=O)OC(C)=O",
    ]
    assert all(">>" not in molecule.smiles for molecule in route.molecules)
    assert len(route.steps) == 1
    step = route.steps[0]
    assert step.product_id == route.target_id
    assert [route.molecule_by_id[item].smiles for item in step.precursor_ids] == [
        "CC(=O)O",
        "CCC(=O)OC(C)=O",
    ]
    assert step.reaction_smiles == "CC(=O)O.CCC(=O)OC(C)=O>>CC(=O)OC(C)=O"
    assert step.policy_score == 0.25


def test_wsl_prediction_creates_its_temp_directory(monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="stopped after command capture")

    monkeypatch.setattr(aizynth_adapter.subprocess, "run", fake_run)

    aizynth_adapter._predict_with_wsl_aizynth(
        aizynth_adapter.WSL_AIZYNTHCLI,
        "CCO",
        [],
        1,
        "/home/meta/data/aizynthfinder/config.yml",
        None,
        None,
    )

    assert commands[0][:3] == ["wsl", "-e", "bash"]
    assert commands[0][-1].startswith(f"mkdir -p {aizynth_adapter.WSL_TEMP_ROOT} && ")
