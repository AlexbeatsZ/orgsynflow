import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
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
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  const [unitRailOpen, setUnitRailOpen] = useState(true);

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
          <button className="primary-button" onClick={() => handleSaveWorkspace()} disabled={!workspace}>
            <Save size={16} /> 保存
          </button>
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
  const nodeTypes = useMemo(() => ({ molecule: MoleculeNode }), []);

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
          nodeTypes={nodeTypes}
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

function MoleculeNode({ data }: NodeProps) {
  const smiles = String(data.smiles ?? "");
  const label = String(data.label ?? smiles);
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
    <div className="molecule-node">
      <Handle type="target" position={Position.Left} />
      <div className="molecule-drawing">
        {svg ? <div dangerouslySetInnerHTML={{ __html: svg }} /> : <span className={failed ? "formula-fallback" : ""}>{failed ? displayFormulaLike(smiles) : "渲染中..."}</span>}
      </div>
      <div className="molecule-caption" title={label === smiles ? smiles : `${label} · ${smiles}`}>
        {smiles}
      </div>
      <Handle type="source" position={Position.Right} />
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
          if (!molecules.some((item) => item.smiles === smiles)) {
            molecules.push({ id: `mol-${Date.now()}-${molecules.length}`, label: smiles, smiles });
          }
        }
      } else if (!molecules.some((item) => item.smiles === line)) {
        molecules.push({ id: `mol-${Date.now()}-${molecules.length}`, label: line, smiles: line });
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
  if (cell.canvas?.edges?.length) return cell.canvas.edges;
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
      edges.push({
        id: `${reaction.id}-${index}`,
        source: source.id,
        target: target.id,
        label: reaction.label || `Step ${reactionIndex + 1}`,
        markerEnd: { type: MarkerType.ArrowClosed },
      });
    });
  });
  return edges;
}

function reactionFromEdge(cell: WorkspaceCell, edge: Edge): ReactionObject | undefined {
  return cell.objects.reactions?.find((reaction) => edge.id.startsWith(reaction.id)) ?? cell.objects.reactions?.[0];
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

function moleculesFromReaction(reactionSmiles: string): string[] {
  return reactionSmiles
    .split(">>")
    .flatMap((side) => side.split("."))
    .map((item) => item.trim())
    .filter(Boolean);
}

function displayFormulaLike(value: string): string {
  if (/^(?:\d+)?(?:[A-Z][a-z]?\d*)+(?:[.·•](?:\d+)?(?:[A-Z][a-z]?\d*)+)*$/.test(value.trim())) {
    return value.replace(/[.·•]/g, " · ");
  }
  return "无法渲染结构";
}
