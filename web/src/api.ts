import axios from "axios";
import type { CellType, ComputeStatus, GaussianJob, RouteCandidate, Workspace, WorkspaceCell, WorkspaceSummary } from "./types";

const http = axios.create({ baseURL: "/api" });

export async function listWorkspaces(): Promise<WorkspaceSummary[]> {
  const { data } = await http.get("/workspaces");
  return data.workspaces;
}

export async function createWorkspace(title: string): Promise<Workspace> {
  const { data } = await http.post("/workspaces", { title });
  return data;
}

export async function getWorkspace(id: string): Promise<Workspace> {
  const { data } = await http.get(`/workspaces/${id}`);
  return data;
}

export async function saveWorkspace(workspace: Workspace): Promise<Workspace> {
  const { data } = await http.put(`/workspaces/${workspace.id}`, { workspace });
  return data;
}

export async function addCell(
  workspaceId: string,
  cellType: CellType,
  title: string,
  objects: Record<string, unknown>,
): Promise<WorkspaceCell> {
  const { data } = await http.post(`/workspaces/${workspaceId}/cells`, {
    cell_type: cellType,
    title,
    objects,
  });
  return data;
}

export async function renderMoleculeSvg(smiles: string): Promise<string | null> {
  const { data } = await http.post("/chem/render/molecule-svg", { smiles });
  return data.svg ?? null;
}

export async function predictProperties(smiles: string, includeOpera: boolean): Promise<unknown> {
  const { data } = await http.post("/molecule/properties", { smiles, include_opera: includeOpera });
  return data;
}

export async function calculateDescriptors(smiles: string): Promise<unknown> {
  const { data } = await http.post("/molecule/descriptors", { smiles });
  return data;
}

export async function analyzeRoute(smiles: string, maxRoutes: number, useAizynth: boolean): Promise<{
  available: boolean;
  status: string;
  used_fallback?: boolean;
  target_smiles: string;
  candidates: RouteCandidate[];
  route_scores?: Record<string, unknown>;
  feasibility?: Record<string, unknown>;
}> {
  const { data } = await http.post("/route/predict", {
    smiles,
    max_routes: maxRoutes,
    aizynth_config: useAizynth ? undefined : undefined,
  });
  return data;
}

export async function validateReaction(reactionSmiles: string, template?: string): Promise<unknown> {
  const { data } = await http.post("/chem/validate/reaction", {
    reaction_smiles: reactionSmiles,
    template: template || null,
  });
  return data;
}

export async function explainReaction(reactionSmiles: string, template?: string): Promise<unknown> {
  const { data } = await http.post("/reaction/explain", {
    reaction_smiles: reactionSmiles,
    template: template || null,
  });
  return data;
}

export async function mapReaction(reactionSmiles: string): Promise<unknown> {
  const { data } = await http.post("/reaction/map", { reaction_smiles: reactionSmiles });
  return data;
}

export async function planTs(reactionSmiles: string): Promise<unknown> {
  const { data } = await http.post("/reaction/ts-plan", { reaction_smiles: reactionSmiles });
  return data;
}

export async function estimateYield(reactionSmiles: string, template?: string): Promise<unknown> {
  const { data } = await http.post("/reaction/yield", {
    reaction_smiles: reactionSmiles,
    template: template || null,
  });
  return data;
}

export async function reactionFeatures(reactionSmiles: string): Promise<unknown> {
  const { data } = await http.post("/reaction/features", { reaction_smiles: reactionSmiles });
  return data;
}

export async function makeGaussianInput(
  smiles: string,
  jobType = "opt freq",
  method = "B3LYP",
  basis = "6-31G(d)",
  charge = 0,
  multiplicity = 1,
): Promise<string> {
  const { data } = await http.post("/gaussian/input", {
    smiles,
    job_type: jobType,
    method,
    basis,
    charge,
    multiplicity,
  });
  return data.gjf;
}

export async function getComputeStatus(): Promise<ComputeStatus> {
  const { data } = await http.get("/compute/status");
  return data;
}

export async function runXtb(smiles: string, timeoutSeconds = 300): Promise<unknown> {
  const { data } = await http.post("/compute/xtb", {
    smiles,
    timeout_seconds: timeoutSeconds,
  });
  return data;
}

export async function runCrest(smiles: string, timeoutSeconds = 1800): Promise<unknown> {
  const { data } = await http.post("/compute/crest", {
    smiles,
    timeout_seconds: timeoutSeconds,
  });
  return data;
}

export async function submitGaussianJob(
  gjfText: string,
  workspaceId?: string,
  cellId?: string,
  objectId?: string,
): Promise<GaussianJob> {
  const { data } = await http.post("/jobs/gaussian", {
    gjf_text: gjfText,
    workspace_id: workspaceId,
    cell_id: cellId,
    object_id: objectId,
  });
  return data;
}

export async function listJobs(): Promise<GaussianJob[]> {
  const { data } = await http.get("/jobs");
  return data.jobs;
}
