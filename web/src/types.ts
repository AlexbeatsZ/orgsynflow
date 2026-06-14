import type { Edge, Node } from "@xyflow/react";

export type CellType = "chem" | "molecule" | "reaction" | "route";

export interface WorkspaceSummary {
  id: string;
  title: string;
  path: string;
  cell_count: number;
  updated_at?: string;
}

export interface Workspace {
  schema_version: number;
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  cells: WorkspaceCell[];
  route_candidate_sets: RouteCandidateSet[];
  jobs: unknown[];
}

export interface WorkspaceCell {
  id: string;
  type: CellType;
  title: string;
  created_at: string;
  updated_at: string;
  canvas: {
    nodes: Node[];
    edges: Edge[];
  };
  objects: {
    molecules?: MoleculeObject[];
    reactions?: ReactionObject[];
    routes?: RouteObject[];
  };
  results: Record<string, CachedResult>;
}

export interface MoleculeObject {
  id: string;
  label: string;
  smiles: string;
}

export interface ReactionObject {
  id: string;
  label: string;
  reaction_smiles: string;
  template?: string;
}

export interface RouteObject {
  id: string;
  label: string;
  route: unknown;
}

export interface RouteCandidateSet {
  id: string;
  target_smiles: string;
  status: string;
  created_at: string;
  candidates: unknown[];
}

export interface CachedResult {
  status: string;
  updated_at: string;
  payload: unknown;
}

export interface GaussianJob {
  job_id: string;
  workspace_id?: string;
  cell_id?: string;
  object_id?: string;
  status: string;
  created_at: string;
  started_at?: string;
  finished_at?: string;
  work_dir?: string;
  result?: unknown;
  error?: string;
}
