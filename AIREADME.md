# AIREADME.md

本文件是 OrgSynFlow 的项目日志和 AI 接手手册。对于这个有独立文件夹的项目，每次新对话开始时应先读取本文件；如果不存在则创建。每次任务完成后，应把新经验、当前状态和未解决事项写回本文件。

## 1. Project Goal

OrgSynFlow 的总目标是构建一个本地优先、可插拔的有机合成工作台，把分子、反应、路线、性质预测、Gaussian 计算、过渡态规划、动力学和产率估计整合到一个连续工作流里。

当前产品方向：

- React/Vite 前端作为主要且唯一的交互界面，地址为 `http://127.0.0.1:5173/`。
- FastAPI 后端提供可测试接口，地址为 `http://127.0.0.1:8765/`。
- CLI `run_cli.py` 保留为稳定自动化入口。
- 所有的桌面客户端（如 Tkinter `desktop_app.py`、Streamlit）及其打包构建脚本（如 `build_exe.ps1` 等）已被永久废弃和删除。
- 工作区应该像 notebook/Jupyter：用户可以创建多个工作区，每个工作区内有多个通用化学单元。
- UI 中不要把单元硬分为“分子/反应/路线”三类；一个通用单元应能根据输入内容识别普通 SMILES、reaction SMILES 和多步路线。
- 画布中的分子必须渲染为结构图，不能只显示标题或大号文本。
- 用户应能选中任意分子节点做分子性质、描述符、Gaussian 输入等任务；也能选中反应箭头做反应解释、映射、产率、TS 计划等任务。
- 路线预测结果应先作为候选/预览呈现，用户确认后再插入当前工作区画布。

核心能力目标：

- 分子性质分析：RDKit 基础性质、可选 OPERA 预测、可选 Mordred/描述符扩展。
- 合成路线预测：AiZynthFinder 可用时解析真实结果；不可用时返回清楚的 unavailable/disabled，不冒充真实预测。
- 反应分析：基础可行性检查、反应解释、可选 RXNMapper 映射、反应特征导出。
- 量化计算：Gaussian 输入生成、Gaussian 作业队列、log/out 解析。
- 过渡态：半自动 TS 计划，不宣称自动保证正确；输出验证等级。
- 动力学/热力学：基于 Gibbs free energy 计算 `ΔG_rxn`、`ΔG‡` 和 Eyring 速率。
- 产率估计：明确区分 heuristic、特征导出、训练模型；每个结果都要有 method/confidence/applicability/note。

主要代码入口：

```text
README.md                         用户面向项目说明
plan.md                           三阶段集成计划
run_cli.py                        CLI 入口
run_api.py                        FastAPI 启动入口
api/main.py                       HTTP API
services/                         CLI/API/UI 共用服务层
core/                             分子、路线、Gaussian、动力学、产率核心逻辑
adapters/                         外部工具适配器
web/src/App.tsx                   React 工作区主界面
web/src/api.ts                    前端 API 客户端
web/src/types.ts                  前端类型定义
web/src/styles.css                前端样式
scripts/orgsynflow-toggle.ps1     本地服务开关脚本
data/workspaces/                  本地工作区 JSON
```

常用命令：

```powershell
# 后端
uv run python run_api.py

# 前端
cd web
npm run dev

# Python 测试
uv run pytest -q

# 前端构建
cd web
npm run build

# 开关脚本测试
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\orgsynflow-toggle.ps1 -NoOpen
```

桌面一键开关：

```text
C:\Users\Meta\Desktop\OrgSynFlow Toggle.cmd
```

它调用：

```powershell
scripts\orgsynflow-toggle.ps1
```

日志位置：

```text
%LOCALAPPDATA%\Temp\codex\orgsynflow\
```

WSL 镜像路径：

```text
/home/meta/Project/Workspaces/orgsynflow
```

WSL 环境：

```bash
/home/meta/.local/opt/miniforge3/bin/mamba run -n orgsynflow-chem <command>
```

WSL 临时文件必须放在：

```text
/tmp/codex/
```

## 2. Lessons Learned

项目日志规则：

- 每次新对话开始时，先读取项目根目录的 `AIREADME.md`。
- 如果 `AIREADME.md` 不存在，则创建。
- 每次任务完成后，更新本文件，至少记录新增经验、已解决 bug、当前任务状态。
- `AIREADME.md` 不是普通 README，而是给 AI/开发代理接力用的项目记忆。

本地工作约定：

- Windows 上运行 Python 优先用 `uv`。
- Windows 上下载/安装程序优先用 `scoop`，但除非用户确认，不要私自安装全局工具。
- Windows 临时文件、备份、日志集中放在 `%LOCALAPPDATA%\Temp\codex\`。
- WSL 临时文件集中放在 `/tmp/codex/`。
- 如果修改 Git 仓库，完成时要提交；如果连接 GitHub，还要推送。
- 不要回滚用户改动；如果测试或浏览器操作弄脏数据文件，只还原自己造成的测试痕迹。

架构与项目精简经验：

- 用户明确只使用 Web 界面（React/Vite），不再需要任何形式的桌面客户端或本地可执行文件打包产物。后续增加交互或 UI 新功能时，请仅针对 `web/` 目录的前端项目和对应的 FastAPI 后端进行开发，切勿重新引入或修改任何桌面 GUI（如 Tkinter/PyQt）及 `.exe` 打包逻辑。

前端 UX 经验：

- TS/GaussView 辅助 3D 预览不能在运行时重复注入 CDN 脚本；应通过项目内 `3dmol` 依赖统一异步加载。右栏是可收缩 flex 容器，viewer 必须设置 `flex: 0 0 350px` 与 `min-height`，否则声明的 350px 会被压缩到约 24px，表现为空白/不可用。候选 XYZ 必须先按分子拆组再应用每个分子的变换，不能在选中候选后直接返回原始 XYZ，否则预览和 GJF 均不会响应平移/旋转。
- SMILES 块删除不能只依赖 React Flow 的临时节点状态；删除时必须同时移除相邻边，并用剩余 nodes/edges 重建 `cell.objects.molecules/reactions`，否则父级单元更新或页面刷新会把节点重新生成。当前选中块后会显示“删除 SMILES 块”按钮，删除结果可随工作区保存持久化。
- 用户明确不要深色永久侧栏。工作区选择应是顶部紧凑下拉菜单。
- 单元栏应是白色、可隐藏；添加单元按钮放在单元栏内。
- UI 不要把单元做成“分子单元/反应单元/路线单元”的固定分类。用户期望一个通用化学单元，根据输入自动推断内容。
- 输入规则：普通 SMILES 是分子；包含 `>>` 是反应；多条连接反应可表达路线。
- 画布节点必须显示 SMILES 渲染出来的分子结构图，不能显示大号标题。
- 曾经出现过画布显示巨大 `Ethanol` 的问题，原因是 React Flow 默认 label 节点把分子 label/title 当内容渲染。已改为自定义 molecule node，并通过后端 RDKit SVG 接口渲染结构图。
- 曾经出现 `CCO` 看起来重复的问题，原因是节点 data 同时拼了 label 和 smiles。已改为节点底部只显示一行 SMILES。
- 单元删除按钮曾经嵌套在整张单元卡的 `<button>` 内，导致非法 DOM 和浏览器警告。已改为单元卡用可点击 `div`，删除按钮独立。
- `CO2.H2O` 这类点式组合不是 RDKit SMILES，但其中 `CO2`、`H2O` 等常见小分子式可以安全映射为结构。结构渲染接口应先尝试 RDKit；失败后按点号拆组分，能受控映射的组分画成多结构 SVG；像 `CuSO4.5H2O` 这种暂时不能可靠推断结构的输入再降级为公式 SVG。前端也要把 `svg: null` 作为失败态，避免节点一直显示“渲染中...”。
- 结果/日志面板不应占据主布局底部全宽；应嵌入中间工作面板内，并使用浅色背景配深色文字，和工作区面板一致。
- React Flow 手动画出的边不要被误当作第一条反应；只有由 reaction 对象生成的边才打开反应任务。手动画布边应能选中后删除，且禁止自连接这类不可见/无意义边。
- 化学画布应允许同一个 SMILES/结构出现多个独立节点，不能按 `smiles` 去重；重复试剂、等价底物、不同位置的同一分子都需要独立对象。
- 分子节点连接位点太少会限制路线/网络表达。当前每个分子节点应提供 8 个连接位点：top-a/top-b/right-a/right-b/bottom-a/bottom-b/left-a/left-b。
- 不要把 React Flow 的多个连接位点直接显示成蓝点，这会让用户以为必须拖拽锚点且画布很乱。连接位点应作为内部锚点隐藏；用户通过“连接分子”按钮进入连续连线状态，或按住 Shift 临时进入连续连线状态；每次点击分子会从上一个分子自动连到当前分子，并把当前分子作为下一段起点。连接线应使用更粗的深色 smoothstep 箭头，选中态再用蓝色强调。画布需要提供“一键删除全部连线”。
- 用户对分子块之间的连接线更偏好几何直觉：当 B 在 A 上方时，应从 A 顶部中心连到 B 底部中心并画成一条直线；左右关系也应使用左右中心锚点。React Flow 边应使用 `straight` 类型，旧的 `top-a/right-a/...` 等边 handle 需要归一到中心 `top/right/bottom/left`，避免历史数据继续画出多弯折线。
- 合成路线/反应关系线必须显示明确箭头。当前 React Flow 边使用 `MarkerType.ArrowClosed`；旧边加载时按当前节点中心重新计算最近的上下/左右 handle，而不是保留历史错误端点。Edge label 默认隐藏，只在选中边时显示，避免文字压在线和分子块上。
- 2026-06-20 后，画布边不再使用 React Flow `straight` 路径，而是自定义 `orthogonal` edge：起点和终点必须落在 SMILES 块上下左右正中间；路径只允许水平/垂直折线；路由会把其它 SMILES 块作为障碍扩展矩形避开；四侧端点自动选择按“总路径最短 → 弯折最少 → 第一次拐弯前路径最长 → 后续段依次最长”的优先级比较。
- 计算后端状态不应常驻占用右侧任务面板。右上角只保留紧凑“后端”入口，点击后弹窗查看；Gaussian 队列和路线候选属于当前分子/反应的二级窗口入口，不应与分子任务平级常驻展示。
- 任务结果应通过独立 modal 展示；中间区域不再常驻“结果/日志”面板，右侧任务面板只承载当前选中对象的操作。点击路线预测后应直接打开候选 modal，窗口内提供查看、加入当前画布和新建路线单元。
- 计算任务按钮必须绑定到当前单元 `results` 中的稳定任务记录，键格式为“对象类型:对象 ID:任务 ID”。蓝色表示未计算、黄色表示运行中、绿色表示成功、红色表示失败；绿色点击查看结果，红色点击先看错误再重试。任务记录通过单独 API 原子更新，不能为写一个结果而回存整份旧工作区。
- 结果详情继续使用 modal，但任务日志入口不能一起消失。当前单元的任务日志应放在中间面板底部可折叠抽屉中，收起时保留标题和数量，展开后按更新时间查看结果或错误。
- Gaussian 结构优化/频率只能有一个主按钮。点击后打开配置窗口并自动生成默认 `Opt + Freq / B3LYP / 6-31G(d) / 0 / 1` 输入；参数与 GJF 均可编辑，窗口只提供重新生成、关闭和提交，不再分“直接提交”和“高级配置”两条流程。
- 左侧单元卡只显示类型、标题和删除入口；分子/反应数量及反应式预览会挤占空间且信息价值低，不应恢复。
- 路线候选中同一步的多个前体必须放进同一个反应物块，SMILES 用点号连接，例如 `O=C(O)c1ccccc1O.CC(=O)OC(C)=O` 作为一个节点连接到产物，不能拆成两条平行边。单纯用户手动输入多个独立分子时仍可按多行创建多个节点。
- 从某个现有 SMILES 块发起逆合成预测后，插入候选路线必须把预测 target 绑定回这个现有块；不要再新建一个同产物的 `C` 块。对于 `A+B>>C` 这类单步结果，画布应创建一个 `A.B` 点式反应物块并用一条箭头指向现有 `C` 块，这样才能区分“一个合成反应的多个反应物”和“两条独立路线”。
- 如果用户从点式多分子块里的某个内层组分发起逆合成预测，插入路线时反应箭头仍属于外层组合节点，但 SVG path 的终点应穿过外层容器并落到该内层组分卡片的边缘；同一组合块里的其它组分卡片要作为障碍绕开，避免箭头压过相邻分子。
- 路线候选树里可能出现多个 molecule id 共享同一个目标 SMILES。对从内层组分发起的逆合成插入，所有与目标组分 SMILES 相同的 route molecule 都必须映射回原内层目标，不能在外面再复制一个“需要合成的东西”；映射后产生的 self-loop 反应边应跳过。
- 前端改动后应尽量用浏览器/Playwright 检查真实 UI，而不只看 `npm run build`。
- 任务面板中常驻的“查看计算队列（Gaussian）”和“查看路线候选”按钮已被移除。计算队列状态与结果已统一收拢到底部任务日志抽屉；路线预测成功后，点击绿色状态的预测路线任务按钮或任务日志中对应的成功记录，均能直接调起带交互操作（“加入当前画布”/“新建路线单元”）的路线候选弹窗，而不是无操作的静态展示。
- 绿色“已完成”任务按钮不应只能查看旧结果；从任务面板点击已完成任务打开结果/路线候选窗口时，应在窗口底部保留“重新计算”入口，复用该任务原来的运行/重试逻辑。Gaussian 等需要参数的任务仍应保留“修改配置”入口。
- Ketcher 引入的 `ketcher-react/dist/index.css` 含有大量全局样式，与项目自带的通用弹窗样式（如 `.modal-backdrop`、`.modal-header` 等）易发生类名冲突，导致弹窗不居中且 Wasm 交互错位。已将项目中所有 Modal 相关基础类名加前缀升级（如 `.osf-modal-backdrop`）。同时，对嵌入了复杂第三方组件的 Modal 容器，应避免使用 CSS Grid 布局，因为 Grid 布局会将第三方组件在运行时动态生成的 style/div 辅助节点强行作为网格项目进行排位，从而摧毁行高比例。必须统一使用 Flexbox 布局，并通过 `flex: 1` 和 `position: relative` 规范子容器的高度撑满与 Containing Block 定位基准。
- TS 参数窗口曾使用未定义的 `osf-modal-window` 类，导致计算样式背景为完全透明，同时缺少阴影、裁剪和相对定位。TS 窗口应复用 `osf-config-modal` 基类，再由 `ts-config-modal` 覆盖尺寸和网格布局；不要新增没有基础视觉契约的 modal 类名。
- 路线预测结果的展示不应只显示纯文本，当前已实现通过 `RouteCandidatePreview` 结合 `MoleculeDrawing` 和 SVG 路径直接在弹窗渲染反应合成树的预览，增强体验直观度。
- Gaussian 优化的收敛过程图表可通过解析 log 文件中所有 `SCF Done:` 与 `Maximum Force` 提取，并在 `GaussianJobView` 渲染出迭代详情（类似 `temp/main.py` 的实现）。
- FastAPI 后端需要显式映射所有管理器，如果新增管理器（例如 `TsWorkflowManager`），必须在 `api/main.py` 添加对应的 `GET / POST` 路由才能防止前端报 404 错误。
化学结果表达经验：

- 不要把 heuristic/demo 逻辑包装成真实模型结果。
- AiZynthFinder、OPERA、RXNMapper、DRFP/RXNFP、xTB、CREST、GoodVibes、cclib 都是可选工具；不可用时应返回明确 unavailable/disabled/fallback，而不是抛未处理异常。
- 公开权重审计结论记录在 `docs/public-model-weights-audit.md`：AiZynthFinder、OPERA、RXNMapper 是当前可直接依赖的公开模型/权重；ASKCOS 公开模型和数据但部署重且模型/数据为 CC BY-NC-SA；DRFP 不需要权重；RXNFP 有公开预训练反应 BERT 但不是通用产率预测器；没有找到可负责任直接接入的官方通用 organic reaction yield 权重，产率模块应继续明确显示 heuristic/features/no trained model。
- `rxn4chemistry/rxn_yields` 官方安装说明仍基于 Python 3.6 与 RDKit 2020.03.3，且官方 README 明确说明 USPTO 产率分布随质量尺度变化、限制模型适用性。不能把它直接安装进当前 `orgsynflow-chem` 环境或包装成通用产率模型；如后续评估，应使用独立隔离环境并在 UI 展示反应族、数据集和适用域。
- 计算后端调研：xTB 官方仓库是 `grimme-lab/xtb`；CREST 官方仓库/文档是 `crest-lab/crest` 和 `crest-lab.github.io/crest-docs`；cclib 可解析多类量化输出；GoodVibes 可从 Gaussian/ORCA/NWChem/Q-Chem/xTB/ASE 结果计算准谐热化学校正；PySCF、Psi4、geomeTRIC、ASE 可作为开源量化/优化/工作流后端候选。
- Gaussian 是商业闭源软件，不能从 GitHub 或公开源直接安装；WSL 集成需要用户提供合法 Gaussian 安装包和 license/环境变量信息。
- 本机 Windows 已安装 Gaussian 16W：`C:\Users\Meta\AppData\Local\Programs\g16w\g16.exe`。WSL 可通过 `/mnt/c/Users/Meta/AppData/Local/Programs/g16w/g16.exe` 调用该 Windows 可执行文件；`core.gaussian_runner.find_gaussian_executable()` 已加固为先查 PATH，再查 `GAUSS_EXEDIR`，最后扫描 WSL 挂载的 Windows Gaussian 常见路径。
- WSL `orgsynflow-chem` 计算工具链当前可用：xTB 6.7.1、CREST 3.0.2、Open Babel 3.1.0、ASE 3.28.0、geomeTRIC 1.1.1、PySCF 2.13.1、Psi4 1.10.1、cclib、GoodVibes、RDKit。
- Windows 后端服务如果直接找不到 xTB/CREST/Open Babel/Psi4/geomeTRIC，可以桥接 WSL `orgsynflow-chem` 的固定路径：`wsl:/home/meta/.local/opt/miniforge3/envs/orgsynflow-chem/bin/<tool>`。`adapters/xtb_adapter.py` 已支持通过 stdin 把 XYZ 写入 WSL `/tmp/codex/orgsynflow/...` 再运行 CLI，避免 Windows/WSL 路径转换和编码问题。
- 计算后端状态统一由 `/compute/status` 暴露，包含 Gaussian、xTB、CREST、Open Babel、GoodVibes、PySCF、Psi4、geomeTRIC、ASE 的 `available/executable/source`。前端右侧任务面板会显示这些状态。
- WSL 中 OPERA 2.9 已安装在 `/home/meta/.local/opt/OPERA2.9`，可通过 `/home/meta/.local/bin/opera` 运行。Windows 后端需要通过 `wsl:/home/meta/.local/bin/opera` bridge 调用，否则“RDKit + OPERA”会退化为 unavailable。
- WSL `orgsynflow-chem` 中已安装 AiZynthFinder CLI：`/home/meta/.local/opt/miniforge3/envs/orgsynflow-chem/bin/aizynthcli`。但 CLI 需要真实 `--config`/policy/stock/model 文件；若未配置，路线预测应返回明确的 demo fallback 候选，不能显示空成功态或假装真实预测。
- 分子任务面板已有 xTB 和 CREST 按钮。当前实现会用 RDKit 从 SMILES 生成 3D XYZ，再调用 `/compute/xtb` 或 `/compute/crest`；结果和 stdout/stderr 返回到中间结果面板。
- Gaussian opt/freq 默认动作应直接生成 gjf 并提交队列；需要修改方法/基组/电荷/多重度时再打开“Gaussian 高级配置”弹窗。不要让用户先点“生成 gjf”再点“提交作业”作为主路径。
- 路线预测结果要作为可查看候选集，而不是只显示 status。候选集应能从右侧卡片查看详情、插入当前画布并连接到被点击预测的分子，或新建一个路线单元承载整条路线。
- Windows 调 WSL CLI 时必须显式设置 `encoding="utf-8", errors="replace"`，否则 CREST/xTB 输出里的 UTF-8 字符可能被 GBK 解码线程打断，导致 `stdout` 为 `None` 或测试崩溃。
- 长时间 CREST / WSL 外部工具任务被强制中断后，可能留下 `wsl.exe` 客户端挂起，导致 AiZynthFinder、OPERA、RXNMapper、DRFP、xTB、CREST 等所有依赖 WSL 的能力一起表现为“缺失/不可用”。恢复顺序：先停止 OrgSynFlow API/Web，精确清理由 API 派生且命令行含 `/tmp/codex/orgsynflow` 或 `orgsynflow-chem` 的残留 `wsl.exe`，再用 `wsl -e true` 验证基础 WSL；只有清理后仍失败时才升级到重启 `WslService`/WSL。
- TS 相关功能只能说“计划/候选/未验证/验证等级”，不能宣称自动找到正确过渡态。
- 点式多分子画布块必须区分“路线节点身份”和“分子计算身份”：路线仍把 `A.B` 作为一个节点，但分子级任务必须绑定用户在节点内点击的具体组分；结果键使用 `node-id:component:index`，相同 SMILES 也不能合并。
- 通用 TS 扫描不能把所有成键/断键平衡距离写死为 1.5 Å。应按元素共价半径估算（例如 C–Br 约 1.96 Å），且每个受限优化点提交前要把扫描原子实际移动到目标距离，否则 Gaussian 可能在 NewRed/RedCar 内坐标转换阶段失败。
- Windows Gaussian 16W 的 `g16.exe` launcher 可能退出后留下独立 `l*.exe` Link 进程。取消 TS 工作流时除了终止 launcher，还必须只按包含该 workflow 目录的命令行精确终止对应 Link 进程，不能全局结束所有 Gaussian 计算。
- 产率输出必须带 `method`、`confidence`、`applicability_domain`、`note`。
- 结果弹窗不应默认展示大段原始 stdout/stderr/JSON。前端应优先展示结构化摘要、关键数值、警告和路径；原始日志放在可展开的“原始日志 / 原始数据”中。包含 XYZ/GJF 坐标的结果必须先渲染可交互 3D 分子视图。
- 依赖隔离与运行环境统一：Gradio、py3Dmol 与 matplotlib 必须在 Windows (uv) 和 WSL (mamba) 中同时声明与安装。在过渡态库中通过 `core.gaussian_runner.find_gaussian_executable()` 代替硬编码的 `g16.exe` 路径，保证计算服务跨 Windows 和 WSL 均可自动发现和调用 Gaussian 可执行文件，并把中间结果输出至工程统一的工作目录下。
- EAS TS 应用调试经验：`app/eas_ts_app.py` 如果直接用 `python app/eas_ts_app.py` 运行，`app/` 目录会作为工作目录，`from core.eas_ts_lib import *` 因 `core` 不在 sys.path 上而抛 `ModuleNotFoundError`。修复方式是在文件头加 `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))`，同样适用于 `core/eas_ts_lib.py` 自身对 `core.gaussian_runner` 的引用。
- WSL 下运行 Windows Gaussian：直接在 WSL bash 中以 Linux 路径调用 `g16.exe` 会报 `Thread and Process ID are zero in wsystem: No such file or directory`，传入 UNC 路径会报 `PGFIO/stdio: No such file or directory`。正确做法是：①将 OUT_DIR 映射到 `/mnt/c/...` 而非 `/home/...`；②用 `cmd.exe /c 'g16.exe input.gjf'` 而非直接 `subprocess.Popen(['g16.exe', ...])` 启动。
- Gradio UI 锁死：若 Gradio 回调函数中含同步 `process.wait()`，整个 Gradio event loop 会被阻塞，UI 无响应。必须改为 generator 函数，用 `time.sleep(2)` + `process.poll()` 轮询，每次循环 `yield` 进度给 Gradio，既能实时更新界面，也能响应取消请求。
- Conda/Miniforge 路径：本机 WSL 的 conda/mamba 安装位置为 `~/.local/opt/miniforge3`，而非 `~/miniconda3` 或 `~/anaconda3`。正确的初始化命令：`source ~/.local/opt/miniforge3/etc/profile.d/conda.sh && conda activate orgsynflow-chem`。
- WSL Gradio 浏览器错误：WSL 无桌面环境时，Gradio 的 `inbrowser=True` 会触发 `gio: http://localhost:7861/: Operation not supported`，这是无害信息，不代表服务启动失败；可在 WSL 中用 `server_name="0.0.0.0"` 并在 Windows 浏览器访问 WSL 的端口。

服务和启动经验：

- 桌面开关脚本 `scripts/orgsynflow-toggle.ps1` 用 8765 和 5173 端口判断运行状态。
- 启动时后台运行 `uv run python run_api.py` and `npm run dev`。
- 同一个桌面 `.cmd` 再次双击会关闭服务。
- PowerShell 脚本需要兼容 Windows PowerShell 5.1，避免使用 PowerShell 7 独有语法，例如 `??`。
- `.cmd` 中不要用在非交互环境会报错的 `timeout /t`；已改为 `powershell Start-Sleep`。
- 每次对 Python 适配器代码（如 `adapters/aizynth_adapter.py`）进行更改后，必须通过 `scripts/orgsynflow-toggle.ps1` 重启 API 后端服务（Uvicorn 进程），否则进程会一直加载旧的内存模块而忽略新的路径自动解析逻辑，导致即使在 WSL 成功部署并配置好了 policy/stock，API 后端还是会报告未配置 policy/stock/config 并回退到内置演示候选路线。

数据和测试经验：

- `data/workspaces/example-workspace.json` 很容易在浏览器测试、保存工作区、自动化点击时被弄脏。不要把测试创建 of cell、route candidate 或 updated_at 混入提交，除非明确要更新 fixture。
- Vite/Ketcher 构建会出现大 chunk warning，当前是预期现象，不等于构建失败。
- 浏览器自动化若用按钮文本选择，注意 `添加` 与 `添加到画布` 会模糊匹配冲突，应用 exact 匹配。
- Windows 与 WSL 项目副本不会自动同步。Windows 提交推送后，如需 WSL 可用，要在 `/home/meta/Project/Workspaces/orgsynflow` 执行 `git pull --ff-only`。
- 默认工作区文件 `data/workspaces/example-workspace.json` 中如果有之前的 fallback/未配置警告缓存记录（例如 `molecule:mol-ethanol:retrosynthesis` 里的 status / used_fallback 记录），页面初次加载时会由于缓存导致直接在页面展示出“已检测到 AiZynthFinder，但尚未配置...”的失效提示。必须手动清理此类任务结果缓存，恢复为初始的“未计算”状态，以便用户重新发起真实的逆合成计算。

- AiZynthFinder JSON 树的 `children` 会交替出现 molecule 与 reaction 节点；reaction 节点的 `smiles` 是逆合成 reaction SMILES，绝不能作为普通分子加入路线。解析时应跳过 reaction 节点，读取其 molecule children 作为前体，并生成正向 `前体>>产物` 反应式。
- 对组合节点内单个组分预测路线时，插入器必须保留所选 `MoleculeComponent`：复用其外层画布节点作为路线 target，不再创建重复 target 或 `target -> anchor` 伪反应边。
- 路线每个 `precursor_id` 必须生成独立分子节点和独立的 `precursor -> product` 边，不能把同一步全部前体合并为点式伪分子；多组分节点的布局宽度按组件卡实际宽度估算，否则相邻节点会重叠并让正向箭头视觉上折返。
- WSL 的 `/tmp` 在服务重启后可能被清空。AiZynthFinder 每次运行前必须自行 `mkdir -p /tmp/codex/orgsynflow`，不能依赖历史目录残留。
- React Flow 的选中状态同步：在使用 React Flow 内置的 `onNodesChange` / `onEdgesChange` 交互（如 Shift + 点击反选、框选等）时，本地定义的 `selectedNodeId` 和 `selectedEdgeId` 需通过 `useEffect` 进行同步清空或更新。否则会导致“删除选中项”按钮在无选中状态下错误显示，且点击后可能误删未选中的历史节点或由于删除非现有节点导致状态不一致发生卡死。

## 3. Task Board

当前状态：

- [done] 2026-06-20 在 AiZynthFinder 和 ASKCOS 适配器中增加基于 RDKit Canonical SMILES 的路线去重和循环路径拦截（如果前体与目标或祖先节点完全一致，则自动剪除该冗余节点），以解决相同分子重复出现并导致冗余的问题。
- [done] 2026-06-20 修复删除选中项按钮在无选中时显示以及点击卡住/误删的问题：更新 `web/src/App.tsx` 中的渲染判定条件和删除逻辑为仅限当前实际选中的节点和边；引入了 `useEffect` 用于同步 React Flow 的 selection 状态，确保在 deselect 时 `selectedNodeId` 和 `selectedEdgeId` 能够同步清空，并同步更新任务面板。
- [done] 2026-06-20 合并 temp/ 目录下的 3 个过渡态搜索/绘图文件到 WSL 和 Windows 仓库，并更新 Python 依赖关系：安装/配置了 gradio、py3Dmol、matplotlib；测试均能正常 import 且编译成功。
- [done] 2026-06-20 修复 EAS TS 应用合并后完全无效问题：诊断出三个根本原因：①`from core.eas_ts_lib import *` 因 sys.path 未包含项目根目录而失败；②Gradio 回调中 `process.wait()` 阻塞导致 UI 完全锁死；③WSL 下直接调用 `g16.exe` 产生 `wsystem` 错误/UNC 路径错误。已分别修复：添加 sys.path bootstrap、改 generator 函数 yield 进度、将 OUT_DIR 映射到 `/mnt/c/...` 并用 `cmd.exe /c` 包装 g16.exe 启动命令。验证：WSL 下 `conda activate orgsynflow-chem && python app/eas_ts_app.py` 可正常启动 Gradio 服务，无异常退出。
- [done] 2026-06-20 增加 SMILES 块删除：选中块后可显式删除，同时清理相邻箭头、关联反应及选中/连线状态；保存工作区后刷新不会复活。
- [done] 2026-06-20 修复组合节点组分级逆合成插入：AiZynthFinder reaction 节点不再误作分子；多个前体拆为独立结构；复用所选目标节点；路线和原反应箭头均保持前体到产物的正向顺序；多组分宽度与下游间距已校正。
- [done] 2026-06-20 修复逆合成候选插入语义：从现有 SMILES 块预测路线时强制复用该产物块；同一步多个前体合并为一个点式 SMILES 反应物块，并只生成一条反应箭头指向产物。
- [done] 2026-06-20 修复点式多分子目标的路线箭头端点：从内层组分预测路线后，新增反应边会把 `targetComponentIndex` 持久化到 edge data，渲染时把终点定位到目标组分边缘，并把同块其它组分作为路由障碍。
- [done] 2026-06-20 修复路线候选重复目标节点：从任务日志/旧结果打开路线候选时，会按 `target_smiles` 在当前 cell 中反查目标分子/组分；所有与目标组分同 SMILES 的 route molecule id 映射到原节点，并跳过映射后 source=target 的自环边。
- [done] 2026-06-20 优化任务面板已完成任务：点击绿色完成态任务打开结果或路线候选窗口时，窗口底部提供“重新计算”按钮，失败态仍沿用错误窗口重试逻辑。
- [done] 三阶段计划已写入 `plan.md`。
- [done] 基础 CLI、适配器、API、测试面已建立。
- [done] OPERA 已由用户下载并安装到 WSL 本地 opt 路径，且可被全局引用。
- [done] React/Vite 主工作区前端已建立。
- [done] 深色永久侧栏已移除。
- [done] 顶部工作区下拉菜单已实现。
- [done] 白色可隐藏单元栏已实现。
- [done] 通用化学单元已替代 UI 层面的分子/反应/路线固定分型。
- [done] 分子节点已改为结构图渲染，不再显示巨大标题。
- [done] `CO2.H2O` 等点式小分子组合已支持多组分结构图显示；无法可靠推断结构的公式/水合物点式再降级为公式 SVG，不再卡在结构渲染加载态。
- [done] 结果/日志面板已移入中间工作面板并改为浅色显示。
- [done] 手动画布箭头已支持选中删除，禁止自连接，且不会再误打开无关反应任务。
- [done] 同一个 SMILES/结构已允许重复加入画布。
- [done] 分子节点连接位点已扩展为 8 个。
- [done] 分子节点周边可见蓝色连接点已隐藏；连接关系改为“连接分子”连续连线模式，支持按钮切换或按住 Shift 临时进入；连接线已加粗加深，并提供删除全部连线。
- [done] 连接线已改为按节点相对位置自动选择上下/左右中心锚点，并使用直线边，避免上下连接时出现歪斜和多段弯折。
- [done] WSL 已可复用 Windows Gaussian 16W；项目 Gaussian runner 能在 Windows 与 WSL 路径下发现该可执行文件。
- [done] WSL `orgsynflow-chem` 已安装/确认 xTB、CREST、Open Babel、ASE、geomeTRIC、PySCF、Psi4、cclib、GoodVibes 等计算工具。
- [done] Windows 后端已桥接 WSL OPERA 和 WSL AiZynthFinder CLI，并在 `/compute/status` 暴露 OPERA/AiZynthFinder 状态。
- [done] 路线预测 UI 已改为可查看候选卡，候选可加入当前画布或新建路线单元；无 AiZynthFinder config 时显示明确 demo fallback。
- [done] Gaussian 分子任务已改为默认直接提交 opt/freq，高级配置弹窗提供 job type、method、basis、charge、multiplicity 和 gjf 预览。
- [done] 右侧面板已移除常驻后端状态、路线候选集和 Gaussian 队列；后端状态移到顶部小弹窗入口，候选与队列移到当前对象任务下的二级窗口。
- [done] 任务结果已改为 modal 展示，中间常驻结果区已移除；路线预测完成后直接打开候选 modal 并可执行插入操作。
- [done] 任务按钮已统一为中文“计算内容（引擎）”，并接入蓝/黄/绿/红持久状态、结果查看、错误提示和重试流程。
- [done] Gaussian Opt/Freq 已合并为单一按钮；配置弹窗打开后自动生成默认 GJF，允许修改参数和原始输入后提交。
- [done] 中间面板底部已恢复可折叠任务日志抽屉；左侧单元卡的数量与反应式预览已删除。
- [done] 新增单元任务结果原子更新接口；Gaussian 队列状态会轮询回写任务记录，页面刷新后不可恢复的同步任务会标记为失败。
- [done] 画布关系线已移除 marker 箭头楔形；旧边加载时重新计算最近边中心 handle，edge label 默认隐藏。
- [done] 路线同一步多个前体插入画布时会合并为一个点式 SMILES 反应物节点，并用单条带箭头反应边连接产物。
- [done] 单元删除入口已加入。
- [done] 桌面一键开关脚本已创建并验证。
- [done] `AIREADME.md` 已按项目日志结构重写。
- [done] “查看计算队列（Gaussian）”与“查看路线候选”常驻按钮已从分子/反应面板中移除，Gaussian 队列统一收拢至任务日志。
- [done] 路线候选弹窗已直接作为逆合成预测成功及后续查看结果的交互式弹窗，支持通过 TaskButton 及 TaskLogDrawer 随时触发。
- [done] Ketcher 绘图窗口已全局隔离 Modal 类名，并将弹窗重构为 Flexbox 布局，彻底解决了由于第三方组件动态插入辅助节点导致的排版错乱、不居中，以及高度塌陷导致绘图器无法正常画图的问题。
- [done] 已在 WSL 中成功部署下载 AiZynthFinder 官方公开的模型和 stock 数据库，并配置了默认 `config.yml` 路径以进行真实的路线预测。
- [done] 新建了 ASKCOS 逆合成路线预测适配器，支持向 Docker 接口查询，并在离线时优雅 Mock/演示降级。
- [done] 修改 `/route/predict` API 支持 `engine` 分发参数，并在前端添加了引擎选择弹窗，让用户选择使用哪个引擎进行计算并呈现计算就绪状态。
- [done] 2026-06-20 检查确认 AiZynthFinder 公开权重已下载到 WSL：`/home/meta/data/aizynthfinder/config.yml`、`uspto_model.onnx`、`uspto_ringbreaker_model.onnx`、`uspto_filter_model.onnx`、`uspto_templates.csv.gz`、`uspto_ringbreaker_templates.csv.gz`、`zinc_stock.hdf5`。API smoke test 对 aspirin 返回 `used_fallback=false`。
- [done] RXNMapper 和 DRFP 已改为通过 WSL `orgsynflow-chem` fallback 调用和探测，`/compute/status` 中 `rxnmapper`、`drfp` 均显示可用。
- [done] Phenol acetylation 示例已改为单个点式反应物块 `O=C(O)c1ccccc1O.CC(=O)OC(C)=O` 指向 aspirin，旧的失败/不可用任务缓存已清空。
- [done] 过渡态任务已合并为单一“计算过渡态（Gaussian）”入口；点击后打开参数化窗口，包含 TS 搜索建议、方法/基组/电荷/多重度/作业类型、相对位移/旋转滑块、3D 构象预览和 GJF 预览。
- [done] 反应/路线箭头已改为智能正交路由，支持四侧中心自动端点选择、横竖折线、避开其它 SMILES 块，以及按路径长度/弯折数/前段长度排序。
- [done] 完成公开模型/权重审计并写入 `docs/public-model-weights-audit.md`：确认 AiZynthFinder/OPERA/RXNMapper/DRFP 当前状态，记录 ASKCOS、RXNFP、Yield-BERT、Chemprop 的可用性与限制。
- [done] 结果展示已从直接铺原始 log/JSON 改为摘要化展示：xTB/CREST/Gaussian 提取状态、关键指标、日志摘要和警告，原始日志折叠；xTB/CREST payload 会返回 `data.input_xyz`，前端对 XYZ/GJF 坐标渲染 3Dmol 可交互分子结构。
- [done] “计算过渡态参数配置 (GaussView 辅助)”窗口已接入统一 `osf-config-modal` 基类，恢复不透明白色背景、阴影、裁剪和正确定位。
- [done] 点式多分子节点已支持在画布内直接点击具体组分；全部分子级任务、结果状态和 Gaussian object ID 均隔离到组分级，路线/反应仍使用外层组合节点。
- [done] 新增持久化通用 Gaussian TS 工作流：RXNMapper 键变化、三个初始构象、1D/2D 扫描、自适应细化、TS/Freq、虚频模式投影、IRC、端点热化学、暂停/续算/取消/导出以及 API/CLI/React 看板。
- [done] TS 默认理论级别更新为 wB97XD/def2SVP；电荷/多重度自动推断，方法、基组、溶剂、资源、温度和虚频阈值可编辑。
- [done] 用户授权后通过管理员权限重启 `WslService`，Ubuntu WSL 已恢复；AiZynthFinder 官方公开数据、RXNMapper 和 OPERA 均完成文件/运行时/真实推理复核。AiZynthFinder 对 aspirin 返回 2 条真实路线且 `used_fallback=false`；RXNMapper 对 `CCO>>CC=O` 的映射置信度为 `0.998663`；OPERA 对乙醇返回 5 项 QSAR 预测及适用域。

当前可运行入口：

- [ready] 桌面双击 `C:\Users\Meta\Desktop\OrgSynFlow Toggle.cmd` 开关服务。
- [ready] 前端 `http://127.0.0.1:5173/`。
- [ready] API `http://127.0.0.1:8765/health`。
- [ready] CLI `uv run python run_cli.py ...`。
- [ready] WSL 镜像 `/home/meta/Project/Workspaces/orgsynflow`。

待继续增强：

- [todo] 路线候选预览窗口还需要做得更像“候选路线浏览器”：预览多条路径、选择满意路径后插入当前工作区画布。
- [todo] 路线画布的多步反应布局还需要优化，尤其是多反应、多反应物、多产物时的分层布局。
- [done] 反应箭头的可视化应更明确：箭头可选中、可显示 step label、可打开反应任务。
- [todo] Ketcher 绘图输入需要进一步验证：绘制后回填 SMILES、加入画布、结构渲染三步应稳定。
- [todo] 工作区保存/自动保存策略需要更清楚，避免测试或打开示例时污染 fixture。
- [todo] AiZynthFinder 真实配置、stock/policy 路径和路线树解析仍可继续强化。
- [todo] OPERA 输出字段在 UI 中还需要更好地结构化展示。
- [done] Gaussian TS 已具备映射反应中心、可编辑 scan 坐标、1D/2D 扫描、freq/IRC 回填和验证等级闭环；后续重点转为更多反应类型基准与长时间真实计算验证。
- [done] WSL 计算工具状态和 Gaussian bridge 状态已暴露到 `/compute/status` 和右侧任务面板。
- [done] xTB/CREST 已接入分子任务按钮，可从当前前端直接运行并把结果送到中间结果面板。
- [todo] 继续把 PySCF/Psi4/geomeTRIC 接入具体任务按钮，而不只是环境可用。
- [todo] 产率/动力学/热力学结果还需要聚合到路线级评分：总收率、最高能垒、限速步、主要风险。
- [todo] 如需真实 ML 产率层，优先评估 `rxn4chemistry/rxn_yields` 或其他窄领域公开模型，并在 UI 中强制展示训练数据来源、反应族/适用域和不确定性；不要把 RXNFP/DRFP 特征本身显示成预测产率。
- [todo] README 中部分 React 工作区描述可能滞后于当前“通用化学单元”设计，后续可同步更新。

最近一次验证基线：

- 2026-06-20 SMILES 块删除回归：`cd web; npm run build` 成功；浏览器中 4 节点/2 边场景删除首个相连节点后变为 3 节点/1 边，保存并刷新后仍为 3/1；测试后已从 `%LOCALAPPDATA%\Temp\codex\orgsynflow-smiles-delete-test\` 恢复原工作区文件并复核为 4/2，SHA256 与测试前一致。
- 2026-06-20 组分级路线回归：`uv run pytest -q tests/test_aizynth_adapter.py tests/test_route_layout.py` 为 3 passed；`cd web; npm run build` 成功。隔离工作区真实运行 AiZynthFinder 后返回 1 步、2 个前体；加入画布得到两个独立前体节点，位置为 `x=40`，复用的组合 target 为 `x=300`，原下游产物调整为 `x=738`；两条新边均为前体 → 组合 target，原边为组合 target → 产物，全部 marker 位于终点。隔离工作区验证后已删除。
- `uv run pytest -q`：36 passed。
- 前端构建命令：`cd web; npm run build`。
- 任务面板状态回归：浏览器确认蓝色 `rgb(37,99,235)`、黄色 `rgb(244,180,0)`、绿色 `rgb(22,128,60)`、红色 `rgb(201,52,52)`；成功/失败状态刷新后仍存在，失败按钮先打开错误窗口。
- 任务面板布局回归：1280px 与 819px 视口均无页面横向滚动；819px 下三栏宽度约为 210/369/240px，工具按钮不再逐字换行；左侧预览为空，底部日志入口可见。
- `CO2.H2O` UI 回归检查：本机 Chrome + Playwright 打开 `http://127.0.0.1:5173/`，添加节点后确认多组分结构 SVG 已显示；截图在 `%LOCALAPPDATA%\Temp\codex\orgsynflow\co2-h2o-component-structures-ui-check.png`。
- 布局/箭头 UI 回归检查：本机 Chrome + Playwright 确认结果面板在 `.detail` 内、浅色显示；手动画布边可创建并通过“删除箭头”删除；819px 视口下中间面板宽度约 280px；截图在 `%LOCALAPPDATA%\Temp\codex\orgsynflow\layout-edge-fix-ui-check.png`。
- 重复结构/连接位点 UI 回归检查：本机 Chrome + Playwright 输入 `CCO\nCCO` 后新增 2 个 CCO 节点；每个分子节点有 8 个 handle；截图在 `%LOCALAPPDATA%\Temp\codex\orgsynflow\duplicate-molecule-handles-ui-check.png`。
- WSL 计算环境检查：Windows `g16.exe` 可从 WSL 调用；`core.gaussian_runner.run_gaussian_job()` 在 WSL 下跑水分子 HF/STO-3G smoke test 正常结束，并解析出 final energy/HOMO/LUMO；xTB/CREST/Open Babel/ASE/geomeTRIC/PySCF/Psi4/cclib/GoodVibes/RDKit 可用。
- WSL 量化 smoke test：PySCF H2/STO-3G energy `-1.11675931`；Psi4 H2/STO-3G energy `-1.11678332`；Gaussian16W H2O HF/STO-3G 正常结束。
- 计算 API smoke test：`/compute/status` 返回 Gaussian Windows bridge 和 WSL xTB/CREST/Open Babel/PySCF/Psi4/geomeTRIC/GoodVibes/ASE；`/compute/xtb` 对 `O` 返回 `total_energy_hartree=-5.06897994546`；`/compute/crest` 对 `O` 正常 returncode 0。
- 前端 UI 检查：内置浏览器刷新 `http://127.0.0.1:5173/` 后右侧任务面板显示计算后端状态；选中 CCO 分子后出现 `xTB 优化/能量`、`CREST 构象搜索`；点击 xTB 后结果面板显示 `xTB CLI via WSL` 和 `/tmp/codex/orgsynflow/xtb_jobs/...`。
- WSL OPERA/AiZynthFinder 检查：`/compute/status` 返回 `opera` 为 `wsl:/home/meta/.local/bin/opera`、`aizynthfinder` 为 `wsl:/home/meta/.local/opt/miniforge3/envs/orgsynflow-chem/bin/aizynthcli`；`/molecule/properties include_opera=true` 对 `CCO` 返回 OPERA `melting_point=-114`、`boiling_point=78`、`logp=-0.31`。
- 路线候选 UI 检查：内置浏览器选中 CCO 后可见 `RDKit + OPERA QSAR 物性`、`预测逆合成路线`、`提交 Gaussian opt/freq`、`Gaussian 高级配置`；点击路线预测后出现候选卡、fallback 提示、`加入当前画布` 和 `新建路线单元`。
- 二级窗口/连线 UI 检查：右侧未选中对象时仅显示任务提示，不再出现后端列表、候选卡或队列；顶部有紧凑 `后端` 入口；弹窗内显示后端/路线/队列；反应/路线边必须带 arrow marker，默认可见 edge label 数为 0。
- 路线预测直接弹窗检查：点击 `预测逆合成路线` 后 modal 标题为 `路线候选`，出现 2 个候选卡，并直接显示 `加入当前画布` 与 `新建路线单元`；中间常驻结果面板数量为 0。
- 点式路线插入回归：同一步多个前体现在应合并为一个点式 SMILES 节点，示例检查确认 `O=C(O)c1ccccc1O.CC(=O)OC(C)=O` 为一个节点、到 aspirin 为一条带箭头边。
- 连接 UI 检查：内置浏览器添加三个 CCO 后打开 `连接分子`，依次点击三个分子得到 `edgeCount=2`、`visibleHandles=0`，模式保持开启且提示继续选择下一个分子；点击 `删除全部连线` 后 `edgeCount=0`。
- 直线连接 UI 检查：内置浏览器临时把示例工作区放成上下两个节点，打开 `连接分子` 后点击下方 A 再点击上方 B，生成 `react-flow__edge-straight canvas-edge`，SVG path 为单段 `M 315,317.5L 315,196.5`，`visibleHandles=0`；验证后已恢复示例数据。
- 桌面开关脚本：已验证可启动、关闭、重新启动 8765/5173。
- 2026-06-20 本次验证：`uv run pytest -q` 为 36 passed；`cd web; npm run build` 成功（仅 Vite 大 chunk warning）；API `/compute/status` 返回 AiZynthFinder、RXNMapper、DRFP 均可用；API `/route/predict` 对 aspirin 返回 `used_fallback=false`；浏览器确认前端 `http://127.0.0.1:5173/` 可打开、任务日志默认展开、路线只有一个点式反应物节点和一条带 `marker-end` 的箭头、选中反应后只有一个 TS 按钮、TS 窗口含 6 个移动/旋转滑块和 3D canvas。
- 2026-06-20 正交箭头验证：`cd web; npm run build` 成功；浏览器刷新 `http://127.0.0.1:5173/` 后示例反应边 SVG path 为 `M 310,344L 402,344L 402,336.5L 430,336.5`，所有 segment 均为水平/垂直，且保留 `marker-end` 箭头。
- 2026-06-20 结果展示验证：`cd web; npm run build` 成功；`/compute/xtb` 对 `O` 返回 `data.input_xyz`，可供结果弹窗 3D 渲染；`uv run pytest -q tests/test_route_layout.py tests/test_v5_yield.py` 为 3 passed。全量 `uv run pytest -q` 与 `tests/test_v6_api_service.py` 在本次环境中超时且无输出，需后续单独诊断测试收集/环境探测卡点。
- 2026-06-20 TS 白色背景回归：修复前浏览器计算样式为 `background=rgba(0,0,0,0)`、`overflow=visible`、`position=static`；改用 `osf-config-modal ts-config-modal` 后为 `background=rgb(255,255,255)`、`overflow=hidden`、`position=relative`，并恢复 modal 阴影，1000×648 视口内截图确认白色内容层完整覆盖。
- 2026-06-20 组分/TS 工作流验证：前端构建成功；浏览器确认水杨酸/乙酸酐两个结构可分别选中且任务面板只使用所选 SMILES；TS/Gaussian/API 核心回归 17 passed，非外部探测测试集合 25 passed。真实 SN2 准备对 `CBr.[Cl-]>>CCl.[Br-]` 得到 RXNMapper confidence=1.000、C–Cl 成键/C–Br 断键、3 个候选与 5×5 网格；实际 DFT 全网格未在本轮跑完，取消链路已验证且未保留 workflow Gaussian Link 进程。旧 phase1/phase2/v6 外部适配器测试组仍会受 WSL 探测挂起影响。
- 2026-06-20 公开权重恢复验证：重启 `WslService` 后，`/compute/status` 中 AiZynthFinder、OPERA、RXNMapper、DRFP 及 WSL 计算后端全部 available；`/route/predict` 对 aspirin 返回 `Loaded 2 route(s) from AiZynthFinder via WSL.`、`used_fallback=false`；RXNMapper 映射 `CCO>>CC=O` 得到 `[CH3:1][CH2:2][OH:3]>>[CH3:1][CH:2]=[O:3]`、confidence `0.998663`；OPERA 对 CCO 返回 melting point `-114`、boiling point `78`、LogP `-0.31`、water solubility `1.26`、vapor pressure `1.77`，对应 AD 均为 `1`。
- 2026-06-20 WSL 挂起事故恢复验证：停止 OrgSynFlow 服务后，发现 API 派生的 CREST 与 `/compute/status` WSL 探测残留 `wsl.exe`；`wsl --terminate Ubuntu-24.04` 与 `wsl --shutdown` 均超时，非管理员 shell 无法 `Restart-Service WslService`。精确停止 10 个命令行含 `/tmp/codex/orgsynflow` / `orgsynflow-chem` 的残留 `wsl.exe` 后，`wsl -e true` 恢复为 exit code 0；重启 OrgSynFlow 后，`/route/predict` 对 aspirin 返回 `used_fallback=false`、`available=true`，OPERA 对 CCO 返回 melting point `-114`、boiling point `78`、LogP `-0.31`、water solubility `1.26`、vapor pressure `1.77`，`/compute/status` 中 AiZynthFinder、OPERA、RXNMapper、DRFP、CREST 均 available。
- 2026-06-20 已完成任务重新计算入口验证：`cd web; npm run build` 成功（仅 Vite 大 chunk warning）；使用本机 Chrome headless 打开 `http://127.0.0.1:5173/`，临时添加 CCO 节点并运行“计算分子描述符（RDKit）”，任务按钮变为 `task-status-succeeded`，首次结果弹窗和再次点击绿色按钮打开的结果弹窗均出现“重新计算”。测试前后已从 `%LOCALAPPDATA%\Temp\.agents\orgsynflow\example-workspace.before-recompute-ui.json` 恢复 `data/workspaces/example-workspace.json`，SHA256 均为 `0D7CA51DD36D940DFDAC7CAE89722F0298C6AE6155A44F3B7B0F1A36B8F2756F`。
- 2026-06-20 逆合成候选插入修复验证：`cd web; npm run build` 成功（仅 Vite 大 chunk warning）；`uv run pytest -q tests/test_route_layout.py tests/test_workspace_api.py` 为 5 passed。代码检查确认 `addRouteCandidateToCell()` 会复用当前选中产物节点，并把同一步多前体候选投影为一个点式 SMILES reactant 节点与一条产物箭头。
- 2026-06-20 组分级路线箭头端点验证：`cd web; npm run build` 成功（仅 Vite 大 chunk warning）；`uv run pytest -q tests/test_route_layout.py tests/test_workspace_api.py` 为 5 passed。Chrome/Playwright 使用临时工作区验证 `c1ccccc1.O=C1CCC(=O)N1Br` 中第二个组分作为逆合成目标时，插入候选后 edge path 为 `M 528,337.5L 678,337.5L 678,252L 706,252`，终点落在目标组分左边缘，且绕开左侧相邻组分；截图在 `%LOCALAPPDATA%\Temp\.agents\orgsynflow-route-component-endpoint.png`，临时工作区已删除。
- 2026-06-20 重复目标节点回归验证：`cd web; npm run build` 成功（仅 Vite 大 chunk warning）；`uv run pytest -q tests/test_route_layout.py tests/test_workspace_api.py` 为 5 passed。Chrome/Playwright 使用临时工作区构造 route 中 `target` 与 `dup` 两个 molecule id 共享 `O=C1CCC(=O)N1Br` 的候选路线；插入后 `targetStandaloneNodes=[]`，只保留原组合块中的目标组分，edge path 为 `M 468,297.5L 678,297.5L 678,252L 706,252`；截图在 `%LOCALAPPDATA%\Temp\.agents\orgsynflow-no-duplicate-target.png`，临时工作区已删除。

## 4. New Issues

- [done] 2026-06-20 修复“3D 构象预览 (类似 GaussView)”不可用：3Dmol 改为前端本地依赖并统一加载，viewer 高度不再被 flex 压缩；支持画布/分子卡选择组分、视图/选择/移动模式、拖拽 XY 平移、Shift+拖拽 Z 平移、方向键微调、逐分子 XYZ 旋转、重置/居中和原子编号。预览坐标与 GJF 输入联动。浏览器回归确认 canvas=1、外部 CDN script=0、容器高 350px，拖拽后 X/Y 由 0/0 变为 1.2/-0.4 且 GJF 改变，重置后恢复；`npm run build` 成功，路线/工作区测试 5 passed。
- [done] 2026-06-20 修复 CREST 不可用结果被前端误记为成功的问题：通用任务会根据 payload 的 `available/status` 推断失败状态并保留 `reason`；历史上已缓存为 `succeeded + unavailable` 的记录也会显示为失败、允许重试。实时 API 已通过 WSL CREST 3.0.2 对水分子完成构象搜索（return code 0），确认当前工具链可用。
- [todo] Ketcher 绘图窗口仍未居中且无法使用。已尝试在 `web/src/styles.css` 中移除 `.osf-ketcher-host > div` 的 flex 布局并提交（commit e1b4eb0），但窗口仍表现异常，需要进一步调试布局和可能的全局 CSS 冲突。

- [done] 2026-06-20 Fix canvas UI interactions: allow dragging blocks from sub-molecules, and add selected styling to single-molecule blocks.
