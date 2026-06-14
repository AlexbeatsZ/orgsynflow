import json
import subprocess
import sys
from pathlib import Path

from core.quantum import parse_quantum_log
from core.reaction_features import featurize_reaction
from core.reaction_mapping import map_reaction
from core.transition_state import plan_transition_state_search
from core.yield_predictor import estimate_reaction_yield_layered
from services.workbench import (
    calculate_molecule_descriptors,
    list_adapters,
    predict_molecule_properties,
)
from adapters.goodvibes_adapter import run_goodvibes
from adapters.xtb_adapter import run_crest_job, run_xtb_job


SAMPLE_REACTANT_LOG = """
 SCF Done:  E(RB3LYP) =  -100.000000     A.U. after   10 cycles
 Frequencies --  100.00   200.00   300.00
 Sum of electronic and thermal Free Energies=        -100.000000
 Normal termination of Gaussian 16
"""

SAMPLE_PRODUCT_LOG = """
 SCF Done:  E(RB3LYP) =  -100.020000     A.U. after   10 cycles
 Frequencies --  100.00   200.00   300.00
 Sum of electronic and thermal Free Energies=        -100.020000
 Normal termination of Gaussian 16
"""

SAMPLE_TS_LOG = """
 SCF Done:  E(RB3LYP) =  -99.970000     A.U. after   10 cycles
 Frequencies --  -521.40   120.00   340.50
 Sum of electronic and thermal Free Energies=        -99.970000
 Normal termination of Gaussian 16
"""


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "run_cli.py", *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_properties_and_descriptors_have_sources_and_fallbacks() -> None:
    properties = predict_molecule_properties("CCO", include_opera=True)
    descriptors = calculate_molecule_descriptors("CCO")

    assert properties["source"] == "rdkit+optional-opera"
    assert properties["rdkit"]["SMILES"] == "CCO"
    assert properties["opera"]["status"] in {"available", "unavailable", "failed"}
    assert descriptors["source"] == "rdkit+mordred_optional"
    assert "molecular_weight" in descriptors["descriptors"]


def test_optional_phase3_adapters_are_reported_and_fallback_cleanly(tmp_path: Path) -> None:
    names = {adapter["name"] for adapter in list_adapters()}

    assert {"cclib", "goodvibes", "rxnmapper", "drfp", "xtb", "crest"} <= names
    goodvibes = run_goodvibes([tmp_path / "missing.log"])
    xtb = run_xtb_job("0\n\n")
    crest = run_crest_job("0\n\n")

    assert goodvibes.status in {"unavailable", "available", "failed"}
    assert xtb.status in {"unavailable", "available", "failed"}
    assert crest.status in {"unavailable", "available", "failed"}


def test_reaction_mapping_and_ts_plan_are_explicitly_unverified_without_tools() -> None:
    mapping = map_reaction("CCO>>CC=O")
    plan = plan_transition_state_search("CCO>>CC=O")

    assert mapping.status in {"mapped", "unavailable", "failed"}
    assert mapping.method
    assert plan.validation_level == "未验证"
    assert "Opt=TS" in " ".join(plan.suggested_steps) or "opt=(ts" in plan.gaussian_ts_route.lower()


def test_layered_yield_and_features_do_not_claim_trained_model() -> None:
    estimate = estimate_reaction_yield_layered("CCO>>CC=O")
    features = featurize_reaction("CCO>>CC=O")

    assert estimate["method"] == "layered_heuristic_plus_optional_features"
    assert estimate["trained_model"]["available"] is False
    assert "heuristic" in estimate
    assert features.method in {"drfp", "hashed_reaction_smiles_fallback"}
    assert features.features


def test_quantum_parser_uses_cclib_or_gaussian_fallback() -> None:
    parsed = parse_quantum_log(SAMPLE_TS_LOG)

    assert parsed.method in {"cclib+gaussian_fallback", "gaussian_fallback"}
    assert parsed.gaussian_result.imaginary_frequency_count == 1
    assert parsed.gaussian_result.gibbs_free_energy_hartree == -99.97


def test_cli_phase2_commands_json() -> None:
    properties = run_cli("properties", "CCO", "--include-opera", "--format", "json")
    descriptors = run_cli("descriptors", "CCO", "--format", "json")

    assert properties.returncode == 0
    assert json.loads(properties.stdout)["rdkit"]["SMILES"] == "CCO"
    assert descriptors.returncode == 0
    assert "descriptors" in json.loads(descriptors.stdout)


def test_cli_phase3_commands_json(tmp_path: Path) -> None:
    reactant = tmp_path / "reactant.log"
    product = tmp_path / "product.log"
    ts = tmp_path / "ts.log"
    reactant.write_text(SAMPLE_REACTANT_LOG, encoding="utf-8")
    product.write_text(SAMPLE_PRODUCT_LOG, encoding="utf-8")
    ts.write_text(SAMPLE_TS_LOG, encoding="utf-8")

    reaction = "CCO>>CC=O"
    explain = run_cli("reaction-explain", reaction, "--format", "json")
    mapping = run_cli("reaction-map", reaction, "--format", "json")
    ts_plan = run_cli("ts-plan", reaction, "--format", "json")
    kinetics = run_cli(
        "kinetics",
        "--reactant-log",
        str(reactant),
        "--ts-log",
        str(ts),
        "--product-log",
        str(product),
        "--format",
        "json",
    )
    yield_result = run_cli("yield", reaction, "--format", "json")
    features = run_cli("reaction-features", reaction, "--format", "json")

    assert explain.returncode == 0
    assert json.loads(explain.stdout)["reaction_type"]
    assert mapping.returncode == 0
    assert json.loads(mapping.stdout)["method"]
    assert ts_plan.returncode == 0
    assert json.loads(ts_plan.stdout)["validation_level"] == "未验证"
    assert kinetics.returncode == 0
    assert json.loads(kinetics.stdout)["delta_g_activation_kj_mol"] > 0
    assert yield_result.returncode == 0
    assert json.loads(yield_result.stdout)["trained_model"]["available"] is False
    assert features.returncode == 0
    assert json.loads(features.stdout)["features"]
