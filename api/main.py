from __future__ import annotations

from pydantic import BaseModel
from fastapi import FastAPI

from services.workbench import (
    analyze_profile_from_logs,
    analyze_target,
    calculate_molecule_descriptors,
    calculate_reaction_features,
    estimate_single_reaction_yield,
    explain_single_reaction,
    gaussian_status,
    make_gaussian_input,
    map_single_reaction,
    parse_gaussian_text,
    plan_single_transition_state,
    predict_molecule_properties,
    run_local_gaussian,
)


app = FastAPI(title="OrgSyn Flow API", version="0.6.0")


class AnalyzeRequest(BaseModel):
    smiles: str
    demo_target: str = "Aspirin"
    use_aizynth: bool = False
    max_routes: int = 3
    aizynth_config: str | None = None
    aizynth_stock: str | None = None
    aizynth_policy: str | None = None


class ReactionExplainRequest(BaseModel):
    reaction_smiles: str
    template: str | None = None


class MoleculePropertiesRequest(BaseModel):
    smiles: str
    include_opera: bool = False


class GaussianInputRequest(BaseModel):
    smiles: str
    title: str = "OrgSynFlow Gaussian job"
    method: str = "B3LYP"
    basis: str = "6-31G(d)"
    job_type: str = "opt freq"
    charge: int = 0
    multiplicity: int = 1


class GaussianParseRequest(BaseModel):
    text: str


class EnergyProfileRequest(BaseModel):
    reactant_log: str
    product_log: str
    ts_log: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "V6"}


@app.get("/gaussian/status")
def gaussian_available() -> dict[str, object]:
    return gaussian_status()


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, object]:
    return analyze_target(
        request.smiles,
        demo_target=request.demo_target,
        use_aizynth=request.use_aizynth,
        max_routes=request.max_routes,
        aizynth_config=request.aizynth_config,
        aizynth_stock=request.aizynth_stock,
        aizynth_policy=request.aizynth_policy,
    )


@app.post("/reaction/explain")
def reaction_explain(request: ReactionExplainRequest) -> dict[str, object]:
    return explain_single_reaction(request.reaction_smiles, request.template)


@app.post("/molecule/properties")
def molecule_properties(request: MoleculePropertiesRequest) -> dict[str, object]:
    return predict_molecule_properties(request.smiles, include_opera=request.include_opera)


@app.post("/molecule/descriptors")
def molecule_descriptors(request: MoleculePropertiesRequest) -> dict[str, object]:
    return calculate_molecule_descriptors(request.smiles)


@app.post("/reaction/map")
def reaction_map(request: ReactionExplainRequest) -> dict[str, object]:
    return map_single_reaction(request.reaction_smiles)


@app.post("/reaction/ts-plan")
def reaction_ts_plan(request: ReactionExplainRequest) -> dict[str, object]:
    return plan_single_transition_state(request.reaction_smiles)


@app.post("/reaction/yield")
def reaction_yield(request: ReactionExplainRequest) -> dict[str, object]:
    return estimate_single_reaction_yield(request.reaction_smiles, request.template)


@app.post("/reaction/features")
def reaction_features(request: ReactionExplainRequest) -> dict[str, object]:
    return calculate_reaction_features(request.reaction_smiles)


@app.post("/gaussian/input")
def gaussian_input(request: GaussianInputRequest) -> dict[str, str]:
    return {"gjf": make_gaussian_input(request.model_dump())}


@app.post("/gaussian/run")
def gaussian_run(request: GaussianInputRequest) -> dict[str, object]:
    return run_local_gaussian(request.model_dump())


@app.post("/gaussian/parse")
def gaussian_parse(request: GaussianParseRequest) -> dict[str, object]:
    return parse_gaussian_text(request.text)


@app.post("/kinetics/profile")
def kinetics_profile(request: EnergyProfileRequest) -> dict[str, object]:
    return analyze_profile_from_logs(request.reactant_log, request.product_log, request.ts_log)
