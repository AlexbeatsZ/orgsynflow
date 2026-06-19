# AIREADME.md

本文件是 OrgSynFlow 的项目日志和 AI 接手手册。对于这个有独立文件夹的项目，每次新对话开始时应先读取本文件；如果不存在则创建。每次任务完成后，应把新经验、当前状态和未解决事项写回本文件。

## 1. Project Goal

OrgSynFlow 的总目标是构建一个本地优先、可插拔的有机合成工作台，把分子、反应、路线、性质预测、Gaussian 计算、过渡态规划、动力学和产率估计整合到一个连续工作流里。

当前产品方向：

- React/Vite 前端作为主要交互界面，地址为 `http://127.0.0.1:5173/`。
- FastAPI 后端提供可测试接口，地址为 `http://127.0.0.1:8765/`。
- CLI `run_cli.py` 保留为稳定自动化入口。
- Streamlit `app/main.py` 和 Tkinter `desktop_app.py` 是旧入口/调试入口，不是当前主要 UI。
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

前端 UX 经验：

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
- React Flow `markerEnd` 会在分子节点边缘形成黑色楔形，尤其是节点遮挡箭头尖端时。当前关系线不使用箭头 marker；旧边加载时按当前节点中心重新计算最近的上下/左右 handle，而不是保留历史错误端点。Edge label 默认隐藏，只在选中边时显示，避免文字压在线和分子块上。
- 计算后端状态不应常驻占用右侧任务面板。右上角只保留紧凑“后端”入口，点击后弹窗查看；Gaussian 队列和路线候选属于当前分子/反应的二级窗口入口，不应与分子任务平级常驻展示。
- 任务结果应通过独立 modal 展示；中间区域不再常驻“结果/日志”面板，右侧任务面板只承载当前选中对象的操作。点击路线预测后应直接打开候选 modal，窗口内提供查看、加入当前画布和新建路线单元。
- 计算任务按钮必须绑定到当前单元 `results` 中的稳定任务记录，键格式为“对象类型:对象 ID:任务 ID”。蓝色表示未计算、黄色表示运行中、绿色表示成功、红色表示失败；绿色点击查看结果，红色点击先看错误再重试。任务记录通过单独 API 原子更新，不能为写一个结果而回存整份旧工作区。
- 结果详情继续使用 modal，但任务日志入口不能一起消失。当前单元的任务日志应放在中间面板底部可折叠抽屉中，收起时保留标题和数量，展开后按更新时间查看结果或错误。
- Gaussian 结构优化/频率只能有一个主按钮。点击后打开配置窗口并自动生成默认 `Opt + Freq / B3LYP / 6-31G(d) / 0 / 1` 输入；参数与 GJF 均可编辑，窗口只提供重新生成、关闭和提交，不再分“直接提交”和“高级配置”两条流程。
- 左侧单元卡只显示类型、标题和删除入口；分子/反应数量及反应式预览会挤占空间且信息价值低，不应恢复。
- 路线候选中的点式多组分 SMILES（例如 `CO.O`）表示多个分子节点，插入画布时必须按点拆分为 `CO` 和 `O` 两个框并分别连接到产物，不能把整串放进一个分子框。
- 前端改动后应尽量用浏览器/Playwright 检查真实 UI，而不只看 `npm run build`。
- 任务面板中常驻的“查看计算队列（Gaussian）”和“查看路线候选”按钮已被移除。计算队列状态与结果已统一收拢到底部任务日志抽屉；路线预测成功后，点击绿色状态的预测路线任务按钮或任务日志中对应的成功记录，均能直接调起带交互操作（“加入当前画布”/“新建路线单元”）的路线候选弹窗，而不是无操作的静态展示。
- Ketcher 引入的 `ketcher-react/dist/index.css` 含有大量全局样式，与项目自带的通用弹窗样式（如 `.modal-backdrop`、`.modal-header` 等）易发生类名冲突，导致弹窗不居中且 Wasm 交互错位。已将项目中所有 Modal 相关基础类名加前缀升级（如 `.osf-modal-backdrop`）。同时，对嵌入了复杂第三方组件的 Modal 容器，应避免使用 CSS Grid 布局，因为 Grid 布局会将第三方组件在运行时动态生成的 style/div 辅助节点强行作为网格项目进行排位，从而摧毁行高比例。必须统一使用 Flexbox 布局，并通过 `flex: 1` 和 `position: relative` 规范子容器的高度撑满与 Containing Block 定位基准。

化学结果表达经验：

- 不要把 heuristic/demo 逻辑包装成真实模型结果。
- AiZynthFinder、OPERA、RXNMapper、DRFP/RXNFP、xTB、CREST、GoodVibes、cclib 都是可选工具；不可用时应返回明确 unavailable/disabled/fallback，而不是抛未处理异常。
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
- TS 相关功能只能说“计划/候选/未验证/验证等级”，不能宣称自动找到正确过渡态。
- 产率输出必须带 `method`、`confidence`、`applicability_domain`、`note`。

服务和启动经验：

- 桌面开关脚本 `scripts/orgsynflow-toggle.ps1` 用 8765 和 5173 端口判断运行状态。
- 启动时后台运行 `uv run python run_api.py` 和 `npm run dev`。
- 同一个桌面 `.cmd` 再次双击会关闭服务。
- PowerShell 脚本需要兼容 Windows PowerShell 5.1，避免使用 PowerShell 7 独有语法，例如 `??`。
- `.cmd` 中不要用在非交互环境会报错的 `timeout /t`；已改为 `powershell Start-Sleep`。

数据和测试经验：

- `data/workspaces/example-workspace.json` 很容易在浏览器测试、保存工作区、自动化点击时被弄脏。不要把测试创建的 cell、route candidate 或 updated_at 混入提交，除非明确要更新 fixture。
- Vite/Ketcher 构建会出现大 chunk warning，当前是预期现象，不等于构建失败。
- 浏览器自动化若用按钮文本选择，注意 `添加` 与 `添加到画布` 会模糊匹配冲突，应用 exact 匹配。
- Windows 与 WSL 项目副本不会自动同步。Windows 提交推送后，如需 WSL 可用，要在 `/home/meta/Project/Workspaces/orgsynflow` 执行 `git pull --ff-only`。

## 3. Task Board

当前状态：

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
- [done] 路线中的 `CO.O` 等点式前体插入画布时会拆成多个独立分子节点。
- [done] 单元删除入口已加入。
- [done] 桌面一键开关脚本已创建并验证。
- [done] `AIREADME.md` 已按项目日志结构重写。
- [done] “查看计算队列（Gaussian）”与“查看路线候选”常驻按钮已从分子/反应面板中移除，Gaussian 队列统一收拢至任务日志。
- [done] 路线候选弹窗已直接作为逆合成预测成功及后续查看结果的交互式弹窗，支持通过 TaskButton 及 TaskLogDrawer 随时触发。
- [done] Ketcher 绘图窗口已全局隔离 Modal 类名，并将弹窗重构为 Flexbox 布局，彻底解决了由于第三方组件动态插入辅助节点导致的排版错乱、不居中，以及高度塌陷导致绘图器无法正常画图的问题。

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
- [todo] Gaussian TS 输入目前仍偏草稿，需要把 scan 建议、反应中心、freq/IRC 检查状态更完整地贯穿 UI。
- [done] WSL 计算工具状态和 Gaussian bridge 状态已暴露到 `/compute/status` 和右侧任务面板。
- [done] xTB/CREST 已接入分子任务按钮，可从当前前端直接运行并把结果送到中间结果面板。
- [todo] 继续把 PySCF/Psi4/geomeTRIC 接入具体任务按钮，而不只是环境可用。
- [todo] 产率/动力学/热力学结果还需要聚合到路线级评分：总收率、最高能垒、限速步、主要风险。
- [todo] README 中部分 React 工作区描述可能滞后于当前“通用化学单元”设计，后续可同步更新。

最近一次验证基线：

- `uv run pytest -q`：35 passed。
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
- 二级窗口/连线 UI 检查：右侧未选中对象时仅显示任务提示，不再出现后端列表、候选卡或队列；顶部有紧凑 `后端` 入口；弹窗内显示后端/路线/队列；画布 `markerCount=0`、默认可见 edge label 数为 0。
- 路线预测直接弹窗检查：点击 `预测逆合成路线` 后 modal 标题为 `路线候选`，出现 2 个候选卡，并直接显示 `加入当前画布` 与 `新建路线单元`；中间常驻结果面板数量为 0。
- 点式路线插入回归：临时注入前体 `CO.O` 的路线候选并点击 `加入当前画布`，结果为独立 `CO`、`O` 节点各 1 个，`CO.O` 合并节点 0 个；测试后已原样恢复工作区文件。
- 连接 UI 检查：内置浏览器添加三个 CCO 后打开 `连接分子`，依次点击三个分子得到 `edgeCount=2`、`visibleHandles=0`，模式保持开启且提示继续选择下一个分子；点击 `删除全部连线` 后 `edgeCount=0`。
- 直线连接 UI 检查：内置浏览器临时把示例工作区放成上下两个节点，打开 `连接分子` 后点击下方 A 再点击上方 B，生成 `react-flow__edge-straight canvas-edge`，SVG path 为单段 `M 315,317.5L 315,196.5`，`visibleHandles=0`；验证后已恢复示例数据。
- 桌面开关脚本：已验证可启动、关闭、重新启动 8765/5173。

## 4. New Issues

- [todo] Ketcher 绘图窗口仍未居中且无法使用。已尝试在 `web/src/styles.css` 中移除 `.osf-ketcher-host > div` 的 flex 布局并提交（commit e1b4eb0），但窗口仍表现异常，需要进一步调试布局和可能的全局 CSS 冲突。
