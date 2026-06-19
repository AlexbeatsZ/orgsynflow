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
  route: RouteCandidate;
}

export interface RouteCandidateSet {
  id: string;
  target_smiles: string;
  status: string;
  created_at: string;
  candidates: RouteCandidate[];
  route_scores?: Record<string, unknown>;
  feasibility?: Record<string, unknown>;
  used_fallback?: boolean;
}

export interface RouteCandidate {
  id: string;
  title: string;
  target_id: string;
  source: string;
  depth: number;
  precursor_count: number;
  stock_count: number;
  molecules: Array<{ id: string; name: string; smiles: string; in_stock?: boolean }>;
  steps: Array<{
    id: string;
    product_id: string;
    precursor_ids: string[];
    reaction_smiles?: string | null;
    policy_score?: number | null;
    template?: string | null;
  }>;
  layout?: {
    nodes: Record<string, { id: string; label: string; x: number; y: number; in_stock: boolean }>;
    edges: Array<{ source_id: string; target_id: string; label: string }>;
  };
}

export interface CachedResult {
  status: string;
  updated_at: string;
  payload: unknown;
  task_id?: string;
  task_label?: string;
  object_id?: string;
  object_kind?: "cell" | "molecule" | "reaction";
  object_label?: string;
  engine?: string;
  error?: string;
  config?: Record<string, unknown>;
  job_id?: string;
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

export interface ComputeBackendStatus {
  name?: string;
  available: boolean;
  executable?: string | null;
  source?: string | null;
  metadata?: Record<string, any> | null;
}

export type ComputeStatus = Record<string, ComputeBackendStatus>;

