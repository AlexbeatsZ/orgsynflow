# OrgSynFlow 三阶段可实操集成计划

## Summary

本计划把 `orgsynflow` 从“演示级有机合成工作台”升级为“可插拔的合成路线、性质预测、量化计算与动力学编排平台”。

默认选择：

- 运行环境：本机轻量优先，重型系统后续 sidecar 化。
- 第一阶段范围：适配器骨架 + 统一 CLI + 可测试接口。
- CLI 形态：新增根目录 `run_cli.py`，不改成正式 Python package。
- 每阶段完成后必须运行测试并确认通过，才能进入下一阶段。
- 本机临时文件统一写入 `%LOCALAPPDATA%\Temp\codex\orgsynflow\...`。

参考项目：AiZynthFinder、ASKCOS、RXNMapper、DRFP/RXNFP、OPERA、Chemprop、xTB/CREST、cclib、GoodVibes、RMG、AutoTST、KinBot、YARP。

## Phase 1：基础适配器、CLI 与可观测测试面

目标：先把“外部工具可插拔、可检测、可测试”的底座做稳，不强行装齐所有模型。

实施内容：

- 新增统一适配器协议：工具名称、能力声明、可用性检测、输入输出、错误信息、来源追踪、置信度字段。
- 将现有 AiZynthFinder、Gaussian runner、RDKit 分子摘要包装成适配器风格，保持现有 API/桌面功能不破坏。
- 新增 `run_cli.py`，提供最小命令行接口：
  - `uv run python run_cli.py health`
  - `uv run python run_cli.py adapters`
  - `uv run python run_cli.py molecule "CC(=O)Oc1ccccc1C(=O)O"`
  - `uv run python run_cli.py route "CC(=O)Oc1ccccc1C(=O)O" --max-routes 3`
  - `uv run python run_cli.py gaussian-status`
  - `uv run python run_cli.py gaussian-input "CCO" --job-type "opt freq"`
- 新增服务层函数，让 CLI、FastAPI、桌面程序复用同一套核心逻辑。
- 所有外部工具检测只读执行，不自动安装，不修改全局环境。

测试门槛：

- `uv run pytest -q`
- `uv run python run_cli.py health`
- `uv run python run_cli.py adapters`
- `uv run python run_cli.py molecule "CCO"`
- `uv run python run_cli.py route "CC(=O)Oc1ccccc1C(=O)O" --max-routes 1`
- `uv run python run_cli.py gaussian-status`

验收标准：

- 现有测试继续通过。
- CLI 在无 AiZynthFinder、无 OPERA、无 xTB 等情况下仍可返回清晰的 unavailable 状态。
- 不可用外部工具不会导致主程序崩溃。
- `plan.md` 已写入并与实际 CLI 命令一致。

## Phase 2：真实路线与性质预测集成

目标：把路线预测和分子物性从规则演示推进到可用外部工具/模型结果。

实施内容：

- 强化 AiZynthFinder 适配器：
  - 支持显式配置文件路径、stock 文件、policy 模型路径。
  - 解析路线树、stock 命中、路线步数、policy score、失败原因。
  - 输出统一 `RouteCandidate` 结构，兼容现有 route/report/UI。
- 新增 OPERA 适配器：
  - 检测 OPERA CLI 是否可用。
  - 输入 SMILES，输出 melting point、boiling point、LogP、水溶解度、蒸气压、适用域信息。
  - OPERA 不存在时返回 unavailable，不影响 RDKit 基础性质。
- 新增 Mordred/RDKit 扩展描述符入口：
  - RDKit 继续作为基础必选层。
  - Mordred 作为可选增强层，用于 ML 特征导出。
- 新增性质 CLI：
  - `uv run python run_cli.py properties "CCO"`
  - `uv run python run_cli.py properties "CCO" --include-opera`
  - `uv run python run_cli.py descriptors "CCO" --format json`
- 更新报告：
  - 明确区分“RDKit 描述符”“QSAR/OPERA 预测”“外部模型不可用/未运行”。
  - 路线卡片加入来源、stock 命中率、模型分数、失败原因。

测试门槛：

- `uv run pytest -q`
- `uv run python run_cli.py adapters`
- `uv run python run_cli.py properties "CCO"`
- `uv run python run_cli.py properties "CCO" --include-opera`
- `uv run python run_cli.py route "CC(=O)Oc1ccccc1C(=O)O" --max-routes 3`
- 若本机未安装 OPERA/AiZynthFinder，测试应验证 graceful fallback；若已安装，则增加 smoke test 验证真实输出解析。

验收标准：

- 路线预测可清晰显示 demo fallback、AiZynthFinder unavailable、AiZynthFinder success 三种状态。
- 性质预测结果带来源和置信/适用域说明。
- UI/API/CLI 对相同输入返回一致核心字段。
- 无外部模型环境下仍能完整运行现有功能。

## Phase 3：量化计算、过渡态与动力学/产率评估

目标：建立可靠的“半自动计算化学工作流”，并把产率预测改成分层置信系统。

实施内容：

- 量化计算链路：
  - 保留 Gaussian 本机 runner。
  - 新增 cclib 解析优先路径，自写 parser 作为 fallback。
  - 新增 GoodVibes 可选热化学校正适配器。
  - 新增 xTB/CREST 可用性检测和 job runner，但默认不自动安装。
- 过渡态半自动流程：
  - 使用 RXNMapper 做 reaction SMILES 原子映射和反应中心识别。
  - 生成 Gaussian scan 输入建议。
  - 支持 TS job 输入生成、freq 检查、一个虚频判据、IRC 结果解析入口。
  - 输出必须标注：未验证、scan 候选、TS 优化完成、freq 合格、IRC 合格。
- 动力学和热力学：
  - 基于 Gaussian/GoodVibes Gibbs free energy 计算 `ΔG_rxn`、`ΔG‡`、Eyring 速率常数。
  - 多步路线输出限速步、最高能垒、热力学风险。
- 产率预测分层：
  - 当前规则估计重命名为 heuristic yield。
  - 新增 DRFP/RXNFP 特征入口。
  - 预留 Chemprop/rxn_yields 模型接口，但没有模型权重时只导出特征和 unavailable 状态。
  - 所有产率输出必须包含 `method`、`confidence`、`applicability_domain`、`note`。
- 新增 CLI：
  - `uv run python run_cli.py reaction-explain "reactants>>products"`
  - `uv run python run_cli.py reaction-map "reactants>>products"`
  - `uv run python run_cli.py ts-plan "reactants>>products"`
  - `uv run python run_cli.py kinetics --reactant-log path --ts-log path --product-log path`
  - `uv run python run_cli.py yield "reactants>>products"`
  - `uv run python run_cli.py reaction-features "reactants>>products" --format json`

测试门槛：

- `uv run pytest -q`
- `uv run python run_cli.py gaussian-input "CCO" --job-type "opt freq"`
- `uv run python run_cli.py reaction-explain "CCO>>CC=O"`
- `uv run python run_cli.py yield "CCO>>CC=O"`
- `uv run python run_cli.py reaction-features "CCO>>CC=O" --format json`
- 使用固定 sample Gaussian logs 测试解析、TS 虚频判据、`ΔG_rxn`、`ΔG‡`、速率常数。
- 外部工具缺失时必须测试 unavailable 状态，不允许失败退出。

验收标准：

- Gaussian/cclib/GoodVibes 解析路径有确定 fallback。
- TS 相关功能不宣称“自动保证正确”，只输出验证等级。
- 产率结果不再伪装成真实模型，清楚区分 heuristic、ML feature、trained model。
- 每条路线可聚合展示路线分数、估计总收率、最高能垒和主要风险。

## Public Interfaces

新增/稳定的命令行接口：

- `run_cli.py health`
- `run_cli.py adapters`
- `run_cli.py molecule <smiles>`
- `run_cli.py properties <smiles> [--include-opera]`
- `run_cli.py descriptors <smiles> [--format json]`
- `run_cli.py route <smiles> [--max-routes N] [--use-aizynth]`
- `run_cli.py gaussian-status`
- `run_cli.py gaussian-input <smiles> [--job-type "..."]`
- `run_cli.py reaction-explain <reaction_smiles>`
- `run_cli.py reaction-map <reaction_smiles>`
- `run_cli.py ts-plan <reaction_smiles>`
- `run_cli.py kinetics --reactant-log <path> --ts-log <path> --product-log <path>`
- `run_cli.py yield <reaction_smiles>`
- `run_cli.py reaction-features <reaction_smiles> [--format json]`

统一输出约定：

- CLI 默认输出中文摘要。
- `--format json` 输出机器可读 JSON。
- 外部工具不可用时返回 `available=false`、`status=unavailable`、`reason`，不抛未处理异常。
- 每个预测结果必须包含 `source` 或 `method`。

## Assumptions

- 不自动安装全局程序；如需下载工具，后续按本机规则优先使用 `scoop`，并先确认。
- 重型系统 ASKCOS/RMG/YARP 暂不进入第一阶段实现，只在后续以 Docker/WSL/远端 sidecar 接入。
- Gaussian 已按当前 README 所述作为本机可检测工具处理。
- 每阶段必须测试通过并由用户确认后，才进入下一阶段实操。
