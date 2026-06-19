import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
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
  type Node,
  type NodeProps,
} from "@xyflow/react";
import {
  Atom,
  BookOpen,
  Boxes,
  ChevronDown,
  Cpu,
  Link2,
  Trash2,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Save,
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
  validateReaction,
} from "./api";
import type {
  CellType,
  ComputeStatus,
  GaussianJob,
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
  | { kind: "molecule"; cell: WorkspaceCell; molecule: MoleculeObject }
  | { kind: "reaction"; cell: WorkspaceCell; reaction: ReactionObject }
  | null;

type ModalState =
  | { kind: "result"; title: string; result: unknown }
  | { kind: "backend"; status: ComputeStatus | null }
  | { kind: "jobs"; jobs: GaussianJob[]; refresh: () => Promise<void> }
  | { kind: "routes"; sets: RouteCandidateSet[]; workspace: Workspace; selected: SelectedObject; onSave: (workspace?: Workspace | null) => Promise<void> }
  | null;

type RunTask = (
  task: () => Promise<unknown>,
  options?: { openResult?: boolean; title?: string },
) => Promise<unknown>;

const examples = {
  molecule: "CCO",
  reaction: "CCO>>CC=O",
  target: "CC(=O)Oc1ccccc1C(=O)O",
};

const moleculeHandles = [
  { id: "top", position: Position.Top, style: { left: "50%" } },
  { id: "top-a", position: Position.Top, style: { left: "34%" } },
  { id: "top-b", position: Position.Top, style: { left: "66%" } },
  { id: "right", position: Position.Right, style: { top: "50%" } },
  { id: "right-a", position: Position.Right, style: { top: "30%" } },
  { id: "right-b", position: Position.Right, style: { top: "70%" } },
  { id: "bottom", position: Position.Bottom, style: { left: "50%" } },
  { id: "bottom-a", position: Position.Bottom, style: { left: "34%" } },
  { id: "bottom-b", position: Position.Bottom, style: { left: "66%" } },
  { id: "left", position: Position.Left, style: { top: "50%" } },
  { id: "left-a", position: Position.Left, style: { top: "30%" } },
  { id: "left-b", position: Position.Left, style: { top: "70%" } },
];

export function App() {
  const [summaries, setSummaries] = useState<WorkspaceSummary[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [activeCellId, setActiveCellId] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedObject>(null);
  const [, setResult] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [jobs, setJobs] = useState<GaussianJob[]>([]);
  const [computeStatus, setComputeStatus] = useState<ComputeStatus | null>(null);
  const [modal, setModal] = useState<ModalState>(null);
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  const [unitRailOpen, setUnitRailOpen] = useState(true);

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
    if (!workspace && items[0]) {
      const loaded = await getWorkspace(items[0].id);
      setWorkspace(loaded);
      setActiveCellId(loaded.cells[0]?.id ?? null);
    }
  }

  async function refreshJobs() {
    setJobs(await listJobs());
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
    setWorkspace(created);
    setActiveCellId(null);
    setSelected(null);
    await refreshWorkspaces();
  }

  async function handleOpenWorkspace(id: string) {
    const loaded = await getWorkspace(id);
    setWorkspace(loaded);
    setActiveCellId(loaded.cells[0]?.id ?? null);
    setSelected(null);
    setResult(null);
  }

  async function handleSaveWorkspace(next = workspace) {
    if (!next) return;
    const saved = await saveWorkspace(next);
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
    if (!workspace) return;
    const next = {
      ...workspace,
      cells: workspace.cells.map((cell) => (cell.id === updated.id ? updated : cell)),
    };
    setWorkspace(next);
  }

  const activeCell = workspace?.cells.find((cell) => cell.id === activeCellId) ?? null;

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
                    <CellPreview cell={cell} />
                  </div>
                ))}
              </div>
            </aside>
          )}
          <section className="detail">
            <div className="detail-stack">
              {activeCell ? (
                <CellDetail
                  cell={activeCell}
                  onUpdate={updateCell}
                  onSelect={setSelected}
                />
              ) : (
                <EmptyState />
              )}
            </div>
          </section>

          <aside className="task-panel">
            <TaskPanel
              selected={selected}
              workspace={workspace}
              busy={busy}
              setBusy={setBusy}
              setResult={setResult}
              openModal={setModal}
              onSave={handleSaveWorkspace}
              jobs={jobs}
              refreshJobs={refreshJobs}
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
  return (
    <section className="result-panel">
      <div className="result-header">
        <BookOpen size={16} />
        <span>结果 / 日志</span>
      </div>
      {!result && <p className="muted">选择一个节点或箭头，然后在右侧运行任务。</p>}
      {routeResult && <RouteResultView result={routeResult} />}
      {propertyResult && <PropertyResultView result={propertyResult} />}
      {computeResult && <ComputeResultView result={computeResult} />}
      {gaussianJob && <GaussianJobView job={gaussianJob} />}
      {Boolean(result) && !routeResult && !propertyResult && !computeResult && !gaussianJob && (
        <pre>{JSON.stringify(result, null, 2) ?? ""}</pre>
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

function ComputeResultView({ result }: { result: Record<string, any> }) {
  return (
    <div className="structured-result">
      <div className="result-summary">
        <strong>{result.source ?? "计算结果"}</strong>
        <span>{result.status}</span>
      </div>
      {result.work_dir && <code>{result.work_dir}</code>}
      {result.data && (
        <div className="metric-grid">
          {Object.entries(result.data).map(([key, value]) => (
            <div key={key}><span>{key}</span><strong>{String(value ?? "-")}</strong></div>
          ))}
        </div>
      )}
      {result.reason && <p>{result.reason}</p>}
      {(result.stdout || result.stderr) && <pre>{[result.stdout, result.stderr].filter(Boolean).join("\n\n")}</pre>}
    </div>
  );
}

function GaussianJobView({ job }: { job: GaussianJob }) {
  return (
    <div className="structured-result">
      <div className="result-summary">
        <strong>{job.job_id}</strong>
        <span>{job.status}</span>
      </div>
      {job.work_dir && <code>{job.work_dir}</code>}
      {job.error && <p>{job.error}</p>}
      {Boolean(job.result) && <pre>{JSON.stringify(job.result, null, 2) ?? ""}</pre>}
    </div>
  );
}

function CellPreview({ cell }: { cell: WorkspaceCell }) {
  return (
    <div>
      <p>{cell.objects.molecules?.length ?? 0} molecules · {cell.objects.reactions?.length ?? 0} reactions</p>
      {(cell.objects.reactions ?? []).slice(0, 3).map((reaction) => (
        <ReactionLine key={reaction.id} reaction={reaction.reaction_smiles} />
      ))}
    </div>
  );
}

function ReactionLine({ reaction }: { reaction: string }) {
  const [left, right] = reaction.split(">>");
  return (
    <div className="reaction-line">
      <span>{left || "reactants"}</span>
      <span className="arrow">→</span>
      <span>{right || "products"}</span>
    </div>
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
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [connectMode, setConnectMode] = useState(false);
  const [shiftConnectMode, setShiftConnectMode] = useState(false);
  const [pendingConnectionNodeId, setPendingConnectionNodeId] = useState<string | null>(null);
  const [relationSourceId, setRelationSourceId] = useState("");
  const [relationTargetId, setRelationTargetId] = useState("");
  const nodeTypes = useMemo(() => ({ molecule: MoleculeNode }), []);
  const molecules = cell.objects.molecules ?? [];
  const linkingActive = connectMode || shiftConnectMode;

  useEffect(() => {
    setNodes(toNodes(cell));
    setEdges(toEdges(cell));
    setSelectedEdgeId(null);
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
      const handles: Partial<ReturnType<typeof smartConnectionHandles>> =
        sourceNode && targetNode ? smartConnectionHandles(sourceNode, targetNode) : {};
      const edge = makeCanvasEdge({
        source: params.source,
        target: params.target,
        sourceHandle: params.sourceHandle ?? handles.sourceHandle,
        targetHandle: params.targetHandle ?? handles.targetHandle,
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
    const handles: Partial<ReturnType<typeof smartConnectionHandles>> =
      sourceNode && targetNode ? smartConnectionHandles(sourceNode, targetNode) : {};
    const edge = makeCanvasEdge({
      source: sourceId,
      target: targetId,
      sourceHandle: handles.sourceHandle,
      targetHandle: handles.targetHandle,
    });
    setEdges((current) => addEdge(edge, current));
    setSelectedEdgeId(edge.id);
    return true;
  }

  function handleNodeClick(node: Node) {
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
    setSelectedEdgeId(null);
    const molecule = cell.objects.molecules?.find((item) => item.id === node.id);
    if (molecule) onSelect({ kind: "molecule", cell, molecule });
  }

  function removeEdge(edgeId: string) {
    setEdges((current) => current.filter((edge) => edge.id !== edgeId));
    setSelectedEdgeId(null);
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
            },
            className: node.id === pendingConnectionNodeId ? "connection-source-node" : undefined,
          }))}
          edges={edges.map((edge) => ({ ...edge, selected: edge.id === selectedEdgeId }))}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          connectionMode={ConnectionMode.Loose}
          deleteKeyCode={["Backspace", "Delete"]}
          fitView
          onNodeClick={(_, node) => handleNodeClick(node)}
          onEdgeClick={(_, edge) => {
            setSelectedEdgeId(edge.id);
            const reaction = reactionFromEdge(cell, edge);
            if (reaction) onSelect({ kind: "reaction", cell, reaction });
          }}
          onPaneClick={() => {
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
    return () => {
      cancelled = true;
    };
  }, [smiles]);

  return (
    <div
      className="molecule-node"
      onClick={(event) => {
        event.stopPropagation();
        onActivate?.();
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
      <div className="molecule-drawing">
        {svg ? <div dangerouslySetInnerHTML={{ __html: svg }} /> : <span className={failed ? "formula-fallback" : ""}>{failed ? displayFormulaLike(smiles) : "渲染中..."}</span>}
      </div>
      <div className="molecule-caption" title={label === smiles ? smiles : `${label} · ${smiles}`}>
        {smiles}
      </div>
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
        reactions.push({ id: reactionId, label: `Step ${reactions.length + 1}`, reaction_smiles: line });
        for (const smiles of moleculesFromReaction(line)) {
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
    <div className="modal-backdrop">
      <div className="ketcher-modal">
        <div className="modal-header">
          <strong>Ketcher 绘图输入</strong>
          <button onClick={onClose}>关闭</button>
        </div>
        <div className="ketcher-host">
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
        <div className="modal-footer">
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
  busy,
  setBusy,
  setResult,
  openModal,
  onSave,
  jobs,
  refreshJobs,
}: {
  selected: SelectedObject;
  workspace: Workspace | null;
  busy: boolean;
  setBusy: (busy: boolean) => void;
  setResult: (result: unknown) => void;
  openModal: (modal: ModalState) => void;
  onSave: (workspace?: Workspace | null) => Promise<void>;
  jobs: GaussianJob[];
  refreshJobs: () => Promise<void>;
}) {
  async function runTask(task: () => Promise<unknown>, options?: { openResult?: boolean; title?: string }) {
    setBusy(true);
    try {
      const nextResult = await task();
      setResult(nextResult);
      if (options?.openResult !== false) {
        openModal({ kind: "result", title: options?.title ?? "任务结果", result: nextResult });
      }
      return nextResult;
    } catch (error) {
      const nextResult = { error: String(error) };
      setResult(nextResult);
      openModal({ kind: "result", title: "任务错误", result: nextResult });
      return nextResult;
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="panel-title">
        <Boxes size={16} />
        <span>任务面板</span>
      </div>
      {busy && <div className="busy"><Loader2 size={16} /> 运行中...</div>}
      {!selected && <p className="muted">选择 notebook 单元、分子节点或反应箭头。</p>}
      {selected?.kind === "cell" && <CellTasks selected={selected} runTask={runTask} />}
      {selected?.kind === "molecule" && (
        <MoleculeTasks
          selected={selected}
          workspace={workspace}
          runTask={runTask}
          setResult={setResult}
          openModal={openModal}
          jobs={jobs}
          onSave={onSave}
          refreshJobs={refreshJobs}
        />
      )}
      {selected?.kind === "reaction" && (
        <ReactionTasks
          selected={selected}
          workspace={workspace}
          runTask={runTask}
          setResult={setResult}
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

  async function addRouteToCurrentCell(route: RouteCandidate) {
    if (!activeCell) return;
    const updatedCell = addRouteCandidateToCell(activeCell, route, anchorMolecule);
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
    <div className="modal-backdrop">
      <div className={modal.kind === "result" ? "result-modal" : "config-modal"}>
        <div className="modal-header">
          <strong>
            {modal.kind === "result" && modal.title}
            {modal.kind === "backend" && "计算后端状态"}
            {modal.kind === "jobs" && "Gaussian 队列"}
            {modal.kind === "routes" && "路线候选"}
          </strong>
          <button onClick={onClose}>关闭</button>
        </div>
        <div className="modal-body">
          {modal.kind === "result" && <ResultPanel result={modal.result} />}
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
        </div>
      </div>
    </div>
  );
}

function GaussianJobsView({ jobs, refresh }: { jobs: GaussianJob[]; refresh: () => Promise<void> }) {
  return (
    <div className="job-list modal-job-list">
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
  const orderedKeys = ["gaussian", "aizynthfinder", "opera", "xtb", "crest", "openbabel", "pyscf", "psi4", "geometric", "goodvibes"];
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

function CellTasks({
  selected,
  runTask,
}: {
  selected: Extract<SelectedObject, { kind: "cell" }>;
  runTask: RunTask;
}) {
  return (
    <div className="task-group">
      <h3>{selected.cell.title}</h3>
      <button onClick={() => runTask(() => Promise.resolve(selected.cell), { title: "单元数据" })}>查看单元 JSON</button>
      {selected.cell.type === "route" && (
        <button onClick={() => runTask(() => Promise.resolve({ note: "路线级报告沿用后端 report_markdown；下一步可在此接入 PDF/Markdown 导出。" }))}>
          路线报告
        </button>
      )}
    </div>
  );
}

function MoleculeTasks({
  selected,
  workspace,
  runTask,
  setResult,
  openModal,
  jobs,
  onSave,
  refreshJobs,
}: {
  selected: Extract<SelectedObject, { kind: "molecule" }>;
  workspace: Workspace | null;
  runTask: RunTask;
  setResult: (result: unknown) => void;
  openModal: (modal: ModalState) => void;
  jobs: GaussianJob[];
  onSave: (workspace?: Workspace | null) => Promise<void>;
  refreshJobs: () => Promise<void>;
}) {
  const { molecule } = selected;
  const [gaussianConfigOpen, setGaussianConfigOpen] = useState(false);
  const moleculeRouteSets = workspace?.route_candidate_sets?.filter((set) => set.target_smiles === molecule.smiles) ?? [];
  return (
    <div className="task-group">
      <h3>{molecule.label}</h3>
      <code>{molecule.smiles}</code>
      <button onClick={() => runTask(() => predictProperties(molecule.smiles, true))}>RDKit + OPERA QSAR 物性</button>
      <button onClick={() => runTask(() => calculateDescriptors(molecule.smiles))}>描述符</button>
      <button onClick={() => runTask(() => runXtb(molecule.smiles, 300))}>xTB 优化/能量</button>
      <button onClick={() => runTask(() => runCrest(molecule.smiles, 1800))}>CREST 构象搜索</button>
      <button
        onClick={async () => {
          let routeSet: RouteCandidateSet | null = null;
          let nextWorkspace = workspace;
          const prediction = await runTask(async () => {
            const prediction = (await analyzeRoute(molecule.smiles, 3, true)) as {
              status?: string;
              used_fallback?: boolean;
              target_smiles?: string;
              candidates?: RouteCandidate[];
              route_scores?: Record<string, unknown>;
              feasibility?: Record<string, unknown>;
            };
            routeSet = {
              id: `rcs-${Date.now()}`,
              target_smiles: prediction.target_smiles ?? molecule.smiles,
              status: prediction.status ?? "unknown",
              created_at: new Date().toISOString(),
              candidates: prediction.candidates ?? [],
              route_scores: prediction.route_scores,
              feasibility: prediction.feasibility,
              used_fallback: prediction.used_fallback,
            };
            if (workspace) {
              nextWorkspace = {
                ...workspace,
                route_candidate_sets: [...(workspace.route_candidate_sets ?? []), routeSet],
              };
              await onSave(nextWorkspace);
            }
            return prediction;
          }, { openResult: false });
          if (routeSet && nextWorkspace) {
            openModal({ kind: "routes", sets: [routeSet], workspace: nextWorkspace, selected, onSave });
          } else {
            openModal({ kind: "result", title: "路线预测结果", result: prediction });
          }
        }}
      >
        预测逆合成路线
      </button>
      {workspace && moleculeRouteSets.length > 0 && (
        <button onClick={() => openModal({ kind: "routes", sets: moleculeRouteSets, workspace, selected, onSave })}>
          查看路线候选 ({moleculeRouteSets.length})
        </button>
      )}
      <button
        onClick={() =>
          runTask(async () => {
            const gjf = await makeGaussianInput(molecule.smiles);
            const job = await submitGaussianJob(gjf, workspace?.id, selected.cell.id, molecule.id);
            await refreshJobs();
            await onSave(workspace);
            return job;
          })
        }
      >
        提交 Gaussian opt/freq
      </button>
      <button onClick={() => setGaussianConfigOpen(true)}>Gaussian 高级配置</button>
      <button onClick={() => openModal({ kind: "jobs", jobs, refresh: refreshJobs })}>查看 Gaussian 队列</button>
      {gaussianConfigOpen && (
        <GaussianConfigModal
          smiles={molecule.smiles}
          onClose={() => setGaussianConfigOpen(false)}
          onSubmit={(jobType, method, basis, charge, multiplicity) =>
            runTask(async () => {
              const gjf = await makeGaussianInput(molecule.smiles, jobType, method, basis, charge, multiplicity);
              const job = await submitGaussianJob(gjf, workspace?.id, selected.cell.id, molecule.id);
              await refreshJobs();
              await onSave(workspace);
              setGaussianConfigOpen(false);
              return job;
            })
          }
          onPreview={(jobType, method, basis, charge, multiplicity) =>
            runTask(async () => {
              const gjf = await makeGaussianInput(molecule.smiles, jobType, method, basis, charge, multiplicity);
              return { gjf };
            })
          }
        />
      )}
    </div>
  );
}

function ReactionTasks({
  selected,
  workspace,
  runTask,
  setResult,
  openModal,
  jobs,
  refreshJobs,
}: {
  selected: Extract<SelectedObject, { kind: "reaction" }>;
  workspace: Workspace | null;
  runTask: RunTask;
  setResult: (result: unknown) => void;
  openModal: (modal: ModalState) => void;
  jobs: GaussianJob[];
  refreshJobs: () => Promise<void>;
}) {
  const { reaction } = selected;
  return (
    <div className="task-group">
      <h3>{reaction.label}</h3>
      <code>{reaction.reaction_smiles}</code>
      <button onClick={() => runTask(() => validateReaction(reaction.reaction_smiles, reaction.template))}>基础校验 + 可行性</button>
      <button onClick={() => runTask(() => explainReaction(reaction.reaction_smiles, reaction.template))}>反应解释</button>
      <button onClick={() => runTask(() => mapReaction(reaction.reaction_smiles))}>RXNMapper 映射</button>
      <button onClick={() => runTask(() => estimateYield(reaction.reaction_smiles, reaction.template))}>产率估计</button>
      <button onClick={() => runTask(() => reactionFeatures(reaction.reaction_smiles))}>反应特征</button>
      <button onClick={() => runTask(() => planTs(reaction.reaction_smiles))}>TS 计划</button>
      <button
        onClick={() =>
          runTask(async () => {
            const plan = await planTs(reaction.reaction_smiles);
            const gjf = `# opt=(ts,calcfc,noeigentest) freq\n\nOrgSynFlow TS candidate - unverified\n\n0 1\n\n`;
            setResult({ plan, gjf, validation_level: "未验证" });
            return { plan, gjf, validation_level: "未验证" };
          })
        }
      >
        生成 TS gjf 草稿
      </button>
      <button
        onClick={() =>
          runTask(async () => {
            const gjf = `# opt=(ts,calcfc,noeigentest) freq\n\nOrgSynFlow TS candidate - unverified\n\n0 1\n\n`;
            const job = await submitGaussianJob(gjf, workspace?.id, selected.cell.id, reaction.id);
            await refreshJobs();
            return job;
          })
        }
      >
        提交 TS Gaussian 作业
      </button>
      <button onClick={() => openModal({ kind: "jobs", jobs, refresh: refreshJobs })}>查看 Gaussian 队列</button>
    </div>
  );
}

function GaussianConfigModal({
  smiles,
  onClose,
  onSubmit,
  onPreview,
}: {
  smiles: string;
  onClose: () => void;
  onSubmit: (jobType: string, method: string, basis: string, charge: number, multiplicity: number) => void;
  onPreview: (jobType: string, method: string, basis: string, charge: number, multiplicity: number) => void;
}) {
  const [jobType, setJobType] = useState("opt freq");
  const [method, setMethod] = useState("B3LYP");
  const [basis, setBasis] = useState("6-31G(d)");
  const [charge, setCharge] = useState(0);
  const [multiplicity, setMultiplicity] = useState(1);

  return (
    <div className="modal-backdrop">
      <div className="config-modal">
        <div className="modal-header">
          <strong>Gaussian 配置</strong>
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
              <option value="opt freq">opt + freq</option>
              <option value="opt">opt</option>
              <option value="freq">freq</option>
              <option value="sp">single point</option>
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
        </div>
        <div className="modal-footer">
          <button onClick={() => onPreview(jobType, method, basis, charge, multiplicity)}>预览 gjf</button>
          <button className="primary-button" onClick={() => onSubmit(jobType, method, basis, charge, multiplicity)}>提交计算</button>
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
    const reactantSmiles = left?.split(".").filter(Boolean) ?? [];
    const productSmiles = right?.split(".").filter(Boolean) ?? [];
    const target = molecules.find((molecule) => productSmiles.includes(molecule.smiles));
    if (!target) return;
    reactantSmiles.forEach((smiles, index) => {
      const source = molecules.find((molecule) => molecule.smiles === smiles);
      if (!source) return;
      edges.push(makeCanvasEdge({
        id: `${reaction.id}-${index}`,
        source: source.id,
        target: target.id,
        sourceHandle: "right",
        targetHandle: "left",
        label: reaction.label || `Step ${reactionIndex + 1}`,
      }));
    });
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

function normalizeEdge(edge: Edge, nodeMap?: Map<string, Node>): Edge {
  const sourceNode = nodeMap?.get(edge.source);
  const targetNode = nodeMap?.get(edge.target);
  const handles = sourceNode && targetNode
    ? smartConnectionHandles(sourceNode, targetNode)
    : {
        sourceHandle: normalizeMoleculeHandleId(edge.sourceHandle, "right"),
        targetHandle: normalizeMoleculeHandleId(edge.targetHandle, "left"),
      };
  return {
    ...edge,
    type: "straight",
    className: edge.className ?? "canvas-edge",
    interactionWidth: edge.interactionWidth ?? 18,
    style: { stroke: "#0f172a", strokeWidth: 3, ...(edge.style ?? {}) },
    markerEnd: undefined,
    sourceHandle: handles.sourceHandle,
    targetHandle: handles.targetHandle,
  };
}

function makeCanvasEdge(edge: Partial<Edge> & { source: string; target: string }): Edge {
  return {
    id: edge.id ?? `edge-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    type: "straight",
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle,
    targetHandle: edge.targetHandle,
    label: edge.label,
    className: "canvas-edge",
    interactionWidth: 18,
    markerEnd: undefined,
    style: { stroke: "#0f172a", strokeWidth: 3, ...(edge.style ?? {}) },
  };
}

function smartConnectionHandles(source: Node, target: Node): { sourceHandle: string; targetHandle: string } {
  const sourceCenter = nodeCenter(source);
  const targetCenter = nodeCenter(target);
  const dx = targetCenter.x - sourceCenter.x;
  const dy = targetCenter.y - sourceCenter.y;
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0
      ? { sourceHandle: "right", targetHandle: "left" }
      : { sourceHandle: "left", targetHandle: "right" };
  }
  return dy >= 0
    ? { sourceHandle: "bottom", targetHandle: "top" }
    : { sourceHandle: "top", targetHandle: "bottom" };
}

function nodeCenter(node: Node): { x: number; y: number } {
  const width = typeof node.measured?.width === "number" ? node.measured.width : 190;
  const height = typeof node.measured?.height === "number" ? node.measured.height : 142;
  return {
    x: node.position.x + width / 2,
    y: node.position.y + height / 2,
  };
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

function addRouteCandidateToCell(cell: WorkspaceCell, route: RouteCandidate, anchorMolecule: MoleculeObject | null): WorkspaceCell {
  const stamp = Date.now();
  const existingNodes = toNodes(cell);
  const existingEdges = toEdges(cell);
  const baseX = 80 + existingNodes.length * 36;
  const baseY = 80 + existingNodes.length * 20;
  const idMap = new Map<string, string[]>();
  const routeMolecules: MoleculeObject[] = [];
  const routeNodes: Node[] = [];
  route.molecules.forEach((molecule, index) => {
    const components = splitSmilesComponents(molecule.smiles);
    const ids = components.map((smiles, componentIndex) => `route-${stamp}-${route.id}-${molecule.id}-${componentIndex}`);
    idMap.set(molecule.id, ids);
    const layoutNode = route.layout?.nodes?.[molecule.id];
    components.forEach((smiles, componentIndex) => {
      const id = ids[componentIndex];
      const label = components.length > 1 ? `${molecule.name || molecule.smiles} ${componentIndex + 1}` : molecule.name || smiles;
      routeMolecules.push({ id, label, smiles });
      routeNodes.push({
        id,
        type: "molecule",
        position: {
          x: baseX + (layoutNode?.x ?? 260 * index),
          y: baseY + (layoutNode?.y ?? 120 * index) + componentIndex * 170,
        },
        data: { label, smiles },
      });
    });
  });
  const routeReactions: ReactionObject[] = route.steps.map((step, index) => {
    const product = route.molecules.find((molecule) => molecule.id === step.product_id);
    const precursors = step.precursor_ids
      .map((id) => route.molecules.find((molecule) => molecule.id === id)?.smiles)
      .filter(Boolean);
    return {
      id: `rxn-route-${stamp}-${route.id}-${step.id}-${index}`,
      label: step.template || `Route step ${index + 1}`,
      reaction_smiles: step.reaction_smiles || `${precursors.join(".")}>>${product?.smiles ?? ""}`,
      template: step.template ?? undefined,
    };
  });
  const routeEdges: Edge[] = [];
  route.steps.forEach((step, stepIndex) => {
    step.precursor_ids.forEach((precursorId, precursorIndex) => {
      const sources = idMap.get(precursorId) ?? [];
      const targets = idMap.get(step.product_id) ?? [];
      sources.forEach((source, sourceIndex) => {
        targets.forEach((target, targetIndex) => {
          const sourceNode = routeNodes.find((node) => node.id === source);
          const targetNode = routeNodes.find((node) => node.id === target);
          const handles = sourceNode && targetNode ? smartConnectionHandles(sourceNode, targetNode) : { sourceHandle: "right", targetHandle: "left" };
          routeEdges.push(makeCanvasEdge({
            id: `${routeReactions[stepIndex]?.id ?? `route-edge-${stamp}-${stepIndex}`}-${precursorIndex}-${sourceIndex}-${targetIndex}`,
            source,
            target,
            sourceHandle: handles.sourceHandle,
            targetHandle: handles.targetHandle,
            label: step.template || `Step ${stepIndex + 1}`,
          }));
        });
      });
    });
  });
  if (anchorMolecule) {
    const routeTarget = idMap.get(route.target_id)?.[0];
    const routeTargetNode = routeNodes.find((node) => node.id === routeTarget);
    const anchorNode = existingNodes.find((node) => node.id === anchorMolecule.id);
    if (routeTarget && routeTargetNode && anchorNode) {
      const handles = smartConnectionHandles(routeTargetNode, anchorNode);
      routeEdges.push(makeCanvasEdge({
        id: `route-anchor-${stamp}-${route.id}`,
        source: routeTarget,
        target: anchorMolecule.id,
        sourceHandle: handles.sourceHandle,
        targetHandle: handles.targetHandle,
        label: "route target",
      }));
    }
  }
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
    .flatMap((side) => side.split("."))
    .map((item) => item.trim())
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
