from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException

from services.workbench import (
    analyze_profile_from_logs,
    analyze_target,
    calculate_molecule_descriptors,
    calculate_reaction_features,
    check_feasibility,
    compute_backend_status,
    estimate_single_reaction_yield,
    explain_single_reaction,
    gaussian_status,
    make_gaussian_input,
    map_single_reaction,
    parse_gaussian_text,
    plan_single_transition_state,
    predict_molecule_properties,
    run_crest_for_smiles,
    run_local_gaussian,
    run_xtb_for_smiles,
)
from core.job_queue import crest_manager, gaussian_job_queue
from core.molecule import molecule_svg
from core.reaction_mapping import mapped_atom_coordinates
from core.reaction_validation import validate_reaction_smiles
from core.workspaces import (
    add_cell,
    create_workspace,
    delete_workspace,
    get_workspace,
    list_workspaces,
    save_workspace,
    update_result,
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


class RoutePredictRequest(BaseModel):
    smiles: str
    max_routes: int = Field(3, ge=1, le=20)
    engine: Literal["aizynthfinder", "askcos", "chemformer"] = "aizynthfinder"
    aizynth_config: str | None = None
    aizynth_stock: str | None = None
    aizynth_policy: str | None = None
    askcos_url: str | None = None
    chemformer_url: str | None = None


class ReactionExplainRequest(BaseModel):
    reaction_smiles: str
    template: str | None = None
    use_llm: bool = False


class FeasibilityCheckRequest(BaseModel):
    reaction_smiles: str
    template: str | None = None
    use_llm: bool = False


class MappedCoordinatesRequest(BaseModel):
    mapped_reaction_smiles: str


class ReactionYieldRequest(ReactionExplainRequest):
    use_llm_fallback: bool = True


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


class WorkspaceCreateRequest(BaseModel):
    title: str = "Untitled workspace"


class WorkspaceSaveRequest(BaseModel):
    workspace: dict[str, object]


class CellCreateRequest(BaseModel):
    cell_type: str
    title: str
    objects: dict[str, object] = {}


class TaskResultRequest(BaseModel):
    record: dict[str, object]


class MoleculeSvgRequest(BaseModel):
    smiles: str
    width: int = 320
    height: int = 220


class ReactionValidationRequest(BaseModel):
    reaction_smiles: str
    template: str | None = None


class GaussianJobRequest(BaseModel):
    gjf_text: str
    workspace_id: str | None = None
    cell_id: str | None = None
    object_id: str | None = None


class SemiempiricalRunRequest(BaseModel):
    smiles: str
    timeout_seconds: int | None = None


class CoordinatesRequest(BaseModel):
    smiles: str


class TsWorkflowCreateRequest(BaseModel):
    reaction_smiles: str
    workspace_id: str | None = None
    cell_id: str | None = None
    reaction_id: str | None = None
    agents: list[str] | None = None


class TsSuggestConfigRequest(BaseModel):
    reaction_smiles: str
    coordinates: list[dict[str, Any]]

class TsWorkflowConfirmRequest(BaseModel):
    candidate_id: str
    coordinates: list[dict[str, object]]
    config: dict[str, object]


class TsWorkflowActionRequest(BaseModel):
    action: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "V6"}


@app.post("/chem/molecule-coordinates")
def molecule_coordinates(request: CoordinatesRequest) -> dict[str, object]:
    reactants_side = request.smiles.split(">>")[0]
    components = re.split(r"\s+\+\s+|\.", reactants_side)
    results = []
    for comp in components:
        comp = comp.strip()
        if not comp:
            continue
        try:
            from core.gaussian import coordinates_from_smiles
            coord_str = coordinates_from_smiles(comp)
            atoms = []
            for line in coord_str.splitlines():
                parts = line.split()
                if len(parts) == 4:
                    atoms.append({
                        "element": parts[0],
                        "x": float(parts[1]),
                        "y": float(parts[2]),
                        "z": float(parts[3]),
                    })
            results.append({
                "smiles": comp,
                "atoms": atoms
            })
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return {"components": results}




@app.get("/workspaces")
def workspaces_list() -> dict[str, object]:
    return {"workspaces": list_workspaces()}


@app.post("/workspaces")
def workspaces_create(request: WorkspaceCreateRequest) -> dict[str, object]:
    return create_workspace(request.title)


@app.get("/workspaces/{workspace_id}")
def workspaces_get(workspace_id: str) -> dict[str, object]:
    try:
        return get_workspace(workspace_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/workspaces/{workspace_id}")
def workspaces_save(workspace_id: str, request: WorkspaceSaveRequest) -> dict[str, object]:
    try:
        return save_workspace(workspace_id, request.workspace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/workspaces/{workspace_id}")
def workspaces_delete(workspace_id: str) -> dict[str, object]:
    try:
        return delete_workspace(workspace_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/workspaces/{workspace_id}/cells")
def workspaces_add_cell(workspace_id: str, request: CellCreateRequest) -> dict[str, object]:
    try:
        return add_cell(workspace_id, request.cell_type, request.title, request.objects)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/workspaces/{workspace_id}/cells/{cell_id}/results/{result_key}")
def workspaces_update_result(
    workspace_id: str,
    cell_id: str,
    result_key: str,
    request: TaskResultRequest,
) -> dict[str, object]:
    try:
        return update_result(workspace_id, cell_id, result_key, request.record)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/chem/render/molecule-svg")
def render_molecule_svg(request: MoleculeSvgRequest) -> dict[str, object]:
    svg = molecule_svg(request.smiles, size=(request.width, request.height))
    return {"available": svg is not None, "svg": svg}


@app.post("/chem/validate/reaction")
def validate_reaction(request: ReactionValidationRequest) -> dict[str, object]:
    return validate_reaction_smiles(request.reaction_smiles, request.template)


@app.get("/gaussian/status")
def gaussian_available() -> dict[str, object]:
    return gaussian_status()


@app.get("/compute/status")
def compute_status() -> dict[str, object]:
    return compute_backend_status()


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


@app.post("/route/predict")
def route_predict(request: RoutePredictRequest) -> dict[str, object]:
    result = analyze_target(
        request.smiles,
        use_aizynth=(request.engine == "aizynthfinder"),
        engine=request.engine,
        max_routes=request.max_routes,
        aizynth_config=request.aizynth_config,
        aizynth_stock=request.aizynth_stock,
        aizynth_policy=request.aizynth_policy,
        askcos_url=request.askcos_url,
        chemformer_url=request.chemformer_url,
    )
    return {
        "available": bool(result.get("available")),
        "status": result["status"],
        "used_fallback": result.get("used_fallback", False),
        "target_smiles": request.smiles,
        "candidates": result["routes"],
        "route_scores": result["route_scores"],
        "feasibility": result["feasibility"],
        "engine": request.engine,
    }


@app.post("/reaction/explain")
def reaction_explain(request: ReactionExplainRequest) -> dict[str, object]:
    return explain_single_reaction(request.reaction_smiles, request.template, use_llm=request.use_llm)


@app.post("/reaction/feasibility-check")
def reaction_feasibility_check(request: FeasibilityCheckRequest) -> dict[str, object]:
    return check_feasibility(request.reaction_smiles, request.template, use_llm=request.use_llm)


@app.post("/reaction/mapping-coordinates")
def reaction_mapping_coordinates(request: MappedCoordinatesRequest) -> dict[str, object]:
    return mapped_atom_coordinates(request.mapped_reaction_smiles)


@app.post("/molecule/properties")
def molecule_properties(request: MoleculePropertiesRequest) -> dict[str, object]:
    return predict_molecule_properties(request.smiles, include_opera=request.include_opera)


@app.post("/molecule/descriptors")
def molecule_descriptors(request: MoleculePropertiesRequest) -> dict[str, object]:
    return calculate_molecule_descriptors(request.smiles)


@app.post("/reaction/map")
def reaction_map(request: ReactionExplainRequest) -> dict[str, object]:
    return map_single_reaction(request.reaction_smiles, use_llm=request.use_llm)


@app.post("/reaction/ts-plan")
def reaction_ts_plan(request: ReactionExplainRequest) -> dict[str, object]:
    return plan_single_transition_state(request.reaction_smiles)


@app.post("/reaction/yield")
def reaction_yield(request: ReactionYieldRequest) -> dict[str, object]:
    return estimate_single_reaction_yield(
        request.reaction_smiles,
        request.template,
        use_llm_fallback=request.use_llm_fallback,
    )


@app.post("/reaction/features")
def reaction_features(request: ReactionExplainRequest) -> dict[str, object]:
    return calculate_reaction_features(request.reaction_smiles)


@app.post("/gaussian/input")
def gaussian_input(request: GaussianInputRequest) -> dict[str, str]:
    return {"gjf": make_gaussian_input(request.model_dump())}


@app.post("/gaussian/run")
def gaussian_run(request: GaussianInputRequest) -> dict[str, object]:
    return run_local_gaussian(request.model_dump())


@app.post("/compute/xtb")
def compute_xtb(request: SemiempiricalRunRequest) -> dict[str, object]:
    return run_xtb_for_smiles(request.smiles, timeout_seconds=request.timeout_seconds or 300)


@app.post("/compute/crest")
def compute_crest(request: SemiempiricalRunRequest) -> dict[str, object]:
    from core.gaussian import coordinates_from_smiles
    coordinates = coordinates_from_smiles(request.smiles)
    coordinate_lines = [line for line in coordinates.splitlines() if line.strip()]
    xyz = "\n".join([str(len(coordinate_lines)), request.smiles, *coordinate_lines, ""])
    return crest_manager.submit(xyz, timeout_seconds=request.timeout_seconds or 1800)


@app.get("/compute/crest/{job_id}")
def compute_crest_status(job_id: str) -> dict[str, object]:
    job = crest_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"CREST job not found: {job_id}")
    return job


@app.post("/compute/crest/{job_id}/cancel")
def compute_crest_cancel(job_id: str) -> dict[str, object]:
    job = crest_manager.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"CREST job not found: {job_id}")
    return job


@app.post("/jobs/gaussian")
def submit_gaussian_job(request: GaussianJobRequest) -> dict[str, object]:
    return gaussian_job_queue.submit(
        request.gjf_text,
        workspace_id=request.workspace_id,
        cell_id=request.cell_id,
        object_id=request.object_id,
    )


@app.get("/jobs")
def list_jobs() -> dict[str, object]:
    jobs = [*gaussian_job_queue.list(), *crest_manager.list()]
    jobs.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return {"jobs": jobs}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, object]:
    job = gaussian_job_queue.get(job_id) or crest_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job


@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, object]:
    job = gaussian_job_queue.cancel(job_id) or crest_manager.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job


@app.post("/gaussian/parse")
def gaussian_parse(request: GaussianParseRequest) -> dict[str, object]:
    return parse_gaussian_text(request.text)


@app.post("/kinetics/profile")
def kinetics_profile(request: EnergyProfileRequest) -> dict[str, object]:
    return analyze_profile_from_logs(request.reactant_log, request.product_log, request.ts_log)


from core.ts_workflow import TsWorkflowManager
ts_manager = TsWorkflowManager()
ts_workflow_manager = ts_manager

@app.post("/ts/workflow")
def ts_workflow_create(request: TsWorkflowCreateRequest) -> dict[str, object]:
    return ts_workflow_manager.create(
        reaction_smiles=request.reaction_smiles,
        workspace_id=request.workspace_id,
        cell_id=request.cell_id,
        reaction_id=request.reaction_id,
        included_agents=request.agents,
    )

@app.post("/ts-workflows")
def ts_workflow_create_legacy(request: TsWorkflowCreateRequest) -> dict[str, object]:
    return ts_workflow_create(request)

@app.get("/ts/workflow/{workflow_id}")
def ts_workflow_get(workflow_id: str) -> dict[str, object]:
    workflow = ts_workflow_manager.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow

@app.get("/ts-workflows/{workflow_id}")
def ts_workflow_get_legacy(workflow_id: str) -> dict[str, object]:
    return ts_workflow_get(workflow_id)

@app.post("/ts/suggest-config")
def ts_suggest_config(request: TsSuggestConfigRequest) -> dict[str, object]:
    from core.ts_workflow import suggest_ts_config_with_deepseek
    return suggest_ts_config_with_deepseek(request.reaction_smiles, request.coordinates)

@app.post("/ts/workflow/{workflow_id}/confirm")
def ts_workflow_confirm(workflow_id: str, request: TsWorkflowConfirmRequest) -> dict[str, object]:
    try:
        return ts_workflow_manager.confirm(workflow_id, request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/ts/workflow/{workflow_id}/action")
def ts_workflow_action(workflow_id: str, request: TsWorkflowActionRequest) -> dict[str, object]:
    try:
        action = request.action
        if action == "pause":
            return ts_workflow_manager.pause(workflow_id)
        elif action in ["resume", "retry"]:
            return ts_workflow_manager.resume(workflow_id)
        elif action == "cancel":
            return ts_workflow_manager.cancel(workflow_id)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
