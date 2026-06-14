# OrgSyn Flow 有机合成工作台

面向有机合成路线预测与计算解析的本地辅助平台。当前已推进到 V6，主交付形态是中文桌面程序，同时保留 HTTP API 方便自动化测试全部功能。

## 已完成版本

- V0：目标分子 SMILES 输入、内置 demo 路线、路线树、基础性质表、Markdown 报告。
- V1：AiZynthFinder CLI 适配器，失败时自动回退到 demo 路线。
- V2：中文界面与反应中心/反应类型解释。
- V3：Gaussian 输入文件生成与 Gaussian log/out 关键字段解析。
- V4：过渡态合理性、ΔG_rxn、ΔG‡ 与 Eyring 速率估计。
- V5：演示级相对产率倾向与路线可行性评分。
- V6：Tkinter 中文桌面程序、FastAPI 测试接口、PyInstaller EXE 打包。

## 桌面程序

已构建的 EXE：

```text
dist_v6/OrgSynFlowV6/OrgSynFlowV6.exe
```

重新打包：

```powershell
uv sync
uv run pyinstaller --noconfirm --clean --name OrgSynFlowV6 --windowed --distpath dist_v6 --workpath build_v6 --add-data "data;data" --add-data "reports;reports" desktop_app.py
```

或运行：

```powershell
.\build_exe.ps1
```

## API 测试接口

启动 API：

```powershell
uv run python run_api.py
```

默认地址：

```text
http://127.0.0.1:8765
```

接口：

- `GET /health`
- `POST /analyze`
- `POST /molecule/properties`
- `POST /molecule/descriptors`
- `POST /reaction/explain`
- `POST /reaction/map`
- `POST /reaction/ts-plan`
- `POST /reaction/yield`
- `POST /reaction/features`
- `POST /gaussian/input`
- `GET /gaussian/status`
- `POST /gaussian/run`
- `POST /gaussian/parse`
- `POST /kinetics/profile`

说明：

- `POST /gaussian/input` 会使用 RDKit 从 SMILES 生成 3D 坐标，再生成真正可供 Gaussian 使用的输入文本。
- `POST /gaussian/run` 会调用本机 `g16/g09`。当前机器已检测到 `C:\Users\Meta\AppData\Local\Programs\g16w\g16.exe`。
- Gaussian 作业临时文件集中写入 `%LOCALAPPDATA%\Temp\codex\orgsynflow\gaussian_jobs\`。
- 反应解释、规则估计总收率和路线可行性评分是规则演示层，不是 RXNMapper/DRFP/HTE 真实模型结果。

示例：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

## CLI

统一命令行入口：

```powershell
uv run python run_cli.py health
uv run python run_cli.py adapters
uv run python run_cli.py molecule "CCO"
uv run python run_cli.py properties "CCO" --include-opera
uv run python run_cli.py descriptors "CCO" --format json
uv run python run_cli.py route "CC(=O)Oc1ccccc1C(=O)O" --max-routes 3
uv run python run_cli.py gaussian-status
uv run python run_cli.py gaussian-input "CCO" --job-type "opt freq"
uv run python run_cli.py reaction-explain "CCO>>CC=O"
uv run python run_cli.py reaction-map "CCO>>CC=O"
uv run python run_cli.py ts-plan "CCO>>CC=O"
uv run python run_cli.py yield "CCO>>CC=O"
uv run python run_cli.py reaction-features "CCO>>CC=O" --format json
```

说明：

- `--format json` 使用 ASCII-safe JSON，便于 Windows 子进程测试和自动化解析。
- OPERA、Mordred、RXNMapper、DRFP/RXNFP、xTB、CREST、GoodVibes、cclib 都按可选适配器处理；未安装时返回 unavailable/fallback，不影响主流程。
- TS 相关命令只生成半自动搜索计划，不宣称已经获得或验证过渡态。

## 测试

```powershell
uv run pytest -q
```

当前测试覆盖：

- demo 路线和路线评分
- 报告生成
- AiZynthFinder 回退
- 反应解释
- Gaussian 输入/解析
- 动力学能垒与速率
- 产率/可行性评分
- 服务层和 HTTP API

## 目录

```text
api/                 FastAPI 自动化测试接口
app/                 Streamlit 调试入口，非主交付
adapters/            外部工具适配器
core/                分子、路线、Gaussian、动力学、产率等核心逻辑
data/demo_routes/    V0/V1 演示路线
reports/templates/   Markdown 报告模板
services/            桌面程序和 API 共用服务层
desktop_app.py       中文桌面程序入口
run_api.py           API 启动入口
build_exe.ps1        EXE 打包脚本
```
