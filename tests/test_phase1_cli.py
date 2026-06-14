import json
import subprocess
import sys

from services.workbench import list_adapters, summarize_target_molecule


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "run_cli.py", *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_list_adapters_reports_optional_tools_without_crashing() -> None:
    adapters = list_adapters()
    names = {adapter["name"] for adapter in adapters}

    assert {"rdkit", "aizynthfinder", "gaussian", "opera", "xtb", "crest"} <= names
    for adapter in adapters:
        assert "available" in adapter
        assert adapter["status"] in {"available", "unavailable"}
        assert adapter["source"]


def test_summarize_target_molecule_returns_display_dict() -> None:
    summary = summarize_target_molecule("CCO")

    assert summary["SMILES"] == "CCO"
    assert "MW" in summary


def test_cli_health_json() -> None:
    completed = run_cli("health", "--format", "json")

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"
    assert payload["source"] == "orgsynflow-cli"


def test_cli_adapters_text_includes_unavailable_optional_tools() -> None:
    completed = run_cli("adapters", "--format", "json")

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    display_names = {adapter["display_name"] for adapter in payload["adapters"]}
    assert "OPERA QSAR" in display_names
    assert "xTB" in display_names


def test_cli_molecule_and_route_smoke() -> None:
    molecule = run_cli("molecule", "CCO", "--format", "json")
    route = run_cli("route", "CC(=O)Oc1ccccc1C(=O)O", "--max-routes", "1", "--format", "json")

    assert molecule.returncode == 0
    assert json.loads(molecule.stdout)["molecule"]["SMILES"] == "CCO"
    assert route.returncode == 0
    route_payload = json.loads(route.stdout)
    assert route_payload["routes"]
    assert route_payload["status"]


def test_cli_gaussian_status_and_input_smoke() -> None:
    status = run_cli("gaussian-status", "--format", "json")
    gjf = run_cli("gaussian-input", "CCO", "--job-type", "opt freq", "--format", "json")

    assert status.returncode == 0
    assert "available" in json.loads(status.stdout)
    assert gjf.returncode == 0
    assert "# opt freq B3LYP/6-31G(d)" in json.loads(gjf.stdout)["gjf"]
