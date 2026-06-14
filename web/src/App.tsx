import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";
import {
  Activity,
  Atom,
  Beaker,
  BookOpen,
  Boxes,
  GitBranch,
  Loader2,
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
  getWorkspace,
  listJobs,
  listWorkspaces,
  makeGaussianInput,
  mapReaction,
  planTs,
  predictProperties,
  reactionFeatures,
  renderMoleculeSvg,
  saveWorkspace,
  submitGaussianJob,
  validateReaction,
} from "./api";
import type { CellType, GaussianJob, MoleculeObject, ReactionObject, Workspace, WorkspaceCell, WorkspaceSummary } from "./types";

type SelectedObject =
  | { kind: "cell"; cell: WorkspaceCell }
  | { kind: "molecule"; cell: WorkspaceCell; molecule: MoleculeObject }
  | { kind: "reaction"; cell: WorkspaceCell; reaction: ReactionObject }
  | null;

const examples = {
  molecule: "CCO",
  reaction: "CCO>>CC=O",
  target: "CC(=O)Oc1ccccc1C(=O)O",
};

export function App() {
  const [summaries, setSummaries] = useState<WorkspaceSummary[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [activeCellId, setActiveCellId] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedObject>(null);
  const [result, setResult] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [jobs, setJobs] = useState<GaussianJob[]>([]);

  useEffect(() => {
    refreshWorkspaces();
    refreshJobs();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(refreshJobs, 5000);
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

  async function handleAddCell(type: CellType) {
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
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Atom size={24} />
          <div>
            <h1>OrgSynFlow</h1>
            <p>Notebook workbench</p>
          </div>
        </div>
        <button className="primary-button" onClick={handleNewWorkspace}>
          <Plus size={16} /> 新建工作区
        </button>
        <div className="section-title">工作区</div>
        <div className="workspace-list">
          {summaries.map((item) => (
            <button
              key={item.id}
              className={`workspace-item ${workspace?.id === item.id ? "active" : ""}`}
              onClick={() => handleOpenWorkspace(item.id)}
            >
              <span>{item.title}</span>
              <small>{item.cell_count} cells</small>
            </button>
          ))}
        </div>
        <div className="section-title">新增单元</div>
        <button className="ghost-button" onClick={() => handleAddCell("molecule")} disabled={!workspace}>
          <Beaker size={16} /> 分子单元
        </button>
        <button className="ghost-button" onClick={() => handleAddCell("reaction")} disabled={!workspace}>
          <Activity size={16} /> 反应单元
        </button>
        <button className="ghost-button" onClick={() => handleAddCell("route")} disabled={!workspace}>
          <GitBranch size={16} /> 路线单元
        </button>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h2>{workspace?.title ?? "未打开工作区"}</h2>
            <p>{workspace ? `${workspace.cells.length} 个单元 · ${workspace.updated_at}` : "创建或打开一个工作区开始"}</p>
          </div>
          <button className="primary-button" onClick={() => handleSaveWorkspace()} disabled={!workspace}>
            <Save size={16} /> 保存
          </button>
        </header>

        <div className="content-grid">
          <section className="notebook">
            <NotebookCells
              workspace={workspace}
              activeCellId={activeCellId}
              onSelect={(cell) => {
                setActiveCellId(cell.id);
                setSelected({ kind: "cell", cell });
                setResult(null);
              }}
            />
          </section>

          <section className="detail">
            {activeCell ? (
              <CellDetail
                cell={activeCell}
                onUpdate={updateCell}
                onSelect={setSelected}
              />
            ) : (
              <EmptyState />
            )}
          </section>

          <aside className="task-panel">
            <TaskPanel
              selected={selected}
              workspace={workspace}
              busy={busy}
              setBusy={setBusy}
              setResult={setResult}
              onSave={handleSaveWorkspace}
              jobs={jobs}
              refreshJobs={refreshJobs}
            />
          </aside>
        </div>

        <section className="result-panel">
          <div className="result-header">
            <BookOpen size={16} />
            <span>结果 / 日志</span>
          </div>
          <pre>{result ? JSON.stringify(result, null, 2) : "选择一个节点或箭头，然后在右侧运行任务。"}</pre>
        </section>
      </main>
    </div>
  );
}

function NotebookCells({
  workspace,
  activeCellId,
  onSelect,
}: {
  workspace: Workspace | null;
  activeCellId: string | null;
  onSelect: (cell: WorkspaceCell) => void;
}) {
  if (!workspace) return <EmptyState />;
  return (
    <div className="cell-list">
      {workspace.cells.map((cell) => (
        <button key={cell.id} className={`cell-card ${activeCellId === cell.id ? "active" : ""}`} onClick={() => onSelect(cell)}>
          <div className="cell-card-header">
            <span className={`type-pill ${cell.type}`}>{cell.type}</span>
            <strong>{cell.title}</strong>
          </div>
          <CellPreview cell={cell} />
        </button>
      ))}
    </div>
  );
}

function CellPreview({ cell }: { cell: WorkspaceCell }) {
  if (cell.type === "molecule") {
    return <p>{cell.objects.molecules?.map((molecule) => molecule.smiles).join(", ") || "空分子单元"}</p>;
  }
  if (cell.type === "reaction") {
    return <ReactionLine reaction={cell.objects.reactions?.[0]?.reaction_smiles ?? examples.reaction} />;
  }
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

  useEffect(() => {
    setNodes(toNodes(cell));
    setEdges(toEdges(cell));
  }, [cell.id, cell.objects]);

  const onConnect = useCallback(
    (params: Connection) => setEdges((current) => addEdge({ ...params, markerEnd: { type: MarkerType.ArrowClosed } }, current)),
    [setEdges],
  );

  function persistCanvas() {
    onUpdate({
      ...cell,
      canvas: { nodes, edges },
      objects: objectsFromCanvas(cell, nodes, edges),
    });
  }

  return (
    <div className="detail-shell">
      <div className="detail-toolbar">
        <strong>{cell.title}</strong>
        <button className="ghost-button compact" onClick={persistCanvas}>同步画布到单元</button>
      </div>
      <div className="canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
          onNodeClick={(_, node) => {
            const molecule = cell.objects.molecules?.find((item) => item.id === node.id);
            if (molecule) onSelect({ kind: "molecule", cell, molecule });
          }}
          onEdgeClick={(_, edge) => {
            const reaction = reactionFromEdge(cell, edge);
            if (reaction) onSelect({ kind: "reaction", cell, reaction });
          }}
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
      <EditorStrip cell={cell} onUpdate={onUpdate} />
    </div>
  );
}

function EditorStrip({ cell, onUpdate }: { cell: WorkspaceCell; onUpdate: (cell: WorkspaceCell) => void }) {
  const [smiles, setSmiles] = useState(examples.molecule);
  const [reaction, setReaction] = useState(examples.reaction);
  const [drawerOpen, setDrawerOpen] = useState(false);

  function addMolecule() {
    const id = `mol-${Date.now()}`;
    const molecule = { id, label: smiles, smiles };
    onUpdate({
      ...cell,
      objects: {
        ...cell.objects,
        molecules: [...(cell.objects.molecules ?? []), molecule],
      },
    });
  }

  function addReaction() {
    const id = `rxn-${Date.now()}`;
    const reactionObject = { id, label: "Reaction", reaction_smiles: reaction };
    onUpdate({
      ...cell,
      objects: {
        ...cell.objects,
        reactions: [...(cell.objects.reactions ?? []), reactionObject],
      },
    });
  }

  return (
    <div className="editor-strip">
      <div>
        <label>添加分子</label>
        <input value={smiles} onChange={(event) => setSmiles(event.target.value)} />
        <button onClick={addMolecule}>添加</button>
      </div>
      <div>
        <label>添加反应</label>
        <input value={reaction} onChange={(event) => setReaction(event.target.value)} />
        <button onClick={addReaction}>添加</button>
      </div>
      <button className="ghost-button compact" onClick={() => setDrawerOpen(true)}>
        打开绘图器
      </button>
      {drawerOpen && (
        <KetcherModal
          initialSmiles={smiles}
          onClose={() => setDrawerOpen(false)}
          onApply={(nextSmiles) => {
            setSmiles(nextSmiles);
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
  onSave,
  jobs,
  refreshJobs,
}: {
  selected: SelectedObject;
  workspace: Workspace | null;
  busy: boolean;
  setBusy: (busy: boolean) => void;
  setResult: (result: unknown) => void;
  onSave: (workspace?: Workspace | null) => Promise<void>;
  jobs: GaussianJob[];
  refreshJobs: () => Promise<void>;
}) {
  async function runTask(task: () => Promise<unknown>) {
    setBusy(true);
    try {
      setResult(await task());
    } catch (error) {
      setResult({ error: String(error) });
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
      {selected?.kind === "cell" && <CellTasks selected={selected} runTask={runTask} setResult={setResult} />}
      {selected?.kind === "molecule" && (
        <MoleculeTasks
          selected={selected}
          workspace={workspace}
          runTask={runTask}
          setResult={setResult}
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
          refreshJobs={refreshJobs}
        />
      )}
      {workspace?.route_candidate_sets?.length ? (
        <>
          <div className="panel-title jobs-title">路线候选集</div>
          <div className="job-list">
            {workspace.route_candidate_sets.slice(-4).reverse().map((set) => (
              <div key={set.id} className="job-row">
                <span>{set.target_smiles}</span>
                <strong>{set.status}</strong>
              </div>
            ))}
          </div>
        </>
      ) : null}
      <div className="panel-title jobs-title">Gaussian 队列</div>
      <div className="job-list">
        {jobs.slice(0, 6).map((job) => (
          <div key={job.job_id} className="job-row">
            <span>{job.job_id}</span>
            <strong>{job.status}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function CellTasks({
  selected,
  runTask,
  setResult,
}: {
  selected: Extract<SelectedObject, { kind: "cell" }>;
  runTask: (task: () => Promise<unknown>) => Promise<void>;
  setResult: (result: unknown) => void;
}) {
  return (
    <div className="task-group">
      <h3>{selected.cell.title}</h3>
      <button onClick={() => setResult(selected.cell)}>查看单元 JSON</button>
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
  onSave,
  refreshJobs,
}: {
  selected: Extract<SelectedObject, { kind: "molecule" }>;
  workspace: Workspace | null;
  runTask: (task: () => Promise<unknown>) => Promise<void>;
  setResult: (result: unknown) => void;
  onSave: (workspace?: Workspace | null) => Promise<void>;
  refreshJobs: () => Promise<void>;
}) {
  const { molecule } = selected;
  return (
    <div className="task-group">
      <h3>{molecule.label}</h3>
      <code>{molecule.smiles}</code>
      <button onClick={() => runTask(() => predictProperties(molecule.smiles, true))}>性质 + OPERA</button>
      <button onClick={() => runTask(() => calculateDescriptors(molecule.smiles))}>描述符</button>
      <button
        onClick={() =>
          runTask(async () => {
            const prediction = (await analyzeRoute(molecule.smiles, 3, true)) as {
              status?: string;
              target_smiles?: string;
              candidates?: unknown[];
            };
            if (workspace) {
              await onSave({
                ...workspace,
                route_candidate_sets: [
                  ...(workspace.route_candidate_sets ?? []),
                  {
                    id: `rcs-${Date.now()}`,
                    target_smiles: prediction.target_smiles ?? molecule.smiles,
                    status: prediction.status ?? "unknown",
                    created_at: new Date().toISOString(),
                    candidates: prediction.candidates ?? [],
                  },
                ],
              });
            }
            return prediction;
          })
        }
      >
        预测路线并缓存候选集
      </button>
      <button
        onClick={() =>
          runTask(async () => {
            const gjf = await makeGaussianInput(molecule.smiles);
            setResult({ gjf });
            return { gjf };
          })
        }
      >
        生成 opt/freq gjf
      </button>
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
        提交 Gaussian 作业
      </button>
    </div>
  );
}

function ReactionTasks({
  selected,
  workspace,
  runTask,
  setResult,
  refreshJobs,
}: {
  selected: Extract<SelectedObject, { kind: "reaction" }>;
  workspace: Workspace | null;
  runTask: (task: () => Promise<unknown>) => Promise<void>;
  setResult: (result: unknown) => void;
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
  if (type === "reaction") {
    return {
      title: "Reaction analysis",
      objects: {
        molecules: [],
        reactions: [{ id: "rxn-1", label: "Oxidation example", reaction_smiles: examples.reaction }],
        routes: [],
      },
    };
  }
  if (type === "route") {
    return {
      title: "Manual route",
      objects: {
        molecules: [
          { id: "mol-reactant", label: "Reactant", smiles: "CCO" },
          { id: "mol-product", label: "Product", smiles: "CC=O" },
        ],
        reactions: [{ id: "rxn-route-1", label: "Step 1", reaction_smiles: examples.reaction }],
        routes: [],
      },
    };
  }
  return {
    title: "Molecule analysis",
    objects: {
      molecules: [{ id: "mol-1", label: "Ethanol", smiles: examples.molecule }],
      reactions: [],
      routes: [],
    },
  };
}

function toNodes(cell: WorkspaceCell): Node[] {
  if (cell.canvas?.nodes?.length) {
    return cell.canvas.nodes.map((node) => ({
      ...node,
      type: node.type === "molecule" ? "default" : node.type,
    }));
  }
  const molecules = cell.objects.molecules ?? [];
  return molecules.map((molecule, index) => ({
    id: molecule.id,
    type: "default",
    position: { x: 80 + index * 260, y: 120 },
    data: { label: `${molecule.label}\n${molecule.smiles}` },
  }));
}

function toEdges(cell: WorkspaceCell): Edge[] {
  if (cell.canvas?.edges?.length) return cell.canvas.edges;
  const molecules = cell.objects.molecules ?? [];
  const reactions = cell.objects.reactions ?? [];
  if (molecules.length >= 2 && reactions[0]) {
    return [
      {
        id: reactions[0].id,
        source: molecules[0].id,
        target: molecules[1].id,
        label: reactions[0].label,
        markerEnd: { type: MarkerType.ArrowClosed },
      },
    ];
  }
  return [];
}

function reactionFromEdge(cell: WorkspaceCell, edge: Edge): ReactionObject | undefined {
  return cell.objects.reactions?.find((reaction) => reaction.id === edge.id) ?? cell.objects.reactions?.[0];
}

function objectsFromCanvas(cell: WorkspaceCell, nodes: Node[], edges: Edge[]) {
  const molecules = nodes.map((node) => {
    const existing = cell.objects.molecules?.find((item) => item.id === node.id);
    return existing ?? { id: node.id, label: String(node.data?.label ?? node.id), smiles: String(node.data?.label ?? "") };
  });
  const reactions = edges.map((edge, index) => {
    const existing = reactionFromEdge(cell, edge);
    return existing ?? { id: edge.id, label: String(edge.label ?? `Step ${index + 1}`), reaction_smiles: "" };
  });
  return { ...cell.objects, molecules, reactions };
}
