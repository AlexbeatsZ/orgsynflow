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
- 前端改动后应尽量用浏览器/Playwright 检查真实 UI，而不只看 `npm run build`。

化学结果表达经验：

- 不要把 heuristic/demo 逻辑包装成真实模型结果。
- AiZynthFinder、OPERA、RXNMapper、DRFP/RXNFP、xTB、CREST、GoodVibes、cclib 都是可选工具；不可用时应返回明确 unavailable/disabled/fallback，而不是抛未处理异常。
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
- [done] 单元删除入口已加入。
- [done] 桌面一键开关脚本已创建并验证。
- [done] `AIREADME.md` 已按项目日志结构重写。

当前可运行入口：

- [ready] 桌面双击 `C:\Users\Meta\Desktop\OrgSynFlow Toggle.cmd` 开关服务。
- [ready] 前端 `http://127.0.0.1:5173/`。
- [ready] API `http://127.0.0.1:8765/health`。
- [ready] CLI `uv run python run_cli.py ...`。
- [ready] WSL 镜像 `/home/meta/Project/Workspaces/orgsynflow`。

待继续增强：

- [todo] 路线候选预览窗口还需要做得更像“候选路线浏览器”：预览多条路径、选择满意路径后插入当前工作区画布。
- [todo] 路线画布的多步反应布局还需要优化，尤其是多反应、多反应物、多产物时的分层布局。
- [todo] 反应箭头的可视化应更明确：箭头可选中、可显示 step label、可打开反应任务。
- [todo] Ketcher 绘图输入需要进一步验证：绘制后回填 SMILES、加入画布、结构渲染三步应稳定。
- [todo] 工作区保存/自动保存策略需要更清楚，避免测试或打开示例时污染 fixture。
- [todo] AiZynthFinder 真实配置、stock/policy 路径和路线树解析仍可继续强化。
- [todo] OPERA 输出字段在 UI 中还需要更好地结构化展示。
- [todo] Gaussian TS 输入目前仍偏草稿，需要把 scan 建议、反应中心、freq/IRC 检查状态更完整地贯穿 UI。
- [todo] 产率/动力学/热力学结果还需要聚合到路线级评分：总收率、最高能垒、限速步、主要风险。
- [todo] README 中部分 React 工作区描述可能滞后于当前“通用化学单元”设计，后续可同步更新。

最近一次验证基线：

- `uv run pytest -q`：34 passed。
- 前端构建命令：`cd web; npm run build`。
- `CO2.H2O` UI 回归检查：本机 Chrome + Playwright 打开 `http://127.0.0.1:5173/`，添加节点后确认多组分结构 SVG 已显示；截图在 `%LOCALAPPDATA%\Temp\codex\orgsynflow\co2-h2o-component-structures-ui-check.png`。
- 桌面开关脚本：已验证可启动、关闭、重新启动 8765/5173。
