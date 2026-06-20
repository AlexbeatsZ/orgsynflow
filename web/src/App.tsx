import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BaseEdge,
  ConnectionMode,
  Controls,
  Handle,
  Position,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
  MarkerType,
} from "@xyflow/react";
import {
  Atom,
  BookOpen,
  Boxes,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Cpu,
  History,
  Link2,
  Trash2,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  RotateCcw,
  Save,
  XCircle,
} from "lucide-react";
import {
  addCell,
  analyzeRoute,
  calculateDescriptors,
  createWorkspace,
  estimateYield,
  explainReaction,
  getComputeStatus,
  getWorkspace,
  listJobs,
  listWorkspaces,
  makeGaussianInput,
  mapReaction,
  planTs,
  predictProperties,
  reactionFeatures,
  renderMoleculeSvg,
  runCrest,
  runXtb,
  saveWorkspace,
  submitGaussianJob,
  updateTaskResult,
  validateReaction,
  getMoleculeCoordinates,
} from "./api";
import type {
  CachedResult,
  CellType,
  ComputeStatus,
  GaussianJob,
  MoleculeComponent,
  MoleculeObject,
  ReactionObject,
  RouteCandidate,
  RouteCandidateSet,
  Workspace,
  WorkspaceCell,
  WorkspaceSummary,
} from "./types";

type SelectedObject =
  | { kind: "cell"; cell: WorkspaceCell }
  | { kind: "molecule"; cell: WorkspaceCell; molecule: MoleculeObject; component?: MoleculeComponent }
  | { kind: "reaction"; cell: WorkspaceCell; reaction: ReactionObject }
  | null;

type ModalState =
  | { kind: "result"; title: string; result: unknown; onRecompute?: () => void; onConfigure?: () => void }
  | { kind: "task-error"; title: string; record: CachedResult; onRetry?: () => void; onConfigure?: () => void }
  | { kind: "backend"; status: ComputeStatus | null }
  | { kind: "jobs"; jobs: GaussianJob[]; refresh: () => Promise<void> }
  | { kind: "routes"; sets: RouteCandidateSet[]; workspace: Workspace; selected: SelectedObject; onSave: (workspace?: Workspace | null) => Promise<void>; onRecompute?: () => void }
  | { kind: "engine-select"; onSelect: (engine: string) => void; backendStatus: ComputeStatus | null }
  | null;

type ExtractedGeometry = {
  xyz: string;
  atomCount: number;
};

type RunTask = (
  definition: TaskDefinition,
  task: () => Promise<unknown>,
  options?: {
    openResult?: boolean;
    title?: string;
    config?: Record<string, unknown>;
    onConfigure?: () => void;
    statusFromResult?: (result: unknown) => CachedResult["status"];
  },
) => Promise<unknown | null>;

interface TaskDefinition {
  id: string;
  label: string;
  objectId: string;
  objectKind: "cell" | "molecule" | "reaction";
  objectLabel: string;
  cellId: string;
  engine?: string;
}

const examples = {
  molecule: "CCO",
  reaction: "CCO>>CC=O",
  target: "CC(=O)Oc1ccccc1C(=O)O",
};

type MoleculeCoordinates = {
  smiles: string;
  atoms: Array<{ element: string; x: number; y: number; z: number }>;
};

type TransitionStatePlanResult = {
  reaction_smiles: string;
  status: string;
  validation_level: string;
  gaussian_scan_route: string;
  gaussian_ts_route: string;
  gaussian_irc_route: string;
  suggested_steps: string[];
  warnings: string[];
};

type Point = { x: number; y: number };
type Side = "top" | "right" | "bottom" | "left";
type NodeRect = { id: string; left: number; right: number; top: number; bottom: number };
type RouteEndpointOverrides = {
  sourceRect?: NodeRect;
  targetRect?: NodeRect;
  obstacles?: NodeRect[];
};

const moleculeHandles = [
  { id: "top", position: Position.Top, style: { left: "50%", top: "-8px" } },
  { id: "top-a", position: Position.Top, style: { left: "34%", top: "-8px" } },
  { id: "top-b", position: Position.Top, style: { left: "66%", top: "-8px" } },
  { id: "right", position: Position.Right, style: { top: "50%", right: "-8px" } },
  { id: "right-a", position: Position.Right, style: { top: "30%", right: "-8px" } },
  { id: "right-b", position: Position.Right, style: { top: "70%", right: "-8px" } },
  { id: "bottom", position: Position.Bottom, style: { left: "50%", bottom: "-8px" } },
  { id: "bottom-a", position: Position.Bottom, style: { left: "34%", bottom: "-8px" } },
  { id: "bottom-b", position: Position.Bottom, style: { left: "66%", bottom: "-8px" } },
  { id: "left", position: Position.Left, style: { top: "50%", left: "-8px" } },
  { id: "left-a", position: Position.Left, style: { top: "30%", left: "-8px" } },
  { id: "left-b", position: Position.Left, style: { top: "70%", left: "-8px" } },
];

export function App() {
  const [summaries, setSummaries] = useState<WorkspaceSummary[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const workspaceRef = useRef<Workspace | null>(null);
  const [activeCellId, setActiveCellId] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedObject>(null);
  const [, setResult] = useState<unknown>(null);
  const [jobs, setJobs] = useState<GaussianJob[]>([]);
  const [computeStatus, setComputeStatus] = useState<ComputeStatus | null>(null);
  const [modal, setModal] = useState<ModalState>(null);
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  const [unitRailOpen, setUnitRailOpen] = useState(true);

  useEffect(() => {
    workspaceRef.current = workspace;
  }, [workspace]);

  useEffect(() => {
    refreshWorkspaces();
    refreshJobs();
    refreshComputeStatus();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(refreshJobs, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(refreshComputeStatus, 30000);
    return () => window.clearInterval(timer);
  }, []);

  async function refreshWorkspaces() {
    const items = await listWorkspaces();
    setSummaries(items);
    if (!workspaceRef.current && items[0]) {
      await loadWorkspace(items[0].id);
    }
  }

  async function refreshJobs() {
    const nextJobs = await listJobs();
    setJobs(nextJobs);
    await syncGaussianTaskRecords(nextJobs);
  }

  async function loadWorkspace(id: string) {
    const [loaded, currentJobs] = await Promise.all([getWorkspace(id), listJobs()]);
    const recovered = await recoverInterruptedTasks(loaded, currentJobs);
    workspaceRef.current = recovered;
    setWorkspace(recovered);
    setJobs(currentJobs);
    setActiveCellId(recovered.cells[0]?.id ?? null);
    setSelected(null);
    setResult(null);
  }

  async function recoverInterruptedTasks(loaded: Workspace, currentJobs: GaussianJob[]): Promise<Workspace> {
    let next = loaded;
    for (const cell of loaded.cells) {
      for (const [key, record] of Object.entries(cell.results ?? {})) {
        if (taskStatus(record.status) !== "running") continue;
        const job = record.job_id ? currentJobs.find((item) => item.job_id === record.job_id) : null;
        const recovered: CachedResult = job
          ? taskRecordFromJob(record, job)
          : {
              ...record,
              status: "failed",
              updated_at: new Date().toISOString(),
              error: record.job_id
                ? "计算后端已重启或任务不存在，请重新提交。"
                : "页面刷新后无法恢复此同步任务，请重新计算。",
            };
        await updateTaskResult(loaded.id, cell.id, key, recovered);
        next = mergeTaskRecord(next, cell.id, key, recovered);
      }
    }
    return next;
  }

  async function syncGaussianTaskRecords(currentJobs: GaussianJob[]) {
    const current = workspaceRef.current;
    if (!current) return;
    for (const cell of current.cells) {
      for (const [key, record] of Object.entries(cell.results ?? {})) {
        if (!record.job_id) continue;
        const job = currentJobs.find((item) => item.job_id === record.job_id);
        if (!job) continue;
        const nextStatus = taskStatus(job.status);
        const payloadStatus = (record.payload as GaussianJob | null)?.status;
        if (taskStatus(record.status) === nextStatus && payloadStatus === job.status) continue;
        const nextRecord = taskRecordFromJob(record, job);
        await persistTaskRecord(cell.id, key, nextRecord);
      }
    }
  }

  async function persistTaskRecord(cellId: string, key: string, record: CachedResult): Promise<CachedResult> {
    const current = workspaceRef.current;
    if (!current) throw new Error("请先打开工作区。");
    const stored = await updateTaskResult(current.id, cellId, key, record);
    setWorkspace((previous) => {
      if (!previous) return previous;
      const next = mergeTaskRecord(previous, cellId, key, stored);
      workspaceRef.current = next;
      return next;
    });
    return stored;
  }

  async function refreshComputeStatus() {
    try {
      setComputeStatus(await getComputeStatus());
    } catch {
      setComputeStatus(null);
    }
  }

  async function handleNewWorkspace() {
    const title = `Workspace ${new Date().toLocaleString()}`;
    const created = await createWorkspace(title);
    workspaceRef.current = created;
    setWorkspace(created);
    setActiveCellId(null);
    setSelected(null);
    await refreshWorkspaces();
  }

  async function handleOpenWorkspace(id: string) {
    await loadWorkspace(id);
  }

  async function handleSaveWorkspace(next = workspace) {
    if (!next) return;
    const latest = workspaceRef.current;
    const candidate = latest?.id === next.id
      ? {
          ...next,
          cells: next.cells.map((cell) => {
            const latestCell = latest.cells.find((item) => item.id === cell.id);
            return latestCell
              ? { ...cell, results: { ...(cell.results ?? {}), ...(latestCell.results ?? {}) } }
              : cell;
          }),
        }
      : next;
    const saved = await saveWorkspace(candidate);
    workspaceRef.current = saved;
    setWorkspace(saved);
    await refreshWorkspaces();
  }

  async function handleDeleteCell(cellId: string) {
    if (!workspace) return;
    const nextCells = workspace.cells.filter((cell) => cell.id !== cellId);
    const next = { ...workspace, cells: nextCells };
    setWorkspace(next);
    if (activeCellId === cellId) {
      const fallback = nextCells[0] ?? null;
      setActiveCellId(fallback?.id ?? null);
      setSelected(fallback ? { kind: "cell", cell: fallback } : null);
    }
    await handleSaveWorkspace(next);
  }

  async function handleAddCell(type: CellType = "chem") {
    if (!workspace) return;
    const defaults = defaultObjectsFor(type);
    const cell = await addCell(workspace.id, type, defaults.title, defaults.objects);
    const next = { ...workspace, cells: [...workspace.cells, cell] };
    setWorkspace(next);
    setActiveCellId(cell.id);
    setSelected({ kind: "cell", cell });
    await refreshWorkspaces();
  }

  function updateCell(updated: WorkspaceCell) {
    setWorkspace((current) => {
      if (!current) return current;
      const next = {
        ...current,
        cells: current.cells.map((cell) => (cell.id === updated.id ? { ...updated, results: cell.results } : cell)),
      };
      workspaceRef.current = next;
      return next;
    });
  }

  const activeCell = workspace?.cells.find((cell) => cell.id === activeCellId) ?? null;
  const currentSelection = bindSelection(selected, workspace);

  return (
    <div className={`app-shell ${unitRailOpen ? "" : "unit-rail-collapsed"}`}>
      <main className="main">
        <header className="topbar">
          <div className="topbar-left">
            <button className="rail-toggle" onClick={() => setUnitRailOpen((open) => !open)} title={unitRailOpen ? "隐藏单元栏" : "显示单元栏"}>
              {unitRailOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
            </button>
            <div className="workspace-switcher">
              <button className="workspace-trigger" onClick={() => setWorkspaceMenuOpen((open) => !open)}>
                <Atom size={18} />
                <span>{workspace?.title ?? "选择工作区"}</span>
                <ChevronDown size={18} />
              </button>
              <p>{workspace ? `${workspace.cells.length} 个单元 · ${workspace.updated_at}` : "创建或打开一个工作区开始"}</p>
              {workspaceMenuOpen && (
                <div className="workspace-menu">
                  <button className="workspace-menu-new" onClick={() => { handleNewWorkspace(); setWorkspaceMenuOpen(false); }}>
                    <Plus size={16} /> 新建工作区
                  </button>
                  {summaries.map((item) => (
                    <button
                      key={item.id}
                      className={`workspace-menu-item ${workspace?.id === item.id ? "active" : ""}`}
                      onClick={() => { handleOpenWorkspace(item.id); setWorkspaceMenuOpen(false); }}
                    >
                      <span>{item.title}</span>
                      <small>{item.cell_count} cells</small>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div className="topbar-actions">
            <button className="ghost-button compact" onClick={() => setModal({ kind: "backend", status: computeStatus })}>
              <Cpu size={15} /> 后端
            </button>
            <button className="primary-button" onClick={() => handleSaveWorkspace()} disabled={!workspace}>
              <Save size={16} /> 保存
            </button>
          </div>
        </header>

        <div className="content-grid">
          {unitRailOpen && (
            <aside className="unit-rail">
              <div className="unit-rail-header">
                <strong>单元</strong>
                <button className="primary-button compact" onClick={() => handleAddCell("chem")} disabled={!workspace}>
                  <Plus size={15} /> 添加
                </button>
              </div>
              <div className="cell-list compact-list">
                {workspace?.cells.map((cell) => (
                  <div
                    key={cell.id}
                    className={`cell-card ${activeCellId === cell.id ? "active" : ""}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => {
                      setActiveCellId(cell.id);
                      setSelected({ kind: "cell", cell });
                      setResult(null);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setActiveCellId(cell.id);
                        setSelected({ kind: "cell", cell });
                        setResult(null);
                      }
                    }}
                  >
                    <div className="cell-card-header">
                      <span className="type-pill chem">chem</span>
                      <strong>{cell.title}</strong>
                      <button
                        className="icon-button danger"
                        title="删除单元"
                        onClick={(event) => {
                          event.stopPropagation();
                          handleDeleteCell(cell.id);
                        }}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </aside>
          )}
          <section className="detail">
            <div className="detail-stack">
              {activeCell ? (
                <>
                  <CellDetail
                    cell={activeCell}
                    onUpdate={updateCell}
                    onSelect={setSelected}
                  />
                  <TaskLogDrawer
                    cell={activeCell}
                    openModal={setModal}
                    workspace={workspace}
                    onSave={handleSaveWorkspace}
                  />
                </>
              ) : (
                <EmptyState />
              )}
            </div>
          </section>

          <aside className="task-panel">
            <TaskPanel
              selected={currentSelection}
              workspace={workspace}
              setResult={setResult}
              openModal={setModal}
              onSave={handleSaveWorkspace}
              jobs={jobs}
              refreshJobs={refreshJobs}
              persistTaskRecord={persistTaskRecord}
              computeStatus={computeStatus}
            />
          </aside>
        </div>

      </main>
      {modal && (
        <AppModal
          modal={modal}
          onClose={() => setModal(null)}
          setResult={setResult}
          openModal={setModal}
        />
      )}
    </div>
  );
}

function ResultPanel({ result }: { result: unknown }) {
  const routeResult = asRoutePredictionResult(result);
  const propertyResult = asPropertyResult(result);
  const computeResult = asComputeResult(result);
  const gaussianJob = asGaussianJob(result);
  const geometry = extractMolecularGeometry(result);
  return (
    <section className="result-panel">
      <div className="result-header">
        <BookOpen size={16} />
        <span>结果 / 日志</span>
      </div>
      {!result && <p className="muted">选择一个节点或箭头，然后在右侧运行任务。</p>}
      {geometry && <Molecule3DResultView geometry={geometry} />}
      {routeResult && <RouteResultView result={routeResult} />}
      {propertyResult && <PropertyResultView result={propertyResult} />}
      {computeResult && <ComputeResultView result={computeResult} />}
      {gaussianJob && <GaussianJobView job={gaussianJob} />}
      {Boolean(result) && !routeResult && !propertyResult && !computeResult && !gaussianJob && (
        <GenericResultView result={result} />
      )}
    </section>
  );
}

function TaskLogDrawer({
  cell,
  openModal,
  workspace,
  onSave,
}: {
  cell: WorkspaceCell;
  openModal: (modal: ModalState) => void;
  workspace: Workspace | null;
  onSave: (workspace?: Workspace | null) => Promise<void>;
}) {
  const [open, setOpen] = useState(true);
  const records = Object.entries(cell.results ?? {})
    .map(([key, record]) => ({ key, record }))
    .sort((left, right) => String(right.record.updated_at).localeCompare(String(left.record.updated_at)));

  function openRecord(record: CachedResult, key: string) {
    const title = record.task_label ?? "任务记录";
    if (taskStatusForRecord(record) === "failed") {
      openModal({ kind: "task-error", title: `${title}失败`, record });
      return;
    }
    const parts = key.split(":");
    if (parts[2] === "retrosynthesis" && workspace) {
      const moleculeId = parts[1];
      const molecule = cell.objects?.molecules?.find((m) => m.id === moleculeId);
      if (molecule) {
        const moleculeRouteSets = workspace.route_candidate_sets?.filter((set) => set.target_smiles === molecule.smiles) ?? [];
        if (moleculeRouteSets.length > 0) {
          openModal({
            kind: "routes",
            sets: moleculeRouteSets,
            workspace,
            selected: { kind: "molecule", cell, molecule },
            onSave,
          });
          return;
        }
      }
    }
    openModal({ kind: "result", title, result: resultForRecord(record) });
  }

  return (
    <section className={`task-log-drawer ${open ? "open" : ""}`}>
      <button className="task-log-toggle" onClick={() => setOpen((current) => !current)}>
        <span><History size={16} /> 任务日志</span>
        <span className="task-log-count">{records.length}</span>
        {open ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
      </button>
      {open && (
        <div className="task-log-list">
          {records.length ? records.map(({ key, record }) => {
            const status = taskStatusForRecord(record);
            return (
              <button key={key} className="task-log-row" onClick={() => openRecord(record, key)}>
                <span className={`task-log-status task-log-status-${status}`}>{taskStatusLabel(status)}</span>
                <span className="task-log-main">
                  <strong>{record.task_label ?? key}</strong>
                  <small>{record.object_label ?? record.object_id ?? "当前单元"}</small>
                </span>
                <time>{formatTaskTime(record.updated_at)}</time>
              </button>
            );
          }) : <p className="muted task-log-empty">当前单元还没有任务记录。</p>}
        </div>
      )}
    </section>
  );
}

function RouteResultView({ result }: { result: ReturnType<typeof asRoutePredictionResult> & {} }) {
  return (
    <div className="structured-result">
      <div className="result-summary">
        <strong>{result.target_smiles}</strong>
        <span>{result.used_fallback ? "演示候选" : "AiZynthFinder"}</span>
      </div>
      <p>{result.status}</p>
      <div className="route-result-list">
        {result.candidates.map((route, index) => (
          <div className="route-result-card" key={route.id}>
            <strong>{index + 1}. {route.title}</strong>
            <span>{route.depth} 步 · {route.precursor_count} 个前体 · 库存 {route.stock_count}</span>
            <small>{route.molecules.map((item) => item.smiles).join("  +  ")}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function PropertyResultView({ result }: { result: Record<string, any> }) {
  const rdkit = result.rdkit ?? {};
  const opera = result.opera ?? null;
  return (
    <div className="structured-result">
      <div className="result-summary">
        <strong>{rdkit.SMILES ?? "分子性质"}</strong>
        <span>{opera?.status === "available" ? "RDKit + OPERA" : "RDKit"}</span>
      </div>
      <div className="metric-grid">
        {["Formula", "MolWt", "LogP", "TPSA", "HBD", "HBA"].map((key) => (
          rdkit[key] !== undefined && <div key={key}><span>{key}</span><strong>{String(rdkit[key])}</strong></div>
        ))}
      </div>
      {opera && (
        <div className="result-block">
          <strong>OPERA QSAR</strong>
          <p>{opera.status === "available" ? opera.source : opera.reason ?? opera.status}</p>
          {opera.properties && (
            <div className="metric-grid">
              {Object.entries(opera.properties).map(([key, value]) => (
                <div key={key}><span>{key}</span><strong>{String(value ?? "-")}</strong></div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Molecule3DResultView({ geometry }: { geometry: ExtractedGeometry }) {
  const viewerRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (typeof window === "undefined") return;
    if ((window as any).$3Dmol) {
      setReady(true);
      return;
    }
    const existing = document.querySelector<HTMLScriptElement>('script[data-osf-3dmol="true"]');
    if (existing) {
      existing.addEventListener("load", () => setReady(true), { once: true });
      existing.addEventListener("error", () => setError("3Dmol 渲染插件加载失败。"), { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = "https://3dmol.org/build/3Dmol-min.js";
    script.async = true;
    script.setAttribute("data-osf-3dmol", "true");
    script.onload = () => setReady(true);
    script.onerror = () => setError("3Dmol 渲染插件加载失败。");
    document.body.appendChild(script);
  }, []);

  useEffect(() => {
    if (!ready || !viewerRef.current || !(window as any).$3Dmol) return;
    const viewer = (window as any).$3Dmol.createViewer(viewerRef.current, { backgroundColor: "#f8fafc" });
    viewer.addModel(geometry.xyz, "xyz");
    viewer.setStyle({}, { stick: { radius: 0.15 }, sphere: { scale: 0.25 } });
    viewer.zoomTo();
    viewer.render();
    return () => {
      viewer.clear();
    };
  }, [ready, geometry.xyz]);

  return (
    <div className="result-block molecule-3d-result">
      <div className="result-summary">
        <strong>三维结构</strong>
        <span>{geometry.atomCount} atoms</span>
      </div>
      <div className="result-3d-viewer-container">
        <div ref={viewerRef} className="result-3d-viewer" />
        {!ready && !error && <div className="result-3d-placeholder">正在加载 3D 结构...</div>}
        {error && <div className="result-3d-placeholder error">{error}</div>}
      </div>
      <p className="result-hint">鼠标拖拽旋转，滚轮缩放，右键拖拽平移。</p>
    </div>
  );
}

function ComputeResultView({ result }: { result: Record<string, any> }) {
  const data = isPlainObject(result.data) ? result.data : {};
  const metricEntries = Object.entries(data)
    .filter(([key]) => !isVerboseResultKey(key))
    .map(([key, value]) => [humanizeKey(key), formatResultValue(value)] as const);
  const highlights = extractLogHighlights([result.stdout, result.stderr].filter(Boolean).join("\n"));
  return (
    <div className="structured-result">
      <div className="result-summary">
        <strong>{result.source ?? "计算结果"}</strong>
        <span>{statusLabel(result.status)}</span>
      </div>
      <div className="result-status-line">
        <span className={`status-dot ${result.status === "failed" ? "missing" : "ready"}`} />
        <strong>{result.status === "failed" ? "计算失败" : "计算完成"}</strong>
        {typeof data.returncode !== "undefined" && <small>return code {String(data.returncode)}</small>}
      </div>
      {result.work_dir && <code>{result.work_dir}</code>}
      {metricEntries.length > 0 && (
        <div className="metric-grid">
          {metricEntries.map(([key, value]) => (
            <div key={key}><span>{key}</span><strong>{value}</strong></div>
          ))}
        </div>
      )}
      {result.reason && <div className="warning-box">{String(result.reason)}</div>}
      {highlights.length > 0 && <LogHighlights items={highlights} />}
      <RawLogDetails
        logs={[
          ["标准输出", result.stdout],
          ["错误输出", result.stderr],
        ]}
        raw={result}
      />
    </div>
  );
}

function GaussianJobView({ job }: { job: GaussianJob }) {
  const payload = job as any;
  const result = isPlainObject(payload.result) ? payload.result : null;
  const parsed = isPlainObject(result?.parsed_result) ? result?.parsed_result : null;
  const metrics = [
    ["状态", statusLabel(job.status)],
    ["作业 ID", job.job_id],
    ["最终能量", parsed?.final_energy_hartree],
    ["Gibbs 自由能", parsed?.gibbs_free_energy_hartree],
    ["虚频数量", parsed?.imaginary_frequency_count],
    ["HOMO", parsed?.homo_ev],
    ["LUMO", parsed?.lumo_ev],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");
  const highlights = extractLogHighlights([result?.stdout, result?.stderr, job.error].filter(Boolean).join("\n"));
  return (
    <div className="structured-result">
      <div className="result-summary">
        <strong>{job.job_id}</strong>
        <span>{statusLabel(job.status)}</span>
      </div>
      <div className="metric-grid">
        {metrics.map(([key, value]) => (
          <div key={String(key)}><span>{String(key)}</span><strong>{formatResultValue(value)}</strong></div>
        ))}
      </div>
      {job.work_dir && <code>{job.work_dir}</code>}
      {result?.input_path && <code>{String(result.input_path)}</code>}
      {result?.log_path && <code>{String(result.log_path)}</code>}
      {Array.isArray(parsed?.warnings) && parsed.warnings.length > 0 && (
        <div className="result-block">
          <strong>解析警告</strong>
          {parsed.warnings.map((warning: string) => <p key={warning}>{warning}</p>)}
        </div>
      )}
      {job.error && <div className="warning-box">{job.error}</div>}
      {highlights.length > 0 && <LogHighlights items={highlights} />}
      <RawLogDetails
        logs={[
          ["标准输出", result?.stdout],
          ["错误输出", result?.stderr],
        ]}
        raw={job}
      />
    </div>
  );
}

function GenericResultView({ result }: { result: unknown }) {
  const summary = summarizeUnknownResult(result);
  return (
    <div className="structured-result">
      {summary.metrics.length > 0 && (
        <div className="metric-grid">
          {summary.metrics.map(([key, value]) => (
            <div key={key}><span>{key}</span><strong>{value}</strong></div>
          ))}
        </div>
      )}
      {summary.messages.map((message) => <p key={message}>{message}</p>)}
      {summary.sections.map((section) => (
        <div className="result-block" key={section.title}>
          <strong>{section.title}</strong>
          <div className="metric-grid">
            {section.items.map(([key, value]) => (
              <div key={key}><span>{key}</span><strong>{value}</strong></div>
            ))}
          </div>
        </div>
      ))}
      <RawLogDetails raw={result} />
    </div>
  );
}

function LogHighlights({ items }: { items: string[] }) {
  return (
    <div className="result-block log-highlights">
      <strong>日志摘要</strong>
      {items.map((item) => <p key={item}>{item}</p>)}
    </div>
  );
}

function RawLogDetails({ logs = [], raw }: { logs?: Array<[string, unknown]>; raw?: unknown }) {
  const visibleLogs = logs.filter(([, value]) => typeof value === "string" && value.trim().length > 0) as Array<[string, string]>;
  if (visibleLogs.length === 0 && raw === undefined) return null;
  return (
    <details className="raw-log-details">
      <summary>原始日志 / 原始数据</summary>
      {visibleLogs.map(([title, value]) => (
        <div key={title} className="raw-log-block">
          <strong>{title}</strong>
          <pre>{trimLongText(value)}</pre>
        </div>
      ))}
      {raw !== undefined && (
        <div className="raw-log-block">
          <strong>完整 JSON</strong>
          <pre>{trimLongText(JSON.stringify(raw, null, 2) ?? "")}</pre>
        </div>
      )}
    </details>
  );
}

function CellDetail({
  cell,
  onUpdate,
  onSelect,
}: {
  cell: WorkspaceCell;
  onUpdate: (cell: WorkspaceCell) => void;
  onSelect: (selected: SelectedObject) => void;
}) {
  const initialNodes = useMemo(() => toNodes(cell), [cell.id]);
  const initialEdges = useMemo(() => toEdges(cell), [cell.id]);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [connectMode, setConnectMode] = useState(false);
  const [shiftConnectMode, setShiftConnectMode] = useState(false);
  const [pendingConnectionNodeId, setPendingConnectionNodeId] = useState<string | null>(null);
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(null);
  const [relationSourceId, setRelationSourceId] = useState("");
  const [relationTargetId, setRelationTargetId] = useState("");
  const nodeTypes = useMemo(() => ({ molecule: MoleculeNode }), []);
  const edgeTypes = useMemo(() => ({ orthogonal: OrthogonalEdge }), []);
  const molecules = cell.objects.molecules ?? [];
  const linkingActive = connectMode || shiftConnectMode;
  const routedEdges = useMemo(
    () => routeEdgesForNodes(edges, nodes).map((edge) => ({ ...edge, selected: edge.id === selectedEdgeId })),
    [edges, nodes, selectedEdgeId],
  );

  useEffect(() => {
    setNodes(toNodes(cell));
    setEdges(toEdges(cell));
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setSelectedComponentId(null);
    setPendingConnectionNodeId(null);
    setRelationSourceId("");
    setRelationTargetId("");
  }, [cell.id, cell.objects]);

  useEffect(() => {
    function handleShiftDown(event: KeyboardEvent) {
      if (event.key !== "Shift") return;
      if (event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) return;
      setShiftConnectMode(true);
      setSelectedEdgeId(null);
    }

    function handleShiftUp(event: KeyboardEvent) {
      if (event.key !== "Shift") return;
      setShiftConnectMode(false);
      setPendingConnectionNodeId(null);
    }

    window.addEventListener("keydown", handleShiftDown);
    window.addEventListener("keyup", handleShiftUp);
    return () => {
      window.removeEventListener("keydown", handleShiftDown);
      window.removeEventListener("keyup", handleShiftUp);
    };
  }, []);

  useEffect(() => {
    function deleteSelectedEdge(event: KeyboardEvent) {
      if (!selectedEdgeId || (event.key !== "Delete" && event.key !== "Backspace")) return;
      if (event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLInputElement) return;
      event.preventDefault();
      removeEdge(selectedEdgeId);
    }
    window.addEventListener("keydown", deleteSelectedEdge);
    return () => window.removeEventListener("keydown", deleteSelectedEdge);
  }, [selectedEdgeId]);

  const onConnect = useCallback(
    (params: Connection) => {
      if (!params.source || !params.target) return;
      if (params.source === params.target) return;
      const sourceNode = nodes.find((node) => node.id === params.source);
      const targetNode = nodes.find((node) => node.id === params.target);
      const route = sourceNode && targetNode ? chooseBestOrthogonalRoute(sourceNode, targetNode, nodes) : null;
      const edge = makeCanvasEdge({
        source: params.source,
        target: params.target,
        sourceHandle: route?.sourceHandle ?? normalizeMoleculeHandleId(params.sourceHandle, "right"),
        targetHandle: route?.targetHandle ?? normalizeMoleculeHandleId(params.targetHandle, "left"),
      });
      setEdges((current) => addEdge(edge, current));
      setSelectedEdgeId(edge.id);
    },
    [nodes, setEdges],
  );

  function createRelationship(sourceId: string, targetId: string): boolean {
    if (sourceId === targetId) return false;
    const sourceNode = nodes.find((node) => node.id === sourceId);
    const targetNode = nodes.find((node) => node.id === targetId);
    const route = sourceNode && targetNode ? chooseBestOrthogonalRoute(sourceNode, targetNode, nodes) : null;
    const edge = makeCanvasEdge({
      source: sourceId,
      target: targetId,
      sourceHandle: route?.sourceHandle ?? "right",
      targetHandle: route?.targetHandle ?? "left",
    });
    setEdges((current) => addEdge(edge, current));
    setSelectedEdgeId(edge.id);
    return true;
  }

  function handleNodeClick(node: Node, componentIndex?: number) {
    if (linkingActive) {
      setSelectedEdgeId(null);
      if (!pendingConnectionNodeId) {
        setPendingConnectionNodeId(node.id);
        setRelationSourceId(node.id);
        return;
      }
      if (createRelationship(pendingConnectionNodeId, node.id)) {
        setPendingConnectionNodeId(node.id);
        setRelationSourceId(node.id);
        const nextTarget = molecules.find((molecule) => molecule.id !== node.id)?.id ?? "";
        setRelationTargetId(nextTarget);
      }
      return;
    }
    setSelectedNodeId(node.id);
    setSelectedEdgeId(null);
    const molecule = cell.objects.molecules?.find((item) => item.id === node.id);
    if (!molecule) return;
    const components = componentsForMolecule(molecule);
    const component = components.length > 1 && componentIndex !== undefined
      ? components[componentIndex]
      : undefined;
    setSelectedComponentId(component?.id ?? null);
    onSelect({ kind: "molecule", cell, molecule, component });
  }

  function removeEdge(edgeId: string) {
    setEdges((current) => current.filter((edge) => edge.id !== edgeId));
    setSelectedEdgeId(null);
  }

  function removeNodes(nodeIds: string[]) {
    if (nodeIds.length === 0) return;
    const removedIds = new Set(nodeIds);
    const nextNodes = nodes.filter((node) => !removedIds.has(node.id));
    const nextEdges = edges.filter((edge) => !removedIds.has(edge.source) && !removedIds.has(edge.target));
    const updatedCell: WorkspaceCell = {
      ...cell,
      canvas: { nodes: nextNodes, edges: nextEdges },
      objects: objectsFromCanvas(cell, nextNodes, nextEdges),
    };
    setNodes(nextNodes);
    setEdges(nextEdges);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setSelectedComponentId(null);
    setPendingConnectionNodeId((current) => current && removedIds.has(current) ? null : current);
    setRelationSourceId((current) => removedIds.has(current) ? "" : current);
    setRelationTargetId((current) => removedIds.has(current) ? "" : current);
    onUpdate(updatedCell);
    onSelect({ kind: "cell", cell: updatedCell });
  }

  function removeAllEdges() {
    setEdges([]);
    setSelectedEdgeId(null);
    setPendingConnectionNodeId(null);
  }

  function persistCanvas() {
    onUpdate({
      ...cell,
      canvas: { nodes, edges },
      objects: objectsFromCanvas(cell, nodes, edges),
    });
  }

  return (
    <div className="detail-shell">
      <div className="detail-toolbar-group">
        <div className="detail-toolbar">
          <strong>{cell.title}</strong>
          <div className="toolbar-actions">
            <button
              className={`ghost-button compact ${connectMode ? "active-action" : ""}`}
              onClick={() => {
                const nextMode = !connectMode;
                const first = molecules[0]?.id ?? "";
                const second = molecules.find((molecule) => molecule.id !== first)?.id ?? "";
                setConnectMode(nextMode);
                setPendingConnectionNodeId(null);
                setRelationSourceId(first);
                setRelationTargetId(second);
                setSelectedEdgeId(null);
              }}
            >
              <Link2 size={14} /> 连接分子
            </button>
            {linkingActive && (
              <span className="toolbar-hint">
                {pendingConnectionNodeId ? "继续选择下一个分子" : shiftConnectMode ? "Shift 连线：选择起点" : "选择起点分子"}
              </span>
            )}
            {selectedEdgeId && (
              <button className="ghost-button compact danger-action" onClick={() => removeEdge(selectedEdgeId)}>
                <Trash2 size={14} /> 删除箭头
              </button>
            )}
            {selectedNodeId && (
              <button className="ghost-button compact danger-action" onClick={() => removeNodes([selectedNodeId])}>
                <Trash2 size={14} /> 删除 SMILES 块
              </button>
            )}
            {edges.length > 0 && (
              <button className="ghost-button compact danger-action" onClick={removeAllEdges}>
                <Trash2 size={14} /> 删除全部连线
              </button>
            )}
            <button className="ghost-button compact" onClick={persistCanvas}>同步画布到单元</button>
          </div>
        </div>
        {connectMode && (
          <div className="relationship-bar">
            <select
              aria-label="连接起点"
              value={relationSourceId}
              onChange={(event) => {
                setRelationSourceId(event.target.value);
                setPendingConnectionNodeId(event.target.value || null);
              }}
            >
              <option value="">起点</option>
              {molecules.map((molecule) => (
                <option key={molecule.id} value={molecule.id}>{molecule.label || molecule.smiles}</option>
              ))}
            </select>
            <span>→</span>
            <select
              aria-label="连接终点"
              value={relationTargetId}
              onChange={(event) => setRelationTargetId(event.target.value)}
            >
              <option value="">终点</option>
              {molecules.map((molecule) => (
                <option key={molecule.id} value={molecule.id}>{molecule.label || molecule.smiles}</option>
              ))}
            </select>
            <button
              className="primary-button compact"
              disabled={!relationSourceId || !relationTargetId || relationSourceId === relationTargetId}
              onClick={() => {
                if (createRelationship(relationSourceId, relationTargetId)) {
                  setPendingConnectionNodeId(relationTargetId);
                  setRelationSourceId(relationTargetId);
                  const nextTarget = molecules.find((molecule) => molecule.id !== relationTargetId)?.id ?? "";
                  setRelationTargetId(nextTarget);
                }
              }}
            >
              创建连接
            </button>
          </div>
        )}
      </div>
      <div className="canvas">
        <ReactFlow
          nodes={nodes.map((node) => ({
            ...node,
            data: {
              ...node.data,
              onActivate: () => handleNodeClick(node),
              onActivateComponent: (componentIndex: number) => handleNodeClick(node, componentIndex),
              selectedComponentId,
            },
            className: node.id === pendingConnectionNodeId ? "connection-source-node" : undefined,
          }))}
          edges={routedEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          connectionMode={ConnectionMode.Loose}
          deleteKeyCode={["Backspace", "Delete"]}
          fitView
          onNodeClick={(_, node) => handleNodeClick(node)}
          onNodesDelete={(deletedNodes) => removeNodes(deletedNodes.map((node) => node.id))}
          onEdgeClick={(_, edge) => {
            setSelectedEdgeId(edge.id);
            const reaction = reactionFromEdge(cell, edge);
            if (reaction) onSelect({ kind: "reaction", cell, reaction });
          }}
          onPaneClick={() => {
            setSelectedNodeId(null);
            setSelectedEdgeId(null);
            if (!connectMode) setPendingConnectionNodeId(null);
          }}
          onEdgesDelete={() => setSelectedEdgeId(null)}
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
      <EditorStrip cell={cell} onUpdate={onUpdate} />
    </div>
  );
}

function MoleculeNode({ data }: NodeProps) {
  const smiles = String(data.smiles ?? "");
  const label = String(data.label ?? smiles);
  const onActivate = typeof data.onActivate === "function" ? data.onActivate : null;
  const onActivateComponent = typeof data.onActivateComponent === "function" ? data.onActivateComponent : null;
  const selectedComponentId = String(data.selectedComponentId ?? "");
  const componentSmiles = splitSmilesComponents(smiles);

  return (
    <div
      className="molecule-node"
      onClick={(event) => {
        event.stopPropagation();
        if (componentSmiles.length <= 1) onActivate?.();
      }}
    >
      {moleculeHandles.map((handle) => (
        <span key={handle.id}>
          <Handle
            id={handle.id}
            type="source"
            position={handle.position}
            className="molecule-handle molecule-handle-hidden"
            style={handle.style}
          />
          <Handle
            id={handle.id}
            type="target"
            position={handle.position}
            className="molecule-handle molecule-handle-hidden"
            style={handle.style}
          />
        </span>
      ))}
      {componentSmiles.length > 1 ? (
        <div className="molecule-components" aria-label="多分子组分">
          {componentSmiles.map((component, index) => {
            const componentId = `${String(data.id ?? "")}:component:${index}`;
            return (
              <button
                type="button"
                className={`molecule-component nodrag nowheel ${selectedComponentId.endsWith(`:component:${index}`) ? "selected" : ""}`}
                key={`${component}-${index}`}
                onClick={(event) => {
                  event.stopPropagation();
                  onActivateComponent?.(index);
                }}
                title={`选择组分 ${index + 1}：${component}`}
                aria-label={`选择组分 ${index + 1}：${component}`}
                data-component-id={componentId}
              >
                <MoleculeDrawing smiles={component} />
                <span>{component}</span>
              </button>
            );
          })}
        </div>
      ) : (
        <MoleculeDrawing smiles={smiles} />
      )}
      <div className="molecule-caption" title={label === smiles ? smiles : `${label} · ${smiles}`}>
        {smiles}
      </div>
    </div>
  );
}

function MoleculeDrawing({ smiles }: { smiles: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setFailed(false);
    if (!smiles) return;
    renderMoleculeSvg(smiles)
      .then((nextSvg) => {
        if (!cancelled) {
          setSvg(nextSvg);
          setFailed(!nextSvg);
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => { cancelled = true; };
  }, [smiles]);

  return (
    <div className="molecule-drawing">
      {svg ? <div dangerouslySetInnerHTML={{ __html: svg }} /> : <span className={failed ? "formula-fallback" : ""}>{failed ? displayFormulaLike(smiles) : "渲染中..."}</span>}
    </div>
  );
}

function EditorStrip({ cell, onUpdate }: { cell: WorkspaceCell; onUpdate: (cell: WorkspaceCell) => void }) {
  const [input, setInput] = useState(examples.molecule);
  const [drawerOpen, setDrawerOpen] = useState(false);

  function addInput() {
    const lines = input
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const molecules = [...(cell.objects.molecules ?? [])];
    const reactions = [...(cell.objects.reactions ?? [])];
    for (const line of lines) {
      if (line.includes(">>")) {
        const reactionId = `rxn-${Date.now()}-${reactions.length}`;
        const reactionSmiles = normalizeReactionSmiles(line);
        reactions.push({ id: reactionId, label: `Step ${reactions.length + 1}`, reaction_smiles: reactionSmiles });
        for (const smiles of moleculesFromReaction(reactionSmiles)) {
          molecules.push(createMoleculeObject(smiles, molecules.length));
        }
      } else {
        molecules.push(createMoleculeObject(line, molecules.length));
      }
    }
    onUpdate({
      ...cell,
      objects: {
        ...cell.objects,
        molecules,
        reactions,
      },
      canvas: { nodes: [], edges: [] },
    });
  }

  return (
    <div className="editor-strip">
      <label>输入结构/反应/路线</label>
      <textarea
        value={input}
        onChange={(event) => setInput(event.target.value)}
        placeholder={"CCO\nCCO>>CC=O\nA.B>>C"}
      />
      <button onClick={addInput}>添加到画布</button>
      <button className="ghost-button compact" onClick={() => setDrawerOpen(true)}>
        打开绘图器
      </button>
      {drawerOpen && (
        <KetcherModal
          initialSmiles={input.includes(">>") ? "" : input.split(/\r?\n/)[0] ?? ""}
          onClose={() => setDrawerOpen(false)}
          onApply={(nextSmiles) => {
            setInput(nextSmiles);
            setDrawerOpen(false);
          }}
        />
      )}
    </div>
  );
}

function KetcherModal({
  initialSmiles,
  onClose,
  onApply,
}: {
  initialSmiles: string;
  onClose: () => void;
  onApply: (smiles: string) => void;
}) {
  const ketcherRef = useRef<any>(null);
  const [EditorComponent, setEditorComponent] = useState<any>(null);
  const [structServiceProvider, setStructServiceProvider] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadKetcher() {
      try {
        (globalThis as any).global = globalThis;
        await import("ketcher-react/dist/index.css");
        const [{ Editor }, { StandaloneStructServiceProvider }] = await Promise.all([
          import("ketcher-react"),
          import("ketcher-standalone/dist/binaryWasm"),
        ]);
        if (!cancelled) {
          setEditorComponent(() => Editor);
          setStructServiceProvider(new StandaloneStructServiceProvider());
        }
      } catch (exc) {
        if (!cancelled) setError(`Ketcher 加载失败：${String(exc)}`);
      }
    }
    loadKetcher();
    return () => {
      cancelled = true;
    };
  }, []);

  async function apply() {
    if (!ketcherRef.current) {
      setError("Ketcher 尚未初始化。");
      return;
    }
    try {
      const smiles = await ketcherRef.current.getSmiles();
      onApply(smiles);
    } catch (exc) {
      setError(String(exc));
    }
  }

  return (
    <div className="osf-modal-backdrop">
      <div className="osf-ketcher-modal">
        <div className="osf-modal-header">
          <strong>Ketcher 绘图输入</strong>
          <button onClick={onClose}>关闭</button>
        </div>
        <div className="osf-ketcher-host">
          {EditorComponent && structServiceProvider ? (
            <EditorComponent
              staticResourcesUrl="/"
              structServiceProvider={structServiceProvider}
              errorHandler={(message: unknown) => setError(String(message))}
              onInit={(ketcher: any) => {
                ketcherRef.current = ketcher;
                if (initialSmiles) {
                  ketcher.setMolecule(initialSmiles).catch((exc: unknown) => setError(String(exc)));
                }
              }}
            />
          ) : (
            <div className="empty-state">正在加载 Ketcher 绘图器...</div>
          )}
        </div>
        {error && <div className="error-box">{error}</div>}
        <div className="osf-modal-footer">
          <span>应用后会回填到“添加分子”的 SMILES 输入框。</span>
          <button className="primary-button" onClick={apply}>应用结构</button>
        </div>
      </div>
    </div>
  );
}

function TaskPanel({
  selected,
  workspace,
  setResult,
  openModal,
  onSave,
  jobs,
  refreshJobs,
  persistTaskRecord,
  computeStatus,
}: {
  selected: SelectedObject;
  workspace: Workspace | null;
  setResult: (result: unknown) => void;
  openModal: (modal: ModalState) => void;
  onSave: (workspace?: Workspace | null) => Promise<void>;
  jobs: GaussianJob[];
  refreshJobs: () => Promise<void>;
  persistTaskRecord: (cellId: string, key: string, record: CachedResult) => Promise<CachedResult>;
  computeStatus: ComputeStatus | null;
}) {
  async function runTask(
    definition: TaskDefinition,
    task: () => Promise<unknown>,
    options?: {
      openResult?: boolean;
      title?: string;
      config?: Record<string, unknown>;
      onConfigure?: () => void;
      statusFromResult?: (result: unknown) => CachedResult["status"];
    },
  ) {
    const key = taskResultKey(definition);
    const runningRecord: CachedResult = {
      task_id: definition.id,
      task_label: definition.label,
      object_id: definition.objectId,
      object_kind: definition.objectKind,
      object_label: definition.objectLabel,
      engine: definition.engine,
      status: "running",
      updated_at: new Date().toISOString(),
      payload: null,
      config: options?.config,
    };
    await persistTaskRecord(definition.cellId, key, runningRecord);
    try {
      const nextResult = await task();
      const nextStatus = options?.statusFromResult?.(nextResult) ?? taskStatusFromResult(nextResult);
      const job = asGaussianJob(nextResult);
      const completedRecord: CachedResult = {
        ...runningRecord,
        status: nextStatus,
        updated_at: new Date().toISOString(),
        payload: nextResult,
        error: nextStatus === "failed" ? resultErrorMessage(nextResult) ?? job?.error ?? "计算失败。" : undefined,
        job_id: job?.job_id,
      };
      await persistTaskRecord(definition.cellId, key, completedRecord);
      setResult(nextResult);
      if (nextStatus === "failed") {
        openModal({
          kind: "task-error",
          title: `${definition.label}失败`,
          record: completedRecord,
          onRetry: () => void runTask(definition, task, options),
          onConfigure: options?.onConfigure,
        });
      } else if (options?.openResult !== false) {
        openModal({
          kind: "result",
          title: options?.title ?? "任务结果",
          result: resultForRecord(completedRecord),
          onRecompute: () => void runTask(definition, task, options),
          onConfigure: options?.onConfigure,
        });
      }
      return nextResult;
    } catch (error) {
      const failedRecord: CachedResult = {
        ...runningRecord,
        status: "failed",
        updated_at: new Date().toISOString(),
        error: errorMessage(error),
        payload: null,
      };
      await persistTaskRecord(definition.cellId, key, failedRecord);
      setResult(failedRecord);
      openModal({
        kind: "task-error",
        title: `${definition.label}失败`,
        record: failedRecord,
        onRetry: () => void runTask(definition, task, options),
        onConfigure: options?.onConfigure,
      });
      return null;
    }
  }

  return (
    <div>
      <div className="panel-title">
        <Boxes size={16} />
        <span>任务面板</span>
      </div>
      {!selected && <p className="muted">选择 notebook 单元、分子节点或反应箭头。</p>}
      {selected?.kind === "cell" && <CellTasks selected={selected} openModal={openModal} />}
      {selected?.kind === "molecule" && (
        <MoleculeTasks
          selected={selected}
          workspace={workspace}
          runTask={runTask}
          openModal={openModal}
          jobs={jobs}
          onSave={onSave}
          refreshJobs={refreshJobs}
          computeStatus={computeStatus}
        />
      )}
      {selected?.kind === "reaction" && (
        <ReactionTasks
          selected={selected}
          workspace={workspace}
          runTask={runTask}
          openModal={openModal}
          jobs={jobs}
          refreshJobs={refreshJobs}
        />
      )}
    </div>
  );
}

function RouteCandidateSets({
  sets,
  workspace,
  selected,
  onSave,
  setResult,
}: {
  sets: RouteCandidateSet[];
  workspace: Workspace;
  selected: SelectedObject;
  onSave: (workspace?: Workspace | null) => Promise<void>;
  setResult: (result: unknown) => void;
}) {
  const activeCell = selected?.kind ? selected.cell : workspace.cells[0];
  const anchorMolecule = selected?.kind === "molecule" ? selected.molecule : null;
  const anchorComponent = selected?.kind === "molecule" ? selected.component ?? null : null;

  async function addRouteToCurrentCell(route: RouteCandidate) {
    if (!activeCell) return;
    const updatedCell = addRouteCandidateToCell(activeCell, route, anchorMolecule, anchorComponent);
    await onSave({
      ...workspace,
      cells: workspace.cells.map((cell) => (cell.id === updatedCell.id ? updatedCell : cell)),
    });
    setResult({ action: "route_inserted_into_current_cell", route });
  }

  async function createRouteCell(route: RouteCandidate) {
    const routeCell = createRouteCellFromCandidate(route);
    await onSave({
      ...workspace,
      cells: [...workspace.cells, routeCell],
    });
    setResult({ action: "route_cell_created", route });
  }

  return (
    <>
      <div className="panel-title jobs-title">路线候选集</div>
      <div className="route-candidate-list">
        {sets.slice(-4).reverse().map((set) => (
          <div key={set.id} className="route-candidate-set">
            <div className="route-candidate-head">
              <strong>{set.target_smiles}</strong>
              <span>{set.used_fallback ? "演示" : "预测"}</span>
            </div>
            <p>{set.status}</p>
            {set.candidates.slice(0, 3).map((route, index) => (
              <div key={route.id} className="route-candidate-card">
                <button onClick={() => setResult({ ...set, selected_route: route })}>
                  {index + 1}. {route.title}
                </button>
                <span>{route.depth} 步 · 前体 {route.precursor_count} · 库存 {route.stock_count}</span>
                <div className="route-actions">
                  <button onClick={() => addRouteToCurrentCell(route)}>加入当前画布</button>
                  <button onClick={() => createRouteCell(route)}>新建路线单元</button>
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  );
}

function EngineSelectorView({
  onSelect,
  backendStatus,
}: {
  onSelect: (engine: string) => void;
  backendStatus: ComputeStatus | null;
}) {
  const aizynth = backendStatus?.aizynthfinder;
  const askcos = backendStatus?.askcos;

  return (
    <div className="engine-selector-container">
      <p className="engine-selector-desc">请选择用来预测逆合成反应路线的计算后端引擎：</p>
      <div className="engine-options-list">
        <button
          className="engine-option-card"
          onClick={() => onSelect("aizynthfinder")}
        >
          <div className="engine-option-header">
            <strong>AiZynthFinder (本地/WSL)</strong>
            <span className={`engine-badge ${aizynth?.available ? "ready" : "not-ready"}`}>
              {aizynth?.available ? "已就绪" : "演示候选（未配置）"}
            </span>
          </div>
          <p className="engine-option-desc">
            运行在本地 WSL 中的 AI 逆合成推荐引擎。已完成本地模型包配置，能进行真实计算。
          </p>
        </button>

        <button
          className="engine-option-card"
          onClick={() => onSelect("askcos")}
        >
          <div className="engine-option-header">
            <strong>ASKCOS (Docker/远程)</strong>
            <span className={`engine-badge ${askcos?.available ? "ready" : "not-ready"}`}>
              {askcos?.available ? "已就绪" : "演示候选（未启动）"}
            </span>
          </div>
          <p className="engine-option-desc">
            由 MIT 开发的多步骤路线规则检索平台，部署于本地或远程 Docker 服务（{askcos?.metadata?.url || "100.106.169.46:9100"}）。
          </p>
        </button>
      </div>
    </div>
  );
}

function AppModal({
  modal,
  onClose,
  setResult,
  openModal,
}: {
  modal: Exclude<ModalState, null>;
  onClose: () => void;
  setResult: (result: unknown) => void;
  openModal: (modal: ModalState) => void;
}) {
  return (
    <div className="osf-modal-backdrop">
      <div className={modal.kind === "result" ? "osf-result-modal" : "osf-config-modal"}>
        <div className="osf-modal-header">
          <strong>
            {modal.kind === "result" && modal.title}
            {modal.kind === "task-error" && modal.title}
            {modal.kind === "backend" && "计算后端状态"}
            {modal.kind === "jobs" && "Gaussian 队列"}
            {modal.kind === "routes" && "路线候选"}
            {modal.kind === "engine-select" && "选择合成路线预测引擎"}
          </strong>
          <button onClick={onClose}>关闭</button>
        </div>
        <div className="osf-modal-body">
          {modal.kind === "result" && <ResultPanel result={modal.result} />}
          {modal.kind === "task-error" && (
            <div className="task-error-content">
              <div className="error-box">{modal.record.error ?? "计算失败，未返回具体错误。"}</div>
              {Boolean(modal.record.payload) && <ResultPanel result={resultForRecord(modal.record)} />}
            </div>
          )}
          {modal.kind === "backend" && <BackendStatus status={modal.status} />}
          {modal.kind === "jobs" && <GaussianJobsView jobs={modal.jobs} refresh={modal.refresh} />}
          {modal.kind === "routes" && (
            <RouteCandidateSets
              sets={modal.sets}
              workspace={modal.workspace}
              selected={modal.selected}
              onSave={modal.onSave}
              setResult={(result) => {
                setResult(result);
                openModal({ kind: "result", title: "路线操作结果", result });
              }}
            />
          )}
          {modal.kind === "engine-select" && (
            <EngineSelectorView
              onSelect={(engine) => {
                modal.onSelect(engine);
                onClose();
              }}
              backendStatus={modal.backendStatus}
            />
          )}
        </div>
        {(modal.kind === "result" || modal.kind === "routes") && (modal.onRecompute || (modal.kind === "result" && modal.onConfigure)) && (
          <div className="osf-modal-footer task-error-actions">
            {modal.kind === "result" && modal.onConfigure && (
              <button className="ghost-button" onClick={() => { onClose(); modal.onConfigure?.(); }}>修改配置</button>
            )}
            {modal.onRecompute && (
              <button className="primary-button" onClick={() => { onClose(); modal.onRecompute?.(); }}>
                <RotateCcw size={14} /> 重新计算
              </button>
            )}
          </div>
        )}
        {modal.kind === "task-error" && (modal.onRetry || modal.onConfigure) && (
          <div className="osf-modal-footer task-error-actions">
            {modal.onConfigure && (
              <button className="ghost-button" onClick={() => { onClose(); modal.onConfigure?.(); }}>修改配置</button>
            )}
            {modal.onRetry && (
              <button className="primary-button" onClick={() => { onClose(); modal.onRetry?.(); }}>重新计算</button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function GaussianJobsView({ jobs, refresh }: { jobs: GaussianJob[]; refresh: () => Promise<void> }) {
  return (
    <div className="job-list osf-modal-job-list">
      <button className="ghost-button compact" onClick={() => refresh()}>刷新队列</button>
      {jobs.length ? jobs.map((job) => (
        <div key={job.job_id} className="job-row">
          <span>{job.job_id}</span>
          <strong>{job.status}</strong>
        </div>
      )) : <p className="muted">暂无 Gaussian 作业。</p>}
    </div>
  );
}

function BackendStatus({ status }: { status: ComputeStatus | null }) {
  const orderedKeys = ["gaussian", "aizynthfinder", "askcos", "opera", "rxnmapper", "drfp", "xtb", "crest", "openbabel", "pyscf", "psi4", "geometric", "goodvibes"];
  const entries = orderedKeys
    .map((key) => [key, status?.[key]] as const)
    .filter(([, item]) => Boolean(item));
  return (
    <div className="backend-status" aria-label="计算后端状态">
      {entries.length ? (
        entries.map(([key, item]) => (
          <div className="backend-row" key={key} title={item?.executable ?? undefined}>
            <span className={`status-dot ${item?.available ? "ready" : "missing"}`} />
            <span>{item?.name ?? key}</span>
            <strong>{item?.available ? item?.source ?? "ready" : "missing"}</strong>
          </div>
        ))
      ) : (
        <div className="backend-row">
          <span className="status-dot missing" />
          <span>计算后端</span>
          <strong>checking</strong>
        </div>
      )}
    </div>
  );
}

function TaskButton({
  definition,
  record,
  onRun,
  onRetry,
  onConfigure,
  openModal,
  onViewResult,
}: {
  definition: TaskDefinition;
  record?: CachedResult;
  onRun: () => void;
  onRetry?: () => void;
  onConfigure?: () => void;
  openModal: (modal: ModalState) => void;
  onViewResult?: () => void;
}) {
  const status = taskStatusForRecord(record);
  const icon = status === "running"
    ? <Loader2 size={16} className="spin" />
    : status === "succeeded"
      ? <CheckCircle2 size={16} />
      : status === "failed"
        ? <XCircle size={16} />
        : null;

  function handleClick() {
    if (!record || status === "idle") {
      onRun();
      return;
    }
    if (status === "failed") {
      openModal({
        kind: "task-error",
        title: `${definition.label}失败`,
        record,
        onRetry: onRetry ?? onRun,
        onConfigure,
      });
      return;
    }
    if (status === "succeeded" && onViewResult) {
      onViewResult();
      return;
    }
    openModal({
      kind: "result",
      title: definition.label,
      result: resultForRecord(record),
      onRecompute: onRetry ?? onRun,
      onConfigure,
    });
  }

  return (
    <button
      className={`task-button task-status-${status}`}
      onClick={handleClick}
      title={taskStatusLabel(status)}
    >
      <span>{definition.label}</span>
      {icon}
    </button>
  );
}

function CellTasks({
  selected,
  openModal,
}: {
  selected: Extract<SelectedObject, { kind: "cell" }>;
  openModal: (modal: ModalState) => void;
}) {
  return (
    <div className="task-group">
      <h3>{selected.cell.title}</h3>
      <button className="secondary-task-button" onClick={() => openModal({ kind: "result", title: "单元数据", result: selected.cell })}>查看单元数据</button>
      {selected.cell.type === "route" && (
        <button className="secondary-task-button" onClick={() => openModal({ kind: "result", title: "路线报告", result: { note: "路线级报告沿用后端 report_markdown；下一步可在此接入 PDF/Markdown 导出。" } })}>
          查看路线报告
        </button>
      )}
    </div>
  );
}

function MoleculeTasks({
  selected,
  workspace,
  runTask,
  openModal,
  jobs,
  onSave,
  refreshJobs,
  computeStatus,
}: {
  selected: Extract<SelectedObject, { kind: "molecule" }>;
  workspace: Workspace | null;
  runTask: RunTask;
  openModal: (modal: ModalState) => void;
  jobs: GaussianJob[];
  onSave: (workspace?: Workspace | null) => Promise<void>;
  refreshJobs: () => Promise<void>;
  computeStatus: ComputeStatus | null;
}) {
  const { molecule, component } = selected;
  const targetSmiles = component?.smiles ?? molecule.smiles;
  const targetLabel = component?.label ?? molecule.label;
  const [gaussianConfigOpen, setGaussianConfigOpen] = useState(false);
  const moleculeRouteSets = workspace?.route_candidate_sets?.filter((set) => set.target_smiles === targetSmiles) ?? [];
  const propertiesTask = makeTaskDefinition(selected, "molecule-properties", "计算分子性质（RDKit + OPERA）", "RDKit + OPERA");
  const descriptorsTask = makeTaskDefinition(selected, "molecule-descriptors", "计算分子描述符（RDKit）", "RDKit");
  const xtbTask = makeTaskDefinition(selected, "xtb-geometry-energy", "计算几何优化与能量（xTB）", "xTB");
  const crestTask = makeTaskDefinition(selected, "crest-conformers", "搜索低能构象（CREST）", "CREST");
  const routeTask = makeTaskDefinition(selected, "retrosynthesis", "预测逆合成路线（AiZynthFinder）", "AiZynthFinder");
  const gaussianTask = makeTaskDefinition(selected, "gaussian-opt-freq", "计算结构优化与频率（Gaussian）", "Gaussian");

  function recordFor(definition: TaskDefinition) {
    return selected.cell.results?.[taskResultKey(definition)];
  }

  async function predictRoute() {
    openModal({
      kind: "engine-select",
      backendStatus: computeStatus,
      onSelect: (engine) => {
        void startRoutePrediction(engine);
      }
    });
  }

  async function startRoutePrediction(engine: string) {
    let routeSet: RouteCandidateSet | null = null;
    let nextWorkspace = workspace;
    const taskEngineLabel = engine === "askcos" ? "ASKCOS" : "AiZynthFinder";
    const customRouteTask = {
      ...routeTask,
      label: `预测逆合成路线（${taskEngineLabel}）`,
      engine: engine
    };

    const prediction = await runTask(customRouteTask, async () => {
      const nextPrediction = await analyzeRoute(targetSmiles, 3, engine);
      routeSet = {
        id: `rcs-${Date.now()}`,
        target_smiles: nextPrediction.target_smiles ?? targetSmiles,
        status: nextPrediction.status ?? "unknown",
        created_at: new Date().toISOString(),
        candidates: nextPrediction.candidates ?? [],
        route_scores: nextPrediction.route_scores,
        feasibility: nextPrediction.feasibility,
        used_fallback: nextPrediction.used_fallback,
      };
      if (workspace) {
        nextWorkspace = {
          ...workspace,
          route_candidate_sets: [...(workspace.route_candidate_sets ?? []), routeSet],
        };
        await onSave(nextWorkspace);
      }
      return nextPrediction;
    }, { openResult: false, title: customRouteTask.label });
    if (!prediction) return;
    if (routeSet && nextWorkspace) {
      openModal({ kind: "routes", sets: [routeSet], workspace: nextWorkspace, selected, onSave, onRecompute: () => void predictRoute() });
    } else {
      openModal({ kind: "result", title: customRouteTask.label, result: prediction, onRecompute: () => void predictRoute() });
    }
  }

  async function submitGaussian(gjfText: string, config: Record<string, unknown>) {
    const job = await runTask(
      gaussianTask,
      () => submitGaussianJob(gjfText, workspace?.id, selected.cell.id, component?.id ?? molecule.id),
      {
        openResult: false,
        title: gaussianTask.label,
        config: { ...config, gjf_text: gjfText },
        onConfigure: () => setGaussianConfigOpen(true),
        statusFromResult: (result) => gaussianTaskStatus((result as GaussianJob).status),
      },
    );
    if (job) {
      setGaussianConfigOpen(false);
      await refreshJobs();
    }
  }

  function retryGaussian() {
    const record = recordFor(gaussianTask);
    const gjfText = typeof record?.config?.gjf_text === "string" ? record.config.gjf_text : null;
    if (!gjfText) {
      setGaussianConfigOpen(true);
      return;
    }
    void submitGaussian(gjfText, record?.config ?? {});
  }

  return (
    <div className="task-group">
      <h3>{targetLabel}</h3>
      {component && <small className="component-context">来自多分子块：{molecule.label}</small>}
      <code>{targetSmiles}</code>
      <TaskButton definition={propertiesTask} record={recordFor(propertiesTask)} onRun={() => void runTask(propertiesTask, () => predictProperties(targetSmiles, true), { title: propertiesTask.label })} openModal={openModal} />
      <TaskButton definition={descriptorsTask} record={recordFor(descriptorsTask)} onRun={() => void runTask(descriptorsTask, () => calculateDescriptors(targetSmiles), { title: descriptorsTask.label })} openModal={openModal} />
      <TaskButton definition={xtbTask} record={recordFor(xtbTask)} onRun={() => void runTask(xtbTask, () => runXtb(targetSmiles, 300), { title: xtbTask.label })} openModal={openModal} />
      <TaskButton definition={crestTask} record={recordFor(crestTask)} onRun={() => void runTask(crestTask, () => runCrest(targetSmiles, 1800), { title: crestTask.label })} openModal={openModal} />
      <TaskButton
        definition={routeTask}
        record={recordFor(routeTask)}
        onRun={() => void predictRoute()}
        onRetry={() => void predictRoute()}
        openModal={openModal}
        onViewResult={() => {
          if (workspace && moleculeRouteSets.length > 0) {
            openModal({ kind: "routes", sets: moleculeRouteSets, workspace, selected, onSave, onRecompute: () => void predictRoute() });
          } else {
            const record = recordFor(routeTask);
            if (record) {
              openModal({ kind: "result", title: routeTask.label, result: resultForRecord(record), onRecompute: () => void predictRoute() });
            }
          }
        }}
      />
      <TaskButton
        definition={gaussianTask}
        record={recordFor(gaussianTask)}
        onRun={() => setGaussianConfigOpen(true)}
        onRetry={retryGaussian}
        onConfigure={() => setGaussianConfigOpen(true)}
        openModal={openModal}
      />
      {gaussianConfigOpen && (
        <GaussianConfigModal
          smiles={targetSmiles}
          onClose={() => setGaussianConfigOpen(false)}
          onSubmit={(gjfText, config) => void submitGaussian(gjfText, config)}
        />
      )}
    </div>
  );
}

function ReactionTasks({
  selected,
  workspace,
  runTask,
  openModal,
  jobs,
  refreshJobs,
}: {
  selected: Extract<SelectedObject, { kind: "reaction" }>;
  workspace: Workspace | null;
  runTask: RunTask;
  openModal: (modal: ModalState) => void;
  jobs: GaussianJob[];
  refreshJobs: () => Promise<void>;
}) {
  const { reaction } = selected;
  const validationTask = makeTaskDefinition(selected, "reaction-validation", "校验反应可行性", undefined);
  const explanationTask = makeTaskDefinition(selected, "reaction-explanation", "解释反应", undefined);
  const mappingTask = makeTaskDefinition(selected, "reaction-mapping", "映射反应原子（RXNMapper）", "RXNMapper");
  const yieldTask = makeTaskDefinition(selected, "reaction-yield", "估算反应产率", undefined);
  const featuresTask = makeTaskDefinition(selected, "reaction-features", "计算反应特征", undefined);
  const tsComputeTask = makeTaskDefinition(selected, "transition-state-compute", "计算过渡态（Gaussian）", "Gaussian");
  const [tsConfigOpen, setTsConfigOpen] = useState(false);

  function recordFor(definition: TaskDefinition) {
    return selected.cell.results?.[taskResultKey(definition)];
  }

  return (
    <div className="task-group">
      <h3>{reaction.label}</h3>
      <code>{reaction.reaction_smiles}</code>
      <TaskButton definition={validationTask} record={recordFor(validationTask)} onRun={() => void runTask(validationTask, () => validateReaction(reaction.reaction_smiles, reaction.template), { title: validationTask.label })} openModal={openModal} />
      <TaskButton definition={explanationTask} record={recordFor(explanationTask)} onRun={() => void runTask(explanationTask, () => explainReaction(reaction.reaction_smiles, reaction.template), { title: explanationTask.label })} openModal={openModal} />
      <TaskButton definition={mappingTask} record={recordFor(mappingTask)} onRun={() => void runTask(mappingTask, () => mapReaction(reaction.reaction_smiles), { title: mappingTask.label })} openModal={openModal} />
      <TaskButton definition={yieldTask} record={recordFor(yieldTask)} onRun={() => void runTask(yieldTask, () => estimateYield(reaction.reaction_smiles, reaction.template), { title: yieldTask.label })} openModal={openModal} />
      <TaskButton definition={featuresTask} record={recordFor(featuresTask)} onRun={() => void runTask(featuresTask, () => reactionFeatures(reaction.reaction_smiles), { title: featuresTask.label })} openModal={openModal} />
      <TaskButton
        definition={tsComputeTask}
        record={recordFor(tsComputeTask)}
        onRun={() => setTsConfigOpen(true)}
        onRetry={() => setTsConfigOpen(true)}
        onConfigure={() => setTsConfigOpen(true)}
        openModal={openModal}
      />
      {tsConfigOpen && (
        <TransitionStateConfigModal
          reactionSmiles={reaction.reaction_smiles}
          reactionId={reaction.id}
          cellId={selected.cell.id}
          workspaceId={workspace?.id}
          onClose={() => setTsConfigOpen(false)}
          runTask={runTask}
          refreshJobs={refreshJobs}
          definition={tsComputeTask}
        />
      )}
    </div>
  );
}

interface TransitionStateConfigModalProps {
  reactionSmiles: string;
  reactionId: string;
  cellId: string;
  workspaceId?: string;
  onClose: () => void;
  runTask: RunTask;
  refreshJobs: () => Promise<void>;
  definition: TaskDefinition;
}

function TransitionStateConfigModal({
  reactionSmiles,
  reactionId,
  cellId,
  workspaceId,
  onClose,
  runTask,
  refreshJobs,
  definition,
}: TransitionStateConfigModalProps) {
  const [method, setMethod] = useState("B3LYP");
  const [basis, setBasis] = useState("6-31G(d)");
  const [charge, setCharge] = useState(0);
  const [multiplicity, setMultiplicity] = useState(1);
  const [jobType, setJobType] = useState("opt=(ts,calcfc,noeigentest) freq");
  const [components, setComponents] = useState<any[]>([]);
  const [plan, setPlan] = useState<TransitionStatePlanResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [mol3dReady, setMol3dReady] = useState(false);
  const [error, setError] = useState("");

  const [distanceX, setDistanceX] = useState(3.0);
  const [distanceY, setDistanceY] = useState(0.0);
  const [distanceZ, setDistanceZ] = useState(0.0);
  const [rotationX, setRotationX] = useState(0);
  const [rotationY, setRotationY] = useState(0);
  const [rotationZ, setRotationZ] = useState(0);

  const viewerRef = useRef<HTMLDivElement>(null);
  const [viewer, setViewer] = useState<any>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if ((window as any).$3Dmol) {
      setMol3dReady(true);
      return;
    }
    const script = document.createElement("script");
    script.src = "https://3dmol.org/build/3Dmol-min.js";
    script.async = true;
    script.onload = () => setMol3dReady(true);
    script.onerror = () => setError("3Dmol 渲染插件加载失败；请检查网络后重试。");
    document.body.appendChild(script);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getMoleculeCoordinates(reactionSmiles),
      fetchTsPlan(reactionSmiles),
    ])
      .then(([res, nextPlan]) => {
        if (!cancelled) {
          setComponents(res.components);
          setPlan(nextPlan);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(errorMessage(err));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reactionSmiles]);

  useEffect(() => {
    if (loading || !mol3dReady || components.length === 0 || !viewerRef.current || !(window as any).$3Dmol) return;
    const v = (window as any).$3Dmol.createViewer(viewerRef.current, { backgroundColor: "#f8fafc" });
    setViewer(v);
    return () => {
      v.clear();
    };
  }, [loading, mol3dReady, components]);

  const getCombinedXyz = useCallback(() => {
    if (components.length === 0) return "";
    let combinedAtoms: MoleculeCoordinates["atoms"] = [];

    const comp0 = components[0];
    combinedAtoms = combinedAtoms.concat(comp0.atoms);

    let c0 = { x: 0, y: 0, z: 0 };
    if (comp0.atoms.length > 0) {
      comp0.atoms.forEach((a: any) => { c0.x += a.x; c0.y += a.y; c0.z += a.z; });
      c0.x /= comp0.atoms.length;
      c0.y /= comp0.atoms.length;
      c0.z /= comp0.atoms.length;
    }

    for (let i = 1; i < components.length; i++) {
      const comp = components[i];
      if (comp.atoms.length === 0) continue;

      let c = { x: 0, y: 0, z: 0 };
      comp.atoms.forEach((a: any) => { c.x += a.x; c.y += a.y; c.z += a.z; });
      c.x /= comp.atoms.length;
      c.y /= comp.atoms.length;
      c.z /= comp.atoms.length;

      const radX = (rotationX * Math.PI) / 180;
      const radY = (rotationY * Math.PI) / 180;
      const radZ = (rotationZ * Math.PI) / 180;

      const cosX = Math.cos(radX), sinX = Math.sin(radX);
      const cosY = Math.cos(radY), sinY = Math.sin(radY);
      const cosZ = Math.cos(radZ), sinZ = Math.sin(radZ);

      const rotated = comp.atoms.map((a: any) => {
        let x = a.x - c.x;
        let y = a.y - c.y;
        let z = a.z - c.z;

        let y1 = y * cosX - z * sinX;
        let z1 = y * sinX + z * cosX;
        y = y1; z = z1;

        let x2 = x * cosY + z * sinY;
        let z2 = -x * sinY + z * cosY;
        x = x2; z = z2;

        let x3 = x * cosZ - y * sinZ;
        let y3 = x * sinZ + y * cosZ;
        x = x3; y = y3;

        return {
          element: a.element,
          x: x + c0.x + distanceX,
          y: y + c0.y + distanceY,
          z: z + c0.z + distanceZ,
        };
      });
      combinedAtoms = combinedAtoms.concat(rotated);
    }

    return combinedAtoms.map(a => `${a.element.padEnd(2)} ${a.x.toFixed(6).padStart(12)} ${a.y.toFixed(6).padStart(12)} ${a.z.toFixed(6).padStart(12)}`).join("\n");
  }, [components, distanceX, distanceY, distanceZ, rotationX, rotationY, rotationZ]);

  useEffect(() => {
    if (!viewer) return;
    const xyz = getCombinedXyz();
    if (!xyz) return;
    viewer.clear();
    viewer.addModel(xyz, "xyz");
    viewer.setStyle({}, { stick: { radius: 0.15 }, sphere: { scale: 0.25 } });
    viewer.zoomTo();
    viewer.render();
  }, [viewer, getCombinedXyz]);

  const gjfText = useMemo(() => {
    const coords = getCombinedXyz();
    return `%nprocshared=4\n%mem=4GB\n# ${jobType} ${method}/${basis}\n\nOrgSynFlow TS Search Job\n\n${charge} ${multiplicity}\n${coords}\n\n`;
  }, [jobType, method, basis, charge, multiplicity, getCombinedXyz]);

  async function handleSubmit() {
    onClose();
    await runTask(
      definition,
      () => submitGaussianJob(gjfText, workspaceId, cellId, reactionId),
      {
        openResult: false,
        title: definition.label,
        config: { gjf_text: gjfText, method, basis, job_type: jobType, charge, multiplicity },
        statusFromResult: (result) => gaussianTaskStatus((result as GaussianJob).status),
      }
    );
    await refreshJobs();
  }

  return (
    <div className="osf-modal-backdrop">
      <div className="osf-config-modal ts-config-modal">
        <div className="osf-modal-header">
          <strong>计算过渡态参数配置 (GaussView 辅助)</strong>
          <button className="close-button" onClick={onClose}>×</button>
        </div>
        <div className="osf-modal-body config-form">
          {loading ? (
            <p className="muted">正在生成 3D 初始坐标...</p>
          ) : error ? (
            <p className="error-box">{error}</p>
          ) : (
            <div className="ts-config-grid">
              <div className="ts-config-left">
                <h4>1. 量子化学参数</h4>
                <div className="form-row">
                  <label>方法 (Method)</label>
                  <select value={method} onChange={(e) => setMethod(e.target.value)}>
                    <option value="B3LYP">B3LYP (DFT)</option>
                    <option value="HF">HF (Ab Initio)</option>
                    <option value="PM6">PM6 (Semi-empirical)</option>
                    <option value="AM1">AM1 (Semi-empirical)</option>
                  </select>
                </div>
                <div className="form-row">
                  <label>基组 (Basis Set)</label>
                  <select value={basis} onChange={(e) => setBasis(e.target.value)}>
                    <option value="6-31G(d)">6-31G(d)</option>
                    <option value="6-31+G(d,p)">6-31+G(d,p)</option>
                    <option value="3-21G">3-21G</option>
                    <option value="STO-3G">STO-3G</option>
                  </select>
                </div>
                <div className="form-row">
                  <label>电荷 (Charge)</label>
                  <input type="number" value={charge} onChange={(e) => setCharge(parseInt(e.target.value) || 0)} />
                </div>
                <div className="form-row">
                  <label>多重度 (Multiplicity)</label>
                  <input type="number" min={1} value={multiplicity} onChange={(e) => setMultiplicity(parseInt(e.target.value) || 1)} />
                </div>
                <div className="form-row">
                  <label>作业类型 (Job Type)</label>
                  <input type="text" value={jobType} onChange={(e) => setJobType(e.target.value)} />
                </div>

                {plan && (
                  <div className="ts-plan-summary">
                    <strong>TS 搜索建议</strong>
                    <small>{plan.validation_level} · {plan.status}</small>
                    <code>{plan.gaussian_ts_route}</code>
                    {plan.warnings.slice(0, 2).map((warning) => <p key={warning}>{warning}</p>)}
                  </div>
                )}

                <h4>2. 可视化调整分子相对位置</h4>
                <div className="ts-slider-group">
                  <label>X 轴间距 (Å)</label>
                  <input type="range" min={1.5} max={8.0} step={0.1} value={distanceX} onChange={(e) => setDistanceX(parseFloat(e.target.value))} />
                  <span>{distanceX.toFixed(2)} Å</span>
                </div>
                <div className="ts-slider-group">
                  <label>Y 轴偏移 (Å)</label>
                  <input type="range" min={-5.0} max={5.0} step={0.1} value={distanceY} onChange={(e) => setDistanceY(parseFloat(e.target.value))} />
                  <span>{distanceY.toFixed(2)} Å</span>
                </div>
                <div className="ts-slider-group">
                  <label>Z 轴偏移 (Å)</label>
                  <input type="range" min={-5.0} max={5.0} step={0.1} value={distanceZ} onChange={(e) => setDistanceZ(parseFloat(e.target.value))} />
                  <span>{distanceZ.toFixed(2)} Å</span>
                </div>
                <div className="ts-slider-group">
                  <label>绕 X 轴旋转 (°)</label>
                  <input type="range" min={0} max={360} step={5} value={rotationX} onChange={(e) => setRotationX(parseInt(e.target.value))} />
                  <span>{rotationX}°</span>
                </div>
                <div className="ts-slider-group">
                  <label>绕 Y 轴旋转 (°)</label>
                  <input type="range" min={0} max={360} step={5} value={rotationY} onChange={(e) => setRotationY(parseInt(e.target.value))} />
                  <span>{rotationY}°</span>
                </div>
                <div className="ts-slider-group">
                  <label>绕 Z 轴旋转 (°)</label>
                  <input type="range" min={0} max={360} step={5} value={rotationZ} onChange={(e) => setRotationZ(parseInt(e.target.value))} />
                  <span>{rotationZ}°</span>
                </div>
              </div>
              <div className="ts-config-right">
                <h4>3D 构象预览 (类似 GaussView)</h4>
                <div className="ts-3d-viewer-container">
                  <div ref={viewerRef} className="ts-3d-viewer" />
                  {!mol3dReady && (
                    <div className="ts-3d-viewer-placeholder">正在加载 3D 渲染插件...</div>
                  )}
                </div>
                <h4>Gaussian 输入预览 (GJF)</h4>
                <pre style={{ maxHeight: "200px", overflow: "auto", fontSize: "11px", background: "#0f172a", color: "#38bdf8", padding: "10px", borderRadius: "6px" }}>
                  {gjfText}
                </pre>
              </div>
            </div>
          )}
        </div>
        <div className="osf-modal-footer">
          <button className="secondary-button" onClick={onClose}>取消</button>
          <button className="primary-button" disabled={loading || !!error} onClick={handleSubmit}>提交 Gaussian 计算</button>
        </div>
      </div>
    </div>
  );
}

function GaussianConfigModal({
  smiles,
  onClose,
  onSubmit,
}: {
  smiles: string;
  onClose: () => void;
  onSubmit: (gjfText: string, config: Record<string, unknown>) => void;
}) {
  const [jobType, setJobType] = useState("opt freq");
  const [method, setMethod] = useState("B3LYP");
  const [basis, setBasis] = useState("6-31G(d)");
  const [charge, setCharge] = useState(0);
  const [multiplicity, setMultiplicity] = useState(1);
  const [gjfText, setGjfText] = useState("");
  const [generating, setGenerating] = useState(true);
  const [generationError, setGenerationError] = useState("");

  useEffect(() => {
    let cancelled = false;
    makeGaussianInput(smiles)
      .then((gjf) => {
        if (!cancelled) setGjfText(gjf);
      })
      .catch((error) => {
        if (!cancelled) setGenerationError(errorMessage(error));
      })
      .finally(() => {
        if (!cancelled) setGenerating(false);
      });
    return () => {
      cancelled = true;
    };
  }, [smiles]);

  async function regenerate() {
    setGenerating(true);
    setGenerationError("");
    try {
      setGjfText(await makeGaussianInput(smiles, jobType, method, basis, charge, multiplicity));
    } catch (error) {
      setGenerationError(errorMessage(error));
    } finally {
      setGenerating(false);
    }
  }

  const config = { job_type: jobType, method, basis, charge, multiplicity };

  return (
    <div className="osf-modal-backdrop">
      <div className="osf-config-modal gaussian-config-modal">
        <div className="osf-modal-header">
          <strong>结构优化与频率计算（Gaussian）</strong>
          <button onClick={onClose}>关闭</button>
        </div>
        <div className="config-form">
          <label>
            结构
            <code>{smiles}</code>
          </label>
          <label>
            任务
            <select value={jobType} onChange={(event) => setJobType(event.target.value)}>
              <option value="opt freq">结构优化 + 频率</option>
              <option value="opt">结构优化</option>
              <option value="freq">频率</option>
              <option value="sp">单点能</option>
            </select>
          </label>
          <label>
            方法
            <input value={method} onChange={(event) => setMethod(event.target.value)} />
          </label>
          <label>
            基组
            <input value={basis} onChange={(event) => setBasis(event.target.value)} />
          </label>
          <label>
            电荷
            <input type="number" value={charge} onChange={(event) => setCharge(Number(event.target.value))} />
          </label>
          <label>
            自旋多重度
            <input type="number" min={1} value={multiplicity} onChange={(event) => setMultiplicity(Number(event.target.value))} />
          </label>
          <div className="gaussian-input-heading">
            <strong>Gaussian 输入</strong>
            <button className="ghost-button compact" onClick={() => void regenerate()} disabled={generating}>
              <RotateCcw size={14} /> {generating ? "正在生成" : "按当前参数重新生成"}
            </button>
          </div>
          <textarea
            className="gaussian-input-editor"
            value={gjfText}
            onChange={(event) => setGjfText(event.target.value)}
            aria-label="Gaussian 输入"
          />
          {generationError && <div className="error-box gaussian-error">{generationError}</div>}
        </div>
        <div className="osf-modal-footer">
          <button className="ghost-button" onClick={onClose}>关闭</button>
          <button className="primary-button" disabled={generating || !gjfText.trim()} onClick={() => onSubmit(gjfText, config)}>提交计算</button>
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="empty-state">
      <Atom size={36} />
      <p>新建工作区并添加分子、反应或路线单元。</p>
    </div>
  );
}

function defaultObjectsFor(type: CellType): { title: string; objects: Record<string, unknown> } {
  return {
    title: "Chem cell",
    objects: {
      molecules: [],
      reactions: [],
      routes: [],
    },
  };
}

function toNodes(cell: WorkspaceCell): Node[] {
  const molecules = cell.objects.molecules ?? [];
  const savedNodes = new Map((cell.canvas?.nodes ?? []).map((node) => [node.id, node]));
  return molecules.map((molecule, index) => ({
    id: molecule.id,
    type: "molecule",
    position: savedNodes.get(molecule.id)?.position ?? { x: 80 + (index % 3) * 260, y: 90 + Math.floor(index / 3) * 170 },
    data: { label: molecule.label, smiles: molecule.smiles },
  }));
}

function componentsForMolecule(molecule: MoleculeObject): MoleculeComponent[] {
  const parts = splitSmilesComponents(molecule.smiles);
  if (molecule.components?.length === parts.length) {
    return molecule.components.map((component, index) => ({
      ...component,
      id: `${molecule.id}:component:${index}`,
      parent_molecule_id: molecule.id,
      component_index: index,
      smiles: parts[index],
      label: component.label || `组分 ${index + 1}`,
    }));
  }
  return parts.map((smiles, index) => ({
    id: `${molecule.id}:component:${index}`,
    parent_molecule_id: molecule.id,
    component_index: index,
    smiles,
    label: `组分 ${index + 1}`,
  }));
}

function smilesComponentsContains(nodeSmiles: string, targetSmiles: string): boolean {
  const nodeParts = nodeSmiles.split(".").map(s => s.trim()).filter(Boolean);
  const targetParts = targetSmiles.split(".").map(s => s.trim()).filter(Boolean);
  return targetParts.every(p => nodeParts.includes(p));
}

function toEdges(cell: WorkspaceCell): Edge[] {
  if (cell.canvas?.edges?.length) {
    const nodeMap = new Map(toNodes(cell).map((node) => [node.id, node]));
    return cell.canvas.edges.map((edge) => normalizeEdge(edge, nodeMap));
  }
  const molecules = cell.objects.molecules ?? [];
  const reactions = cell.objects.reactions ?? [];
  const edges: Edge[] = [];
  reactions.forEach((reaction, reactionIndex) => {
    const [left, right] = reaction.reaction_smiles.split(">>");
    if (!left || !right) return;
    const sourceSmiles = normalizeReactionSide(left);
    const targetSmiles = normalizeReactionSide(right);
    const target = molecules.find((molecule) => smilesComponentsContains(molecule.smiles, targetSmiles));
    const source = molecules.find((molecule) => smilesComponentsContains(molecule.smiles, sourceSmiles));
    if (!target || !source) return;
    edges.push(makeCanvasEdge({
      id: `${reaction.id}-0`,
      source: source.id,
      target: target.id,
      sourceHandle: "right",
      targetHandle: "left",
      label: reaction.label || `Step ${reactionIndex + 1}`,
    }));
  });
  return edges;
}

function reactionFromEdge(cell: WorkspaceCell, edge: Edge): ReactionObject | undefined {
  return cell.objects.reactions?.find((reaction) => edge.id.startsWith(reaction.id));
}

function objectsFromCanvas(cell: WorkspaceCell, nodes: Node[], edges: Edge[]) {
  const molecules = nodes.map((node) => {
    const existing = cell.objects.molecules?.find((item) => item.id === node.id);
    return existing ?? { id: node.id, label: String(node.data?.label ?? node.id), smiles: String(node.data?.label ?? "") };
  });
  const reactionsById = new Map<string, ReactionObject>();
  edges.forEach((edge) => {
    const existing = reactionFromEdge(cell, edge);
    if (existing) reactionsById.set(existing.id, existing);
  });
  return { ...cell.objects, molecules, reactions: [...reactionsById.values()] };
}

async function fetchTsPlan(reactionSmiles: string): Promise<TransitionStatePlanResult | null> {
  try {
    const result = await planTs(reactionSmiles);
    if (result && typeof result === "object" && "validation_level" in result) {
      return result as TransitionStatePlanResult;
    }
  } catch {
    return null;
  }
  return null;
}

function normalizeEdge(edge: Edge, nodeMap?: Map<string, Node>): Edge {
  const sourceNode = nodeMap?.get(edge.source);
  const targetNode = nodeMap?.get(edge.target);
  const endpointOverrides = sourceNode && targetNode
    ? endpointOverridesForEdge(edge, targetNode)
    : {};
  const route = nodeMap && sourceNode && targetNode
    ? chooseBestOrthogonalRoute(sourceNode, targetNode, [...nodeMap.values()], endpointOverrides)
    : {
        sourceHandle: normalizeMoleculeHandleId(edge.sourceHandle, "right"),
        targetHandle: normalizeMoleculeHandleId(edge.targetHandle, "left"),
        points: [],
      };
  return {
    ...edge,
    type: "orthogonal",
    className: edge.className ?? "canvas-edge",
    interactionWidth: edge.interactionWidth ?? 18,
    style: { stroke: "#0f172a", strokeWidth: 3, ...(edge.style ?? {}) },
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 15,
      height: 15,
      color: "#0f172a",
    },
    sourceHandle: route.sourceHandle,
    targetHandle: route.targetHandle,
    data: { ...(edge.data ?? {}), routePoints: route.points },
  };
}

function makeCanvasEdge(edge: Partial<Edge> & { source: string; target: string }): Edge {
  return {
    id: edge.id ?? `edge-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    type: "orthogonal",
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle,
    targetHandle: edge.targetHandle,
    label: edge.label,
    data: edge.data,
    className: "canvas-edge",
    interactionWidth: 18,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 15,
      height: 15,
      color: "#0f172a",
    },
    style: { stroke: "#0f172a", strokeWidth: 3, ...(edge.style ?? {}) },
  };
}

function routeEdgesForNodes(edges: Edge[], nodes: Node[]): Edge[] {
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  return edges.map((edge) => normalizeEdge(edge, nodeMap));
}

function chooseBestOrthogonalRoute(
  source: Node,
  target: Node,
  nodes: Node[],
  endpointOverrides: RouteEndpointOverrides = {},
): { sourceHandle: string; targetHandle: string; points: Point[] } {
  const sourceNodeRect = nodeRect(source);
  const targetNodeRect = nodeRect(target);
  const sourceRect = endpointOverrides.sourceRect ?? sourceNodeRect;
  const targetRect = endpointOverrides.targetRect ?? targetNodeRect;
  const obstacles = nodes
    .filter((node) => node.id !== source.id && node.id !== target.id)
    .map((node) => expandRect(nodeRect(node), 18))
    .concat(endpointOverrides.obstacles ?? []);
  const candidates: Array<{ sourceHandle: Side; targetHandle: Side; points: Point[] }> = [];

  for (const sourceHandle of sideOrder(sourceRect, targetRect)) {
    for (const targetHandle of sideOrder(targetRect, sourceRect)) {
      const sourcePoint = sideCenter(sourceRect, sourceHandle);
      const targetPoint = sideCenter(targetRect, targetHandle);
      const sourcePort = sidePort(sourceRect, sourceHandle, 28);
      const targetPort = sidePort(targetRect, targetHandle, 28);
      const middle = findOrthogonalPath(sourcePort, targetPort, obstacles);
      const points = simplifyPoints([sourcePoint, sourcePort, ...middle, targetPort, targetPoint]);
      candidates.push({ sourceHandle, targetHandle, points });
    }
  }

  candidates.sort((left, right) => compareRoutePoints(left.points, right.points));
  const best = candidates[0] ?? {
    sourceHandle: "right" as Side,
    targetHandle: "left" as Side,
    points: fallbackOrthogonalPath(sideCenter(sourceRect, "right"), sideCenter(targetRect, "left")),
  };
  return {
    sourceHandle: best.sourceHandle,
    targetHandle: best.targetHandle,
    points: best.points,
  };
}

function findOrthogonalPath(start: Point, end: Point, obstacles: NodeRect[]): Point[] {
  const xs = uniqueSorted([start.x, end.x, ...obstacles.flatMap((rect) => [rect.left, rect.right])]);
  const ys = uniqueSorted([start.y, end.y, ...obstacles.flatMap((rect) => [rect.top, rect.bottom])]);
  const points: Point[] = [];
  const indexByKey = new Map<string, number>();
  for (const x of xs) {
    for (const y of ys) {
      const point = { x, y };
      if (isPointInsideAnyRect(point, obstacles)) continue;
      indexByKey.set(pointKey(point), points.length);
      points.push(point);
    }
  }

  const startIndex = indexByKey.get(pointKey(start));
  const endIndex = indexByKey.get(pointKey(end));
  if (startIndex === undefined || endIndex === undefined) {
    return fallbackOrthogonalPath(start, end);
  }

  const neighbors = buildOrthogonalNeighbors(points, obstacles);
  const bestPath = runOrthogonalSearch(points, neighbors, startIndex, endIndex);
  return simplifyPoints(bestPath ?? fallbackOrthogonalPath(start, end));
}

function buildOrthogonalNeighbors(points: Point[], obstacles: NodeRect[]): number[][] {
  const neighbors = points.map(() => [] as number[]);
  const byY = new Map<number, number[]>();
  const byX = new Map<number, number[]>();
  points.forEach((point, index) => {
    byY.set(point.y, [...(byY.get(point.y) ?? []), index]);
    byX.set(point.x, [...(byX.get(point.x) ?? []), index]);
  });
  for (const indices of byY.values()) {
    indices.sort((a, b) => points[a].x - points[b].x);
    connectVisibleAdjacent(indices, points, obstacles, neighbors);
  }
  for (const indices of byX.values()) {
    indices.sort((a, b) => points[a].y - points[b].y);
    connectVisibleAdjacent(indices, points, obstacles, neighbors);
  }
  return neighbors;
}

function connectVisibleAdjacent(indices: number[], points: Point[], obstacles: NodeRect[], neighbors: number[][]): void {
  for (let index = 0; index < indices.length - 1; index += 1) {
    const left = indices[index];
    const right = indices[index + 1];
    if (segmentBlocked(points[left], points[right], obstacles)) continue;
    neighbors[left].push(right);
    neighbors[right].push(left);
  }
}

function runOrthogonalSearch(
  points: Point[],
  neighbors: number[][],
  startIndex: number,
  endIndex: number,
): Point[] | null {
  type SearchState = {
    index: number;
    direction: "h" | "v" | null;
    length: number;
    bends: number;
    completedSegments: number[];
    activeSegment: number;
    path: number[];
  };
  const queue: SearchState[] = [{
    index: startIndex,
    direction: null,
    length: 0,
    bends: 0,
    completedSegments: [],
    activeSegment: 0,
    path: [startIndex],
  }];
  const bestByState = new Map<string, SearchState>();

  while (queue.length) {
    queue.sort(compareSearchStates);
    const state = queue.shift()!;
    const key = `${state.index}:${state.direction ?? "none"}`;
    const previous = bestByState.get(key);
    if (previous && compareSearchStates(previous, state) <= 0) continue;
    bestByState.set(key, state);
    if (state.index === endIndex) {
      return state.path.map((index) => points[index]);
    }
    for (const nextIndex of neighbors[state.index]) {
      if (state.path.includes(nextIndex)) continue;
      const current = points[state.index];
      const next = points[nextIndex];
      const direction = current.x === next.x ? "v" : "h";
      const distance = manhattan(current, next);
      const sameDirection = state.direction === null || state.direction === direction;
      const nextState: SearchState = {
        index: nextIndex,
        direction,
        length: state.length + distance,
        bends: sameDirection ? state.bends : state.bends + 1,
        completedSegments: sameDirection ? state.completedSegments : [...state.completedSegments, state.activeSegment],
        activeSegment: sameDirection ? state.activeSegment + distance : distance,
        path: [...state.path, nextIndex],
      };
      queue.push(nextState);
    }
  }
  return null;
}

function compareSearchStates(left: {
  length: number;
  bends: number;
  completedSegments: number[];
  activeSegment: number;
}, right: {
  length: number;
  bends: number;
  completedSegments: number[];
  activeSegment: number;
}): number {
  if (left.length !== right.length) return left.length - right.length;
  if (left.bends !== right.bends) return left.bends - right.bends;
  return compareSegmentPreference([...left.completedSegments, left.activeSegment], [...right.completedSegments, right.activeSegment]);
}

function compareRoutePoints(left: Point[], right: Point[]): number {
  const leftLengths = routeSegmentLengths(left);
  const rightLengths = routeSegmentLengths(right);
  const leftLength = leftLengths.reduce((sum, value) => sum + value, 0);
  const rightLength = rightLengths.reduce((sum, value) => sum + value, 0);
  if (leftLength !== rightLength) return leftLength - rightLength;
  const leftBends = Math.max(0, leftLengths.length - 1);
  const rightBends = Math.max(0, rightLengths.length - 1);
  if (leftBends !== rightBends) return leftBends - rightBends;
  return compareSegmentPreference(leftLengths, rightLengths);
}

function compareSegmentPreference(left: number[], right: number[]): number {
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const leftValue = left[index] ?? 0;
    const rightValue = right[index] ?? 0;
    if (leftValue !== rightValue) return rightValue - leftValue;
  }
  return 0;
}

function routeSegmentLengths(points: Point[]): number[] {
  const simplified = simplifyPoints(points);
  const lengths: number[] = [];
  for (let index = 1; index < simplified.length; index += 1) {
    lengths.push(manhattan(simplified[index - 1], simplified[index]));
  }
  return lengths;
}

function sideOrder(source: NodeRect, target: NodeRect): Side[] {
  const sourceCenter = rectCenter(source);
  const targetCenter = rectCenter(target);
  const dx = targetCenter.x - sourceCenter.x;
  const dy = targetCenter.y - sourceCenter.y;
  const horizontal: Side[] = dx >= 0 ? ["right", "left"] : ["left", "right"];
  const vertical: Side[] = dy >= 0 ? ["bottom", "top"] : ["top", "bottom"];
  return Math.abs(dx) >= Math.abs(dy)
    ? [horizontal[0], vertical[0], vertical[1], horizontal[1]]
    : [vertical[0], horizontal[0], horizontal[1], vertical[1]];
}

function nodeRect(node: Node): NodeRect {
  const width = typeof node.measured?.width === "number" ? node.measured.width : estimatedNodeWidth(node);
  const height = typeof node.measured?.height === "number" ? node.measured.height : 142;
  return {
    id: node.id,
    left: node.position.x,
    right: node.position.x + width,
    top: node.position.y,
    bottom: node.position.y + height,
  };
}

function endpointOverridesForEdge(edge: Pick<Edge, "data">, targetNode: Node): RouteEndpointOverrides {
  const targetComponentIndex = Number(edge.data?.targetComponentIndex);
  const targetComponentRect = Number.isInteger(targetComponentIndex)
    ? componentRectForNode(targetNode, targetComponentIndex)
    : null;
  if (!targetComponentRect) return {};
  return {
    targetRect: targetComponentRect,
    obstacles: componentObstacleRects(targetNode, targetComponentIndex),
  };
}

function componentRectForNode(node: Node, componentIndex: number): NodeRect | null {
  const parts = splitSmilesComponents(String(node.data?.smiles ?? ""));
  if (parts.length <= 1 || componentIndex < 0 || componentIndex >= parts.length) return null;
  const rect = nodeRect(node);
  const componentWidth = 172;
  const componentGap = 6;
  const componentHeight = 128;
  const left = rect.left + 8 + componentIndex * (componentWidth + componentGap);
  const top = rect.top + 8;
  return {
    id: `${node.id}:component:${componentIndex}`,
    left,
    right: left + componentWidth,
    top,
    bottom: top + componentHeight,
  };
}

function componentObstacleRects(node: Node, targetComponentIndex: number): NodeRect[] {
  const parts = splitSmilesComponents(String(node.data?.smiles ?? ""));
  if (parts.length <= 1) return [];
  return parts
    .map((_, index) => index)
    .filter((index) => index !== targetComponentIndex)
    .map((index) => componentRectForNode(node, index))
    .filter((rect): rect is NodeRect => !!rect)
    .map((rect) => expandRect(rect, 14));
}

function estimatedNodeWidth(node: Node): number {
  const componentCount = splitSmilesComponents(String(node.data?.smiles ?? "")).length;
  return componentCount > 1
    ? Math.min(590, componentCount * 172 + (componentCount - 1) * 6 + 18)
    : 190;
}

function rectCenter(rect: NodeRect): Point {
  return {
    x: (rect.left + rect.right) / 2,
    y: (rect.top + rect.bottom) / 2,
  };
}

function sideCenter(rect: NodeRect, side: Side): Point {
  const center = rectCenter(rect);
  if (side === "top") return { x: center.x, y: rect.top };
  if (side === "right") return { x: rect.right, y: center.y };
  if (side === "bottom") return { x: center.x, y: rect.bottom };
  return { x: rect.left, y: center.y };
}

function sidePort(rect: NodeRect, side: Side, offset: number): Point {
  const point = sideCenter(rect, side);
  if (side === "top") return { x: point.x, y: point.y - offset };
  if (side === "right") return { x: point.x + offset, y: point.y };
  if (side === "bottom") return { x: point.x, y: point.y + offset };
  return { x: point.x - offset, y: point.y };
}

function expandRect(rect: NodeRect, margin: number): NodeRect {
  return {
    id: rect.id,
    left: rect.left - margin,
    right: rect.right + margin,
    top: rect.top - margin,
    bottom: rect.bottom + margin,
  };
}

function isPointInsideAnyRect(point: Point, rects: NodeRect[]): boolean {
  return rects.some((rect) => point.x > rect.left && point.x < rect.right && point.y > rect.top && point.y < rect.bottom);
}

function segmentBlocked(start: Point, end: Point, rects: NodeRect[]): boolean {
  if (start.x === end.x) {
    const top = Math.min(start.y, end.y);
    const bottom = Math.max(start.y, end.y);
    return rects.some((rect) => start.x > rect.left && start.x < rect.right && bottom > rect.top && top < rect.bottom);
  }
  if (start.y === end.y) {
    const left = Math.min(start.x, end.x);
    const right = Math.max(start.x, end.x);
    return rects.some((rect) => start.y > rect.top && start.y < rect.bottom && right > rect.left && left < rect.right);
  }
  return true;
}

function fallbackOrthogonalPath(start: Point, end: Point): Point[] {
  if (start.x === end.x || start.y === end.y) return [start, end];
  return simplifyPoints([start, { x: end.x, y: start.y }, end]);
}

function simplifyPoints(points: Point[]): Point[] {
  const deduped = points.filter((point, index) => index === 0 || point.x !== points[index - 1].x || point.y !== points[index - 1].y);
  const simplified: Point[] = [];
  for (const point of deduped) {
    const previous = simplified[simplified.length - 1];
    const beforePrevious = simplified[simplified.length - 2];
    if (beforePrevious && previous && ((beforePrevious.x === previous.x && previous.x === point.x) || (beforePrevious.y === previous.y && previous.y === point.y))) {
      simplified[simplified.length - 1] = point;
    } else {
      simplified.push(point);
    }
  }
  return simplified;
}

function uniqueSorted(values: number[]): number[] {
  return [...new Set(values.map((value) => Math.round(value * 1000) / 1000))].sort((left, right) => left - right);
}

function pointKey(point: Point): string {
  return `${point.x},${point.y}`;
}

function manhattan(start: Point, end: Point): number {
  return Math.abs(end.x - start.x) + Math.abs(end.y - start.y);
}

function pointsToSvgPath(points: Point[]): string {
  const simplified = simplifyPoints(points);
  if (!simplified.length) return "";
  const [first, ...rest] = simplified;
  return `M ${first.x},${first.y}${rest.map((point) => `L ${point.x},${point.y}`).join("")}`;
}

function midPointOnPath(points: Point[]): Point {
  const simplified = simplifyPoints(points);
  const lengths = routeSegmentLengths(simplified);
  const total = lengths.reduce((sum, value) => sum + value, 0);
  let remaining = total / 2;
  for (let index = 1; index < simplified.length; index += 1) {
    const start = simplified[index - 1];
    const end = simplified[index];
    const length = manhattan(start, end);
    if (remaining <= length) {
      const ratio = length === 0 ? 0 : remaining / length;
      return { x: start.x + (end.x - start.x) * ratio, y: start.y + (end.y - start.y) * ratio };
    }
    remaining -= length;
  }
  return simplified[Math.max(0, simplified.length - 1)] ?? { x: 0, y: 0 };
}

function OrthogonalEdge(props: EdgeProps) {
  const routePoints = Array.isArray(props.data?.routePoints) ? props.data.routePoints as Point[] : [
    { x: props.sourceX, y: props.sourceY },
    { x: props.targetX, y: props.targetY },
  ];
  const edgePath = pointsToSvgPath(routePoints);
  const labelPoint = midPointOnPath(routePoints);
  return (
    <BaseEdge
      {...props}
      path={edgePath}
      labelX={labelPoint.x}
      labelY={labelPoint.y}
    />
  );
}

function normalizeMoleculeHandleId(handleId: string | null | undefined, fallback: string): string {
  if (!handleId) return fallback;
  if (handleId === "right-source" || handleId === "right-a" || handleId === "right-b") return "right";
  if (handleId === "left-source" || handleId === "left-a" || handleId === "left-b") return "left";
  if (handleId === "top-a" || handleId === "top-b") return "top";
  if (handleId === "bottom-a" || handleId === "bottom-b") return "bottom";
  return moleculeHandles.some((handle) => handle.id === handleId) ? handleId : fallback;
}

function createMoleculeObject(smiles: string, index: number): MoleculeObject {
  const id = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? `mol-${crypto.randomUUID()}`
    : `mol-${Date.now()}-${index}-${Math.random().toString(16).slice(2)}`;
  return { id, label: smiles, smiles };
}

function normalizeReactionSmiles(reactionSmiles: string): string {
  const sides = reactionSmiles.split(">>");
  if (sides.length !== 2) return reactionSmiles.trim();
  return sides.map(normalizeReactionSide).join(">>");
}

function normalizeReactionSide(side: string): string {
  return splitReactionSide(side)
    .map((item) => item.trim())
    .filter(Boolean)
    .join(".");
}

function splitReactionSide(side: string): string[] {
  const parts: string[] = [];
  let buffer = "";
  let bracketDepth = 0;
  for (const char of side) {
    if (char === "[") bracketDepth += 1;
    if (char === "]") bracketDepth = Math.max(0, bracketDepth - 1);
    if (char === "+" && bracketDepth === 0) {
      parts.push(buffer);
      buffer = "";
      continue;
    }
    buffer += char;
  }
  parts.push(buffer);
  return parts;
}

function addRouteCandidateToCell(
  cell: WorkspaceCell,
  route: RouteCandidate,
  anchorMolecule: MoleculeObject | null,
  anchorComponent: MoleculeComponent | null = null,
): WorkspaceCell {
  const stamp = Date.now();
  let existingNodes = toNodes(cell);
  const existingEdges = toEdges(cell);
  const targetMol = route.molecules.find((m) => m.id === route.target_id);
  if (!targetMol) return cell;

  const anchorNode = anchorMolecule
    ? existingNodes.find((node) => node.id === anchorMolecule.id)
    : undefined;
  const targetLayout = route.layout?.nodes?.[targetMol.id];
  const routeLayouts = Object.values(route.layout?.nodes ?? {});
  const minimumLayoutX = routeLayouts.length ? Math.min(...routeLayouts.map((layout) => layout.x)) : 0;

  // Keep the synthesis route left-to-right. If the selected target is already
  // near the left edge, move the existing canvas right to make room for its
  // precursors instead of placing them on the product side and reversing arrows.
  let canvasShiftX = 0;
  if (anchorNode && targetLayout) {
    const prospectiveMinimumX = anchorNode.position.x + minimumLayoutX - targetLayout.x;
    canvasShiftX = Math.max(0, 40 - prospectiveMinimumX);
    if (canvasShiftX > 0) {
      existingNodes = existingNodes.map((node) => ({
        ...node,
        position: { ...node.position, x: node.position.x + canvasShiftX },
      }));
    }
  }

  let shiftedAnchorNode = anchorNode
    ? existingNodes.find((node) => node.id === anchorNode.id)
    : undefined;
  if (shiftedAnchorNode) {
    const anchorX = shiftedAnchorNode.position.x;
    const downstreamNodes = existingNodes.filter((node) => node.position.x > anchorX);
    const nearestDownstreamX = downstreamNodes.length
      ? Math.min(...downstreamNodes.map((node) => node.position.x))
      : null;
    const requiredDownstreamX = anchorX + estimatedNodeWidth(shiftedAnchorNode) + 70;
    const downstreamShiftX = nearestDownstreamX === null ? 0 : Math.max(0, requiredDownstreamX - nearestDownstreamX);
    if (downstreamShiftX > 0) {
      existingNodes = existingNodes.map((node) => (
        node.position.x > anchorX
          ? { ...node, position: { ...node.position, x: node.position.x + downstreamShiftX } }
          : node
      ));
      shiftedAnchorNode = existingNodes.find((node) => node.id === shiftedAnchorNode!.id);
    }
  }
  const baseX = shiftedAnchorNode && targetLayout
    ? shiftedAnchorNode.position.x - targetLayout.x
    : 80 + existingNodes.length * 36;
  const baseY = shiftedAnchorNode && targetLayout
    ? shiftedAnchorNode.position.y - targetLayout.y
    : 80 + existingNodes.length * 20;
  const routeNodes: Node[] = [];
  const routeMolecules: MoleculeObject[] = [];
  const routeReactions: ReactionObject[] = [];
  const routeEdges: Edge[] = [];
  const routeNodeIdByMoleculeId = new Map<string, string>();
  const targetComponentIndex = shiftedAnchorNode && anchorComponent?.parent_molecule_id === shiftedAnchorNode.id
    ? anchorComponent.component_index
    : null;

  const productIds = new Set(route.steps.map((step) => step.product_id));
  const individualMoleculeIds = new Set<string>([route.target_id, ...productIds]);
  route.steps.forEach((step) => {
    if (step.precursor_ids.length === 1) {
      individualMoleculeIds.add(step.precursor_ids[0]);
    }
  });

  // The route candidate keeps the full molecule graph, but the canvas should
  // represent each synthetic operation as one reactant block pointing to the
  // product. A + B >> C therefore becomes a single A.B node connected to C.
  route.molecules.forEach((molecule, index) => {
    if (!individualMoleculeIds.has(molecule.id)) return;
    if (molecule.id === route.target_id && shiftedAnchorNode) {
      routeNodeIdByMoleculeId.set(molecule.id, shiftedAnchorNode.id);
      return;
    }
    const nodeId = `route-${stamp}-${route.id}-molecule-${molecule.id}`;
    const layout = route.layout?.nodes?.[molecule.id];
    routeNodeIdByMoleculeId.set(molecule.id, nodeId);
    routeMolecules.push({ id: nodeId, label: molecule.name || molecule.smiles, smiles: molecule.smiles });
    routeNodes.push({
      id: nodeId,
      type: "molecule",
      position: {
        x: baseX + (layout?.x ?? index * 260),
        y: baseY + (layout?.y ?? index * 110),
      },
      data: { label: molecule.name || molecule.smiles, smiles: molecule.smiles },
    });
  });

  let allRouteNodes = [...existingNodes, ...routeNodes];
  route.steps.forEach((step, stepIndex) => {
    const productNodeId = routeNodeIdByMoleculeId.get(step.product_id);
    const productMol = route.molecules.find((m) => m.id === step.product_id);
    if (!productNodeId || !productMol) return;
    const precursors = step.precursor_ids
      .map((id) => route.molecules.find((m) => m.id === id))
      .filter(Boolean);
    const precursorSmiles = precursors.map((p) => p!.smiles).join(".");
    const rxnId = `rxn-route-${stamp}-${route.id}-${step.id}-${stepIndex}`;
    routeReactions.push({
      id: rxnId,
      label: step.template || `Route step ${stepIndex + 1}`,
      reaction_smiles: normalizeReactionSmiles(step.reaction_smiles || `${precursorSmiles}>>${productMol.smiles}`),
      template: step.template ?? undefined,
    });

    let sourceNodeId: string | undefined;
    if (step.precursor_ids.length > 1) {
      sourceNodeId = `route-${stamp}-${route.id}-step-${step.id}-reactants`;
      const precursorLayouts = step.precursor_ids
        .map((id) => route.layout?.nodes?.[id])
        .filter(Boolean) as Array<{ x: number; y: number }>;
      const fallbackX = targetLayout ? targetLayout.x - 260 : stepIndex * 260;
      const fallbackY = targetLayout ? targetLayout.y + stepIndex * 120 : stepIndex * 110;
      const layoutX = precursorLayouts.length
        ? Math.min(...precursorLayouts.map((layout) => layout.x))
        : fallbackX;
      const layoutY = precursorLayouts.length
        ? precursorLayouts.reduce((sum, layout) => sum + layout.y, 0) / precursorLayouts.length
        : fallbackY;
      routeMolecules.push({ id: sourceNodeId, label: precursorSmiles, smiles: precursorSmiles });
      const sourceNode: Node = {
        id: sourceNodeId,
        type: "molecule",
        position: { x: baseX + layoutX, y: baseY + layoutY },
        data: { label: precursorSmiles, smiles: precursorSmiles },
      };
      routeNodes.push(sourceNode);
      allRouteNodes = [...allRouteNodes, sourceNode];
    } else {
      sourceNodeId = routeNodeIdByMoleculeId.get(step.precursor_ids[0]);
    }

    if (sourceNodeId) {
      const sourceNode = allRouteNodes.find((node) => node.id === sourceNodeId);
      const targetNode = allRouteNodes.find((node) => node.id === productNodeId);
      const edgeData = targetComponentIndex !== null && productNodeId === shiftedAnchorNode?.id && step.product_id === route.target_id
        ? { targetComponentIndex }
        : undefined;
      const endpointOverrides = targetNode && edgeData
        ? endpointOverridesForEdge({ data: edgeData }, targetNode)
        : {};
      const routePath = sourceNode && targetNode
        ? chooseBestOrthogonalRoute(sourceNode, targetNode, allRouteNodes, endpointOverrides)
        : null;
      routeEdges.push(makeCanvasEdge({
        id: `${rxnId}-edge`,
        source: sourceNodeId,
        target: productNodeId,
        sourceHandle: routePath?.sourceHandle ?? "right",
        targetHandle: routePath?.targetHandle ?? "left",
        label: step.template || `Step ${stepIndex + 1}`,
        data: edgeData,
      }));
    }
  });

  return {
    ...cell,
    objects: {
      ...cell.objects,
      molecules: [...(cell.objects.molecules ?? []), ...routeMolecules],
      reactions: [...(cell.objects.reactions ?? []), ...routeReactions],
      routes: [...(cell.objects.routes ?? []), { id: `route-${stamp}-${route.id}`, label: route.title, route }],
    },
    canvas: {
      nodes: [...existingNodes, ...routeNodes],
      edges: [...existingEdges, ...routeEdges],
    },
  };
}

function createRouteCellFromCandidate(route: RouteCandidate): WorkspaceCell {
  const now = new Date().toISOString();
  const id = `cell-route-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const emptyCell: WorkspaceCell = {
    id,
    type: "route",
    title: route.title || "Predicted route",
    created_at: now,
    updated_at: now,
    canvas: { nodes: [], edges: [] },
    objects: { molecules: [], reactions: [], routes: [{ id: route.id, label: route.title, route }] },
    results: {},
  };
  return addRouteCandidateToCell(emptyCell, route, null);
}

type DisplayTaskStatus = "idle" | "running" | "succeeded" | "failed";

function taskStatus(status: string | undefined): DisplayTaskStatus {
  if (status === "queued" || status === "running") return "running";
  if (status === "succeeded" || status === "completed" || status === "available") return "succeeded";
  if (status === "failed" || status === "cancelled" || status === "error") return "failed";
  return "idle";
}

function taskStatusFromResult(result: unknown): CachedResult["status"] {
  if (!isPlainObject(result)) return "succeeded";
  if (result.available === false || ["failed", "unavailable", "error", "cancelled"].includes(String(result.status))) {
    return "failed";
  }
  return "succeeded";
}

function taskStatusForRecord(record: CachedResult | undefined): DisplayTaskStatus {
  const storedStatus = taskStatus(record?.status);
  if (storedStatus === "succeeded" && taskStatusFromResult(record?.payload) === "failed") return "failed";
  return storedStatus;
}

function resultErrorMessage(result: unknown): string | undefined {
  if (!isPlainObject(result)) return undefined;
  if (typeof result.reason === "string" && result.reason.trim()) return result.reason;
  if (typeof result.error === "string" && result.error.trim()) return result.error;
  return undefined;
}

function gaussianTaskStatus(status: string): CachedResult["status"] {
  return taskStatus(status) === "idle" ? "failed" : taskStatus(status);
}

function taskStatusLabel(status: DisplayTaskStatus): string {
  if (status === "running") return "计算中";
  if (status === "succeeded") return "已完成";
  if (status === "failed") return "计算失败";
  return "未计算";
}

function makeTaskDefinition(
  selected: Exclude<SelectedObject, null>,
  id: string,
  label: string,
  engine?: string,
): TaskDefinition {
  const object = selected.kind === "molecule"
    ? selected.component ?? selected.molecule
    : selected.kind === "reaction"
      ? selected.reaction
      : selected.cell;
  return {
    id,
    label,
    engine,
    cellId: selected.cell.id,
    objectId: object.id,
    objectKind: selected.kind,
    objectLabel: "label" in object ? object.label : object.title,
  };
}

function taskResultKey(definition: TaskDefinition): string {
  return `${definition.objectKind}:${definition.objectId}:${definition.id}`;
}

function mergeTaskRecord(workspace: Workspace, cellId: string, key: string, record: CachedResult): Workspace {
  return {
    ...workspace,
    cells: workspace.cells.map((cell) => cell.id === cellId
      ? { ...cell, results: { ...(cell.results ?? {}), [key]: record } }
      : cell),
  };
}

function taskRecordFromJob(record: CachedResult, job: GaussianJob): CachedResult {
  const status = gaussianTaskStatus(job.status);
  return {
    ...record,
    status,
    updated_at: job.finished_at ?? job.started_at ?? job.created_at ?? new Date().toISOString(),
    payload: job,
    error: status === "failed" ? job.error ?? "Gaussian 计算失败。" : undefined,
    job_id: job.job_id,
  };
}

function bindSelection(selected: SelectedObject, workspace: Workspace | null): SelectedObject {
  if (!selected || !workspace) return null;
  const cell = workspace.cells.find((item) => item.id === selected.cell.id);
  if (!cell) return null;
  if (selected.kind === "cell") return { kind: "cell", cell };
  if (selected.kind === "molecule") {
    const molecule = cell.objects.molecules?.find((item) => item.id === selected.molecule.id);
    if (!molecule) return null;
    const component = selected.component
      ? componentsForMolecule(molecule).find((item) => item.component_index === selected.component?.component_index)
      : undefined;
    return { kind: "molecule", cell, molecule, component };
  }
  const reaction = cell.objects.reactions?.find((item) => item.id === selected.reaction.id);
  return reaction ? { kind: "reaction", cell, reaction } : null;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (error && typeof error === "object") {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (detail) return String(detail);
  }
  return String(error);
}

function formatTaskTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function resultForRecord(record: CachedResult): unknown {
  if (record.payload && typeof record.payload === "object") {
    return {
      ...(record.payload as Record<string, unknown>),
      _task_config: record.config,
      _task_meta: {
        task_id: record.task_id,
        task_label: record.task_label,
        engine: record.engine,
        object_label: record.object_label,
      },
    };
  }
  return record.payload ?? record;
}

function isPlainObject(value: unknown): value is Record<string, any> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function extractMolecularGeometry(value: unknown): ExtractedGeometry | null {
  const candidates = collectGeometryCandidates(value);
  for (const candidate of candidates) {
    const xyz = candidate.includes("\n") ? normalizeGeometryText(candidate) : "";
    if (!xyz) continue;
    const atomCount = countXyzAtoms(xyz);
    if (atomCount > 0) return { xyz, atomCount };
  }
  return null;
}

function collectGeometryCandidates(value: unknown, depth = 0): string[] {
  if (depth > 5 || value == null) return [];
  if (typeof value === "string") {
    if (looksLikeXyz(value) || looksLikeGaussianInput(value)) return [value];
    return [];
  }
  if (Array.isArray(value)) return value.flatMap((item) => collectGeometryCandidates(item, depth + 1));
  if (!isPlainObject(value)) return [];

  const directKeys = ["input_xyz", "xyz", "coordinates", "gjf_text", "gjf", "input"];
  const direct = directKeys
    .map((key) => value[key])
    .filter((item): item is string => typeof item === "string" && (looksLikeXyz(item) || looksLikeGaussianInput(item)));
  const nested = Object.entries(value)
    .filter(([key]) => !["stdout", "stderr", "reason"].includes(key))
    .flatMap(([, item]) => collectGeometryCandidates(item, depth + 1));
  return [...direct, ...nested];
}

function normalizeGeometryText(text: string): string {
  if (looksLikeXyz(text)) return normalizeXyz(text);
  if (looksLikeGaussianInput(text)) return gaussianInputToXyz(text);
  return "";
}

function looksLikeXyz(text: string): boolean {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (lines.length < 2) return false;
  if (/^\d+$/.test(lines[0])) return lines.slice(2).some(isAtomCoordinateLine);
  return lines.some(isAtomCoordinateLine);
}

function looksLikeGaussianInput(text: string): boolean {
  return /^\s*-?\d+\s+\d+\s*$/m.test(text) && text.split(/\r?\n/).some(isAtomCoordinateLine);
}

function normalizeXyz(text: string): string {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const atomLines = /^\d+$/.test(lines[0]) ? lines.slice(2).filter(isAtomCoordinateLine) : lines.filter(isAtomCoordinateLine);
  if (atomLines.length === 0) return "";
  return [String(atomLines.length), "OrgSynFlow geometry", ...atomLines.map(normalizeAtomLine)].join("\n");
}

function gaussianInputToXyz(text: string): string {
  const lines = text.split(/\r?\n/);
  const chargeIndex = lines.findIndex((line) => /^\s*-?\d+\s+\d+\s*$/.test(line));
  if (chargeIndex < 0) return "";
  const atomLines: string[] = [];
  for (const line of lines.slice(chargeIndex + 1)) {
    if (!line.trim()) break;
    if (isAtomCoordinateLine(line)) atomLines.push(normalizeAtomLine(line));
  }
  if (atomLines.length === 0) return "";
  return [String(atomLines.length), "OrgSynFlow Gaussian input geometry", ...atomLines].join("\n");
}

function isAtomCoordinateLine(line: string): boolean {
  return /^\s*([A-Z][a-z]?|\d+)\s+[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?\s+[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?\s+[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?/.test(line);
}

function normalizeAtomLine(line: string): string {
  const parts = line.trim().split(/\s+/);
  return `${parts[0]} ${parts[1]} ${parts[2]} ${parts[3]}`;
}

function countXyzAtoms(xyz: string): number {
  const first = xyz.split(/\r?\n/)[0]?.trim();
  const parsed = Number.parseInt(first, 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

function extractLogHighlights(text: string): string[] {
  if (!text.trim()) return [];
  const items: string[] = [];
  const totalEnergy = lastRegex(text, /TOTAL ENERGY\s+(-?\d+\.\d+)/gi);
  if (totalEnergy) items.push(`总能量: ${totalEnergy} Hartree`);
  const scfEnergy = lastRegex(text, /SCF Done:\s+E\([^)]+\)\s+=\s+(-?\d+\.\d+)/gi);
  if (scfEnergy) items.push(`SCF 最终能量: ${scfEnergy} Hartree`);
  const gibbs = lastRegex(text, /Sum of electronic and thermal Free Energies=\s+(-?\d+\.\d+)/gi);
  if (gibbs) items.push(`Gibbs 自由能: ${gibbs} Hartree`);
  const gap = lastRegex(text, /HOMO-LUMO GAP\s+(-?\d+\.\d+)/gi);
  if (gap) items.push(`HOMO-LUMO gap: ${gap}`);
  const frequencies = [...text.matchAll(/Frequencies --\s+([^\n]+)/g)]
    .flatMap((match) => match[1].trim().split(/\s+/).map(Number))
    .filter((value) => Number.isFinite(value));
  if (frequencies.length > 0) {
    const imaginary = frequencies.filter((value) => value < 0);
    items.push(`频率: ${frequencies.length} 个，虚频 ${imaginary.length} 个`);
  }
  if (/Normal termination/i.test(text)) items.push("Gaussian 正常结束。");
  if (/ERROR|FAILED|abnormal termination/i.test(text)) items.push("日志中检测到错误或异常终止，需要检查原始日志。");
  return [...new Set(items)].slice(0, 8);
}

function lastRegex(text: string, pattern: RegExp): string | null {
  const matches = [...text.matchAll(pattern)];
  return matches.length ? matches[matches.length - 1][1] : null;
}

function summarizeUnknownResult(result: unknown): {
  metrics: Array<[string, string]>;
  messages: string[];
  sections: Array<{ title: string; items: Array<[string, string]> }>;
} {
  if (!isPlainObject(result)) return { metrics: [], messages: [String(result)], sections: [] };
  const metrics: Array<[string, string]> = [];
  const messages: string[] = [];
  const sections: Array<{ title: string; items: Array<[string, string]> }> = [];
  for (const [key, value] of Object.entries(result)) {
    if (isVerboseResultKey(key) || key.startsWith("_")) continue;
    if (value === null || value === undefined) continue;
    if (typeof value === "string" && value.length < 260) {
      if (["status", "method", "confidence", "applicability_domain", "note", "summary", "reaction_type"].includes(key)) {
        messages.push(`${humanizeKey(key)}: ${value}`);
      } else {
        metrics.push([humanizeKey(key), value]);
      }
      continue;
    }
    if (typeof value === "number" || typeof value === "boolean") {
      metrics.push([humanizeKey(key), formatResultValue(value)]);
      continue;
    }
    if (Array.isArray(value)) {
      if (value.every((item) => typeof item === "string" || typeof item === "number")) {
        messages.push(`${humanizeKey(key)}: ${value.join(", ")}`);
      } else {
        metrics.push([humanizeKey(key), `${value.length} 项`]);
      }
      continue;
    }
    if (isPlainObject(value)) {
      const items = Object.entries(value)
        .filter(([childKey, childValue]) => !isVerboseResultKey(childKey) && !isPlainObject(childValue) && !Array.isArray(childValue))
        .slice(0, 12)
        .map(([childKey, childValue]) => [humanizeKey(childKey), formatResultValue(childValue)] as [string, string]);
      if (items.length > 0) sections.push({ title: humanizeKey(key), items });
    }
  }
  return { metrics: metrics.slice(0, 16), messages: messages.slice(0, 12), sections: sections.slice(0, 6) };
}

function isVerboseResultKey(key: string): boolean {
  return ["stdout", "stderr", "raw", "raw_log", "log", "logs", "input_xyz", "gjf_text", "gjf", "features"].includes(key);
}

function humanizeKey(key: string): string {
  const labels: Record<string, string> = {
    available: "可用",
    status: "状态",
    source: "来源",
    work_dir: "工作目录",
    returncode: "返回码",
    total_energy_hartree: "总能量 (Hartree)",
    final_energy_hartree: "最终能量 (Hartree)",
    gibbs_free_energy_hartree: "Gibbs 自由能 (Hartree)",
    imaginary_frequency_count: "虚频数量",
    homo_ev: "HOMO (eV)",
    lumo_ev: "LUMO (eV)",
    method: "方法",
    confidence: "置信度",
    applicability_domain: "适用域",
    note: "说明",
    reaction_type: "反应类型",
    reaction_smiles: "Reaction SMILES",
    mapped_reaction_smiles: "映射反应",
    valid: "有效",
    balanced: "元素守恒",
  };
  return labels[key] ?? key.replace(/_/g, " ");
}

function statusLabel(status: unknown): string {
  const text = String(status ?? "");
  const labels: Record<string, string> = {
    available: "完成",
    succeeded: "成功",
    failed: "失败",
    running: "运行中",
    queued: "排队中",
    unavailable: "不可用",
  };
  return labels[text] ?? text;
}

function formatResultValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") {
    if (Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.001)) return value.toExponential(4);
    return Number.isInteger(value) ? String(value) : value.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
  }
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) return `${value.length} 项`;
  if (isPlainObject(value)) return "结构化数据";
  return String(value);
}

function trimLongText(text: string, limit = 12000): string {
  if (text.length <= limit) return text;
  return `${text.slice(0, limit)}\n\n... 已截断，完整内容仍在任务缓存/日志文件中。`;
}

function asRoutePredictionResult(value: unknown): {
  status: string;
  used_fallback?: boolean;
  target_smiles: string;
  candidates: RouteCandidate[];
} | null {
  if (!value || typeof value !== "object") return null;
  const result = value as any;
  if (!Array.isArray(result.candidates) || !result.target_smiles) return null;
  return result;
}

function asPropertyResult(value: unknown): Record<string, any> | null {
  if (!value || typeof value !== "object") return null;
  const result = value as Record<string, any>;
  return result.rdkit ? result : null;
}

function asComputeResult(value: unknown): Record<string, any> | null {
  if (!value || typeof value !== "object") return null;
  const result = value as Record<string, any>;
  return typeof result.status === "string" && typeof result.source === "string" && ("work_dir" in result || "stdout" in result || "data" in result)
    ? result
    : null;
}

function asGaussianJob(value: unknown): GaussianJob | null {
  if (!value || typeof value !== "object") return null;
  const result = value as GaussianJob;
  return result.job_id && result.status ? result : null;
}

function moleculesFromReaction(reactionSmiles: string): string[] {
  return reactionSmiles
    .split(">>")
    .map((side) => side.trim())
    .filter(Boolean);
}

function splitSmilesComponents(smiles: string): string[] {
  const components = smiles
    .split(/[.·•]/)
    .map((item) => item.trim())
    .filter(Boolean);
  return components.length ? components : [smiles];
}

function displayFormulaLike(value: string): string {
  if (/^(?:\d+)?(?:[A-Z][a-z]?\d*)+(?:[.·•](?:\d+)?(?:[A-Z][a-z]?\d*)+)*$/.test(value.trim())) {
    return value.replace(/[.·•]/g, " · ");
  }
  return "无法渲染结构";
}
