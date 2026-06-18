# AIREADME.md

This file is a handoff-oriented guide for AI coding agents working on OrgSynFlow. It summarizes the project shape, runnable commands, integration boundaries, and local conventions that matter during implementation.

## Project Intent

OrgSynFlow is a local organic synthesis workbench. The goal is not to pretend every chemistry module is a trained production model; the system should expose a clear, composable workflow for:

- molecule property analysis
- retrosynthesis route prediction
- reaction analysis
- Gaussian input generation and job orchestration
- transition-state planning
- kinetics and thermodynamics estimation
- layered yield estimation with explicit method/confidence labels

The preferred product direction is a notebook-like workspace: the user can create many workspaces, add generic chemistry cells, place molecules/reactions/routes on a canvas, select a molecule node or reaction arrow, and run context-specific tasks without copying SMILES between disconnected modules.

## Current Main Surfaces

- React/Vite workspace frontend: `web/`
- FastAPI backend: `api/main.py`, launched by `run_api.py`
- CLI: `run_cli.py`
- Legacy Streamlit debug UI: `app/main.py`
- Legacy Tkinter desktop app: `desktop_app.py`
- Shared service/core logic: `services/`, `core/`
- External tool adapters: `adapters/`
- Local workspace JSON files: `data/workspaces/`
- Desktop on/off launcher logic: `scripts/orgsynflow-toggle.ps1`

The current browser UI is at:

```text
http://127.0.0.1:5173/
```

The API is at:

```text
http://127.0.0.1:8765/
```

## One-Click Local Launcher

The user's desktop has a double-click toggle command:

```text
C:\Users\Meta\Desktop\OrgSynFlow Toggle.cmd
```

It calls:

```powershell
scripts\orgsynflow-toggle.ps1
```

Behavior:

- If OrgSynFlow is stopped, it starts `uv run python run_api.py` and `npm run dev`.
- If OrgSynFlow is running, it stops both services.
- Logs go under `%LOCALAPPDATA%\Temp\codex\orgsynflow\`.
- The launcher opens `http://127.0.0.1:5173/` unless `-NoOpen` is passed to the PowerShell script.

## Normal Development Commands

Run the backend:

```powershell
uv run python run_api.py
```

Run the React frontend:

```powershell
cd web
npm run dev
```

Run Python tests:

```powershell
uv run pytest -q
```

Build the frontend:

```powershell
cd web
npm run build
```

Useful CLI smoke tests:

```powershell
uv run python run_cli.py health
uv run python run_cli.py adapters
uv run python run_cli.py molecule "CCO"
uv run python run_cli.py properties "CCO" --include-opera
uv run python run_cli.py route "CC(=O)Oc1ccccc1C(=O)O" --max-routes 3
uv run python run_cli.py gaussian-status
uv run python run_cli.py reaction-explain "CCO>>CC=O"
uv run python run_cli.py yield "CCO>>CC=O"
```

## WSL Mirror

The project is also mirrored in WSL:

```text
/home/meta/Project/Workspaces/orgsynflow
```

The WSL chemistry environment is:

```bash
/home/meta/.local/opt/miniforge3/bin/mamba run -n orgsynflow-chem <command>
```

For WSL temporary files, use:

```text
/tmp/codex/
```

Do not assume the Windows and WSL copies are automatically synchronized. After commits on Windows, pull in WSL when needed:

```bash
cd /home/meta/Project/Workspaces/orgsynflow
git pull --ff-only
```

## Frontend Model

The React workbench should follow these UX rules from the user:

- No dark permanent sidebar.
- Workspace selection belongs in a compact dropdown near the top-left.
- The unit/cell rail should be white and hideable.
- Add-cell controls belong in the unit rail.
- Cells should be generic chemistry cells, not separate molecule/reaction/route cell types in the UI.
- Input should infer intent:
  - plain SMILES means molecule
  - reaction SMILES containing `>>` means reaction
  - multiple connected reactions can represent a route
- Canvas nodes should render molecule structures from SMILES, not show oversized titles.
- Reaction arrows should be selectable and drive reaction-specific tasks.
- Each molecule on a route should remain selectable for molecule-specific calculations.
- Predicted routes should first appear as candidates/previews; accepted routes can be inserted into a workspace.

Implementation notes:

- React Flow is used for the canvas.
- Molecule nodes currently call the backend molecule SVG render endpoint.
- Ketcher is embedded for visual molecule drawing input.
- The task panel changes behavior based on selected cell, molecule node, or reaction edge.

## Backend/API Model

FastAPI routes in `api/main.py` expose the reusable core behavior. Keep CLI, frontend, and any desktop UI aligned through shared service/core functions rather than duplicating chemistry logic in UI code.

Important API groups:

- workspace CRUD
- molecule SVG rendering
- molecule properties and descriptors
- route prediction
- reaction validation/explanation/mapping/features/yield
- Gaussian status/input/run/parse
- Gaussian job queue
- kinetics profile

External tools must fail gracefully. If OPERA, AiZynthFinder, RXNMapper, DRFP/RXNFP, xTB, CREST, GoodVibes, or cclib are unavailable, return clear `unavailable`, `disabled`, or fallback metadata instead of crashing.

## Chemistry Honesty Rules

Be explicit about method and confidence. Do not present heuristic/demo logic as a trained model.

Required style for outputs:

- molecule properties should state source, method, and applicability when possible
- route prediction should state whether it is real AiZynthFinder output, disabled, unavailable, or fallback/demo
- transition-state features should use validation levels such as unverified, scan candidate, TS optimized, freq passed, IRC passed
- yield estimates should include `method`, `confidence`, `applicability_domain`, and `note`

## Important Local Conventions

From the user's repo rules:

- On Windows, prefer `uv` for Python.
- On Windows, prefer `scoop` for downloading/installing programs, but do not install global tools without user confirmation.
- Temporary files and backups on Windows must stay under `%LOCALAPPDATA%\Temp\codex\`.
- Temporary files in WSL should stay under `/tmp/codex/`.
- If the repo changes, commit the work at the end; if connected to GitHub, push it.
- Do not revert user changes unless explicitly asked.

## Files Worth Knowing

```text
README.md                         user-facing project overview
plan.md                           three-phase integration plan
run_cli.py                        stable CLI entry point
run_api.py                        FastAPI launcher
api/main.py                       HTTP API surface
services/                         reusable service layer
core/                             chemistry, Gaussian, kinetics, yield logic
adapters/                         optional external tool adapters
web/src/App.tsx                   main React workbench
web/src/api.ts                    frontend API client
web/src/types.ts                  frontend workspace/task types
web/src/styles.css                frontend layout and visual styling
scripts/orgsynflow-toggle.ps1     local service on/off controller
```

## Pre-Final Verification Checklist

For backend/core changes:

```powershell
uv run pytest -q
```

For frontend changes:

```powershell
cd web
npm run build
```

For launcher/service changes:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\orgsynflow-toggle.ps1 -NoOpen
Invoke-RestMethod http://127.0.0.1:8765/health
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\orgsynflow-toggle.ps1 -NoOpen
```

After browser-facing frontend changes, open or test:

```text
http://127.0.0.1:5173/
```

## Known Caution Areas

- `data/workspaces/example-workspace.json` can become dirty during browser/manual testing. Do not commit test-created workspace mutations unless they are intentional fixtures.
- Vite/Ketcher builds produce large chunk warnings. These warnings are currently expected unless specifically working on bundling.
- Some README text may lag the evolving React workbench UX; prefer the current UI rules in this file when making frontend layout decisions.
- Gaussian and OPERA availability depends on local machine setup. Tests should allow graceful fallback.
- Keep the frontend experience integrated: molecule, reaction, route, properties, TS planning, and kinetics should feel like operations on selected canvas objects, not isolated pages.
