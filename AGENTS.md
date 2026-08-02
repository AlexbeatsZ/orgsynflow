# OrgSynFlow agent guidance

Write this file in English. Keep it limited to current product constraints, operational entry points, and open work; completed history belongs in Git and issues.

## Product identity

OrgSynFlow is a local-first, pluggable organic-synthesis workbench joining molecules, reactions, routes, property prediction, Gaussian calculations, transition-state planning, kinetics, and yield estimation in one workflow.

- The React/Vite Web UI at `http://127.0.0.1:5173/` is the only interactive product interface.
- FastAPI at `http://127.0.0.1:8765/` is the testable backend; `run_cli.py` remains the automation entry point.
- Do not restore Tkinter, Streamlit, desktop clients, executable packaging, or deleted desktop build scripts.
- Workspaces are notebook-like collections of general chemistry cells. Infer molecule, reaction, or route content from the input instead of forcing users to choose rigid cell types.
- Render molecule structures, not title-only/text-only placeholders. Route predictions are previews until the user explicitly inserts them.

## Scientific integrity

- Never present heuristic, fallback, or unavailable integrations as authentic model results.
- Optional tools must return explicit `available`, `unavailable`, `disabled`, or `fallback` status rather than fake success.
- Yield results include method, confidence, applicability domain, and notes. Transition-state output must state its verification level and never claim guaranteed correctness.
- Preserve route-node identity separately from molecular-component identity, especially for dot-separated inputs and repeated SMILES.

## Architecture and data constraints

- Shared behavior belongs in `services/` and `core/`; external programs belong behind `adapters/`. Keep CLI, API, and Web behavior consistent through those layers.
- Computation tasks use stable records in the workspace instead of rewriting the entire workspace for every status update.
- Do not commit browser/test mutations to `data/workspaces/example-workspace.json` unless the fixture is intentionally changing.
- Windows and WSL checkouts do not synchronize automatically. Push Windows changes, then use `git pull --ff-only` in `/home/meta/Project/Workspaces/orgsynflow` when the WSL mirror must run them.
- Keep WSL toolchains isolated in `/home/meta/.local/opt/miniforge3/envs/orgsynflow-chem`; do not mix legacy chemistry stacks into the main Windows environment.
- WSL temporary computation data belongs under `/tmp/codex/orgsynflow/`; Windows logs and backups belong under `%LOCALAPPDATA%\Temp\.agents\orgsynflow\`.

## Important implementation boundaries

- React Flow connections are chemistry relationships only when backed by reaction data; user-drawn edges remain independently selectable/deletable and self-loops are forbidden.
- Duplicate SMILES may represent different physical nodes. Do not deduplicate canvas objects by SMILES alone.
- Long-running Gaussian/CREST jobs must expose live progress, cancellation, and recovery without blocking the UI event loop or killing unrelated computations.
- Use the bounded fast orthogonal router while dragging and on large canvases; detailed obstacle routing is for small stationary canvases. Selection changes must not recompute paths.
- Frontend task results open structured modals; raw stdout, stderr, and JSON stay behind expandable raw-data sections.

## Commands and verification

```powershell
uv run python run_api.py
uv run pytest -q
cd web
npm run dev
npm run build
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\orgsynflow-toggle.ps1 -NoOpen
```

- After frontend changes, verify the real browser workflow; a production build alone is insufficient.
- The desktop shortcut `C:\Users\Meta\Desktop\OrgSynFlow Toggle.cmd` must continue to target the current repository and `scripts\orgsynflow-toggle.ps1`.
- Restart the API after adapter changes so Uvicorn does not keep stale modules loaded.
