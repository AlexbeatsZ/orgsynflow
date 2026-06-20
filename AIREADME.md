# AIREADME.md

> [!IMPORTANT]
> **CRITICAL INSTRUCTION**: This file serves as the project log and AI agent hand-off manual. All future updates, logs, and comments in this file **MUST** be written in English. Do not write in Chinese or any other language.

---

This file is the project log and AI hand-off manual for OrgSynFlow. For projects with an independent folder, this file should be read at the beginning of each new conversation; if it does not exist, it should be created. After each task is completed, new lessons learned, the current status, and unresolved items should be written back to this file.

## 1. Project Goal

The overall goal of OrgSynFlow is to build a local-first, pluggable organic synthesis workbench, integrating molecules, reactions, routes, property predictions, Gaussian calculations, transition state planning, kinetics, and yield estimations into a continuous workflow.

Current Product Direction:

- React/Vite frontend serves as the primary and only interactive interface, located at `http://127.0.0.1:5173/`.
- FastAPI backend provides testable endpoints, located at `http://127.0.0.1:8765/`.
- CLI `run_cli.py` is retained as a stable automation entry point.
- All desktop clients (e.g., Tkinter `desktop_app.py`, Streamlit) and their build/packaging scripts (e.g., `build_exe.ps1`) have been permanently deprecated and deleted.
- Workspaces should be notebook/Jupyter-like: users can create multiple workspaces, and each workspace contains multiple general chemistry cells.
- The UI should not strictly categorize cells into "Molecule/Reaction/Route" types; a general cell should be able to identify ordinary SMILES, reaction SMILES, and multi-step routes based on the input content.
- Molecules in the canvas must be rendered as structure diagrams, not just titles or large text.
- Users should be able to select any molecule node to perform molecular properties, descriptors, Gaussian inputs, and other tasks; they should also be able to select reaction arrows to perform reaction analysis, mapping, yields, TS planning, and other tasks.
- Route prediction results should first be presented as candidates/previews, and only inserted into the current workspace canvas after user confirmation.

Core Capabilities:

- Molecular Property Analysis: RDKit basic properties, optional OPERA predictions, optional Mordred/descriptor extensions.
- Synthetic Route Prediction: Parse real results when AiZynthFinder is available; return clear "unavailable/disabled" when unavailable, and do not fake real predictions.
- Reaction Analysis: Basic feasibility check, reaction explanation, optional RXNMapper mapping, and reaction feature export.
- Quantum Chemistry Calculation: Gaussian input generation, Gaussian job queue, and log/out parsing.
- Transition State: Semi-automatic TS planning, without claiming to automatically guarantee correctness; output verification levels.
- Kinetics/Thermodynamics: Calculate `ΔG_rxn`, `ΔG‡`, and Eyring rates based on Gibbs free energy.
- Yield Estimation: Clearly distinguish between heuristic, feature export, and trained models; each result must contain method/confidence/applicability/note.

Main Code Entry Points:

```text
README.md                         User-facing project documentation
plan.md                           Three-phase integration plan
run_cli.py                        CLI entry point
run_api.py                        FastAPI startup entry point
api/main.py                       HTTP API
services/                         Common service layer shared by CLI/API/UI
core/                             Core logic for molecules, routes, Gaussian, kinetics, and yield
adapters/                         Adapters for external tools
web/src/App.tsx                   Main React workspace interface
web/src/api.ts                    Frontend API client
web/src/types.ts                  Frontend type definitions
web/src/styles.css                Frontend styles
scripts/orgsynflow-toggle.ps1     Local service toggle script
data/workspaces/                  Local workspace JSON
```

Common Commands:

```powershell
# Backend
uv run python run_api.py

# Frontend
cd web
npm run dev

# Python tests
uv run pytest -q

# Frontend build
cd web
npm run build

# Toggle script test
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\orgsynflow-toggle.ps1 -NoOpen
```

Desktop One-Click Toggle:

```text
C:\Users\Meta\Desktop\OrgSynFlow Toggle.cmd
```

It calls:

```powershell
scripts\orgsynflow-toggle.ps1
```

Log Location:

```text
%LOCALAPPDATA%\Temp\codex\orgsynflow\
```

WSL Mirror Path:

```text
/home/meta/Project/Workspaces/orgsynflow
```

WSL Environment:

```bash
/home/meta/.local/opt/miniforge3/bin/mamba run -n orgsynflow-chem <command>
```

WSL Temporary Files must be placed in:

```text
/tmp/codex/
```

## 2. Lessons Learned

Project Log Rules:

- At the beginning of each new conversation, read `AIREADME.md` in the project root directory first.
- If `AIREADME.md` does not exist, create it.
- After each task is completed, update this file, recording at least new lessons learned, fixed bugs, and the current task status.
- `AIREADME.md` is not a standard README, but a project memory meant for hand-off between AI agents/development proxies.

Local Workspace Conventions:

- Prefer `uv` when running Python on Windows.
- Prefer `scoop` when downloading/installing programs on Windows, but do not install global tools without user confirmation.
- Centralize Windows temporary files, backups, and logs under `%LOCALAPPDATA%\Temp\codex\`.
- Centralize WSL temporary files under `/tmp/codex/`.
- If modifying a Git repository, commit changes upon completion; if connected to GitHub, push changes as well.
- Do not roll back user changes; if testing or browser operations dirty data files, revert only the test artifacts caused by yourself.

Architecture & Project Simplification Lessons:

- The user explicitly requested to only use the Web interface (React/Vite), and no longer needs any desktop client or local executable packaging artifacts. When adding interactive or UI features in the future, develop only for the frontend project in the `web/` directory and the corresponding FastAPI backend. Do not reintroduce or modify any desktop GUI (such as Tkinter/PyQt) or `.exe` packaging logic.

Frontend UX Lessons:

- The TS 3D Conformation Editor must not repeatedly inject CDN scripts at runtime; it should be asynchronously loaded using the in-project `3dmol` dependency. The right column is a collapsible flex container, and the viewer must set `flex: 0 0 350px` and `min-height`, otherwise the declared 350px will be compressed to about 24px, appearing blank/unavailable. Each XYZ sub-model passed to 3Dmol must include the number of atoms in the first line and a comment in the second line; passing only coordinate lines will cause the model to parse as empty while manual labels still show, resulting in the "only a bunch of numbers" symptom. Candidate XYZs must be split into groups by molecule before applying each molecule's transformation, and cannot return the original XYZ directly after selecting a candidate, otherwise the preview and GJF will not respond to translation/rotation.
- 3D molecular dragging must not write screen dx/dy directly into world X/Y; camera rotation makes the direction incorrect. Shift translation should use 3Dmol's `screenOffsetToModel(dx, dy)`, which sets the depth component to zero on the projection plane first, and then transforms back to model coordinates via the camera quaternion, ensuring movement is restricted to the plane perpendicular to the line of sight. Ctrl rotation should use screen-up/screen-right in the camera plane as the rotation axes, and then convert the combined quaternion back to XYZ Euler angles for GJF use.
- Deleting SMILES blocks cannot rely solely on the temporary node state of React Flow; during deletion, adjacent edges must also be removed, and `cell.objects.molecules/reactions` must be rebuilt using the remaining nodes/edges. Otherwise, parent cell updates or page refreshes will regenerate the nodes. Currently, when a block is selected, a "Delete SMILES Block" button is shown, and the deletion result is persisted upon saving the workspace.
- The user explicitly does not want a dark permanent sidebar. Workspace selection should be a compact dropdown menu at the top.
- The cell sidebar should be white and hidable, with the add-cell button placed inside it.
- The UI should not strictly classify cells into "Molecule Cell/Reaction Cell/Route Cell". The user expects a general chemistry cell that automatically infers its content type based on the input.
- Input rules: An ordinary SMILES is a molecule; containing `>>` is a reaction; multiple connected reactions represent a route.
- Canvas nodes must display the molecular structure diagram rendered from the SMILES, not a large title.
- There was once an issue where the canvas displayed a giant "Ethanol" because React Flow's default label node rendered the molecular label/title as content. It has been changed to a custom molecule node and renders the structure diagram via the backend's RDKit SVG endpoint.
- There was once an issue where `CCO` appeared duplicated because the node data combined both the label and smiles. It has been changed to only display a single line of SMILES at the bottom of the node.
- The cell delete button was once nested inside the `<button>` of the entire cell card, causing invalid DOM and browser warnings. It has been changed to use a clickable `div` for the cell card and an independent delete button.
- Dot-separated mixtures like `CO2.H2O` are not standard single RDKit SMILES, but common small molecular formulas like `CO2` and `H2O` within them can be safely mapped to structures. The structure rendering endpoint should try RDKit first; on failure, split by dot, and draw a multi-structure SVG for components that can be reliably mapped; inputs like `CuSO4.5H2O` whose structures cannot be reliably inferred are downgraded to formula SVGs. The frontend should treat `svg: null` as a failure state to prevent the node from showing "Rendering..." indefinitely.
- The results/logs panel should not occupy the full width at the bottom of the main layout; it should be embedded within the middle workspace panel and use a light background with dark text, consistent with the workspace panel.
- Hand-drawn edges in React Flow must not be mistaken for reactions; only edges generated from reaction objects should trigger reaction tasks. Hand-drawn canvas edges should be selectable and deletable, and self-connections (invisible/meaningless edges) are forbidden.
- The chemistry canvas should allow multiple independent nodes for the exact same SMILES/structure, and must not de-duplicate by `smiles`; duplicate reagents, equivalent substrates, or the same molecule at different positions all require independent objects.
- Having too few connection handles on molecular nodes limits route/network representation. Currently, each molecular node must provide 8 connection handles: top-a/top-b/right-a/right-b/bottom-a/bottom-b/left-a/left-b.
- Do not display the React Flow connection handles directly as blue dots, which clutter the canvas and make users feel they must manually drag anchors. Handles should be hidden internally; the user enters a continuous drawing mode via a "Connect Molecules" button or temporarily by holding Shift; each clicked molecule automatically draws a connection from the previous one, setting the current one as the start of the next segment. Connection lines should use thicker, darker smoothstep arrows, with blue highlighting for the selected state. The canvas must provide a "Delete All Connections" function.
- Users prefer geometric intuition for connections between molecular blocks: when B is above A, it should connect from A's top-center to B's bottom-center in a straight line; left-right relations should also use left-right center anchors. React Flow edges should use the `straight` type. Legacy handles like `top-a/right-a/...` must be normalized to central `top/right/bottom/left` to prevent old data from drawing redundant bends.
- Synthetic routes/reaction relationship lines must display clear arrows. React Flow edges currently use `MarkerType.ArrowClosed`; legacy edges should recalculate the nearest top/bottom or left/right handle based on node centers during loading, rather than preserving historically incorrect endpoints. Edge labels are hidden by default and only shown when selected, preventing text from overlapping lines and molecular blocks.
- Since 2026-06-20, canvas edges no longer use React Flow's `straight` path but instead use a custom `orthogonal` edge: starting and ending points must fall exactly on the center of the top/bottom/left/right sides of the SMILES blocks; paths are restricted to horizontal/vertical polyline segments; routing treats other SMILES blocks as obstacle bounding boxes to avoid overlapping; side endpoints are automatically selected based on the priority: "shortest overall path → fewest bends → longest segment before first bend → longest subsequent segments in order."
- The TS configuration window must not continuously overwrite frontend parameters or coordinates during `awaiting_confirmation` polling; otherwise, the GJF preview, coordinates, and resource parameters being edited by the user will be reset by the backend's initial values every 2 seconds. It should be initialized once per workflow id/status, after which the user's edits drive the preview.
- The candidate field submitted by the TS frontend is `candidate_id`, but the backend historically only read `selected_candidate_id`, causing the user-selected initial conformation to be ignored and fallback to the first candidate. Backend confirmation must support both fields.
- The backend computation status should not permanently occupy the right task panel. A compact "Backend" button at the top-right triggers a popup instead; Gaussian queues and route candidates belong to secondary window entry points of the current molecule/reaction and should not stand permanently alongside molecular tasks.
- Task results should be displayed via independent modals; the center workspace panel no longer permanently hosts a "Results/Logs" section, and the right task panel only handles operations for the currently selected object. Clicking route prediction should directly open the candidate modal, offering options to view, add to the current canvas, or create a new route cell.
- Computation task buttons must bind to stable task records in the current cell's `results` using the key format `"object_type:object_id:task_id"`. Blue indicates uncomputed, yellow indicates running, green indicates success, and red indicates failure; green opens results, red displays errors before allowing retry. Task records are updated atomically via a dedicated API, and the entire workspace should not be saved back just to store one task result.
- Result details use a modal, but task log entries must not disappear with it. The current cell's task log should reside in a collapsible drawer at the bottom of the middle panel, retaining its title and count when collapsed, and displaying results/errors sorted by update time when expanded.
- Gaussian geometry optimization/frequency must have only one primary button. Clicking it opens the configuration window and generates a default `Opt + Freq / B3LYP / 6-31G(d) / 0 / 1` input; parameters and the GJF are editable, and the window only provides regenerate, close, and submit options—no longer split into "Direct Submit" and "Advanced Config".
- The left-side cell cards should only display the type, title, and delete option; the molecule/reaction count and equation previews clutter space and offer low information value, so they should not be restored.
- Multiple precursors of the same step in route candidates must be grouped into a single reactant block with SMILES connected by dots, e.g., `O=C(O)c1ccccc1O.CC(=O)OC(C)=O` as a single node connecting to the product, rather than splitting into parallel edges. For manual user inputs of multiple independent molecules, they can still be created as multiple nodes via multiple lines.
- When triggering retrosynthesis prediction from an existing SMILES block, inserting the candidate route must bind the prediction target back to this existing block; do not create a duplicate `C` block with the same product. For single-step results like `A+B>>C`, the canvas should create an `A.B` dot-separated reactant block pointing to the existing `C` block via a single arrow, distinguishing "multiple reactants of a single reaction" from "two independent routes".
- If a user triggers retrosynthesis prediction from an inner component of a dot-separated multi-molecule block, the reaction arrow still belongs to the outer container node upon insertion, but the SVG path endpoint must pierce the outer container and land on the edge of the inner component's card; other component cards in the same container should be bypassed as obstacles to avoid arrows crossing adjacent molecules.
- Multiple molecule IDs in the route candidate tree may share the same target SMILES. For retrosynthesis insertion initiated from an inner component, all route molecules with the same SMILES as the target component must map back to the original inner target, rather than duplicating the "synthesis target" outside; self-loop reaction edges generated after mapping should be skipped.
- After making frontend changes, try to check the actual UI using a browser/Playwright instead of just checking `npm run build`.
- The permanent "View Job Queue (Gaussian)" and "View Route Candidates" buttons have been removed from the task panel. The job queue status and results are unified inside the bottom task log drawer; upon successful route prediction, clicking the green prediction task button or the corresponding success log entry directly opens the route candidate popup with interactive actions ("Add to Current Canvas" / "Create Route Cell"), rather than a static non-interactive display.
- The green "Completed" task button should not only view stale results; when clicking a completed task from the task panel to open the results/route candidate window, a "Recompute" entry must be kept at the bottom of the window, reusing the task's original run/retry logic. Tasks requiring parameters like Gaussian should also retain the "Modify Configuration" option.
- The `ketcher-react/dist/index.css` imported by Ketcher contains global styles that conflict with the project's modal styles (like `.modal-backdrop`, `.modal-header`), causing off-center modals and displaced Wasm interactions. All basic modal class names have been prefixed (e.g., `.osf-modal-backdrop`). Avoid CSS Grid for modal containers embedding complex third-party components, as Grid forces dynamically generated auxiliary elements into grid items, ruining layouts. Flexbox must be used, applying `flex: 1` and `position: relative` to ensure child container height fills the containing block properly.
- The Ketcher editor must not render inside containers with broad descendant selectors like `.editor-strip`; `.editor-strip div/button/textarea` recursively pollutes hundreds of divs/buttons inside Ketcher, disabling toolbars and canvases. It should render via React Portal attached to `document.body`, and `.editor-strip` styles must be narrowed to direct child selectors.
- Ketcher 3.15 under Vite dev requires pre-bundling `ketcher-react`, `ketcher-core`, `lodash`, and `@babel/runtime/regenerator` to avoid "does not provide an export named default" errors. However, do not pre-bundle `ketcher-standalone/dist/binaryWasm`, as Vite's optimizer would break the Indigo worker path, leading to `getSmiles()` hanging or missing worker files.
- The TS parameter window once used an undefined `osf-modal-window` class, making the background fully transparent, and lacking shadows, clipping, or relative positioning. The TS window must reuse the `.osf-config-modal` base class, with `.ts-config-modal` overriding size and grid layouts; do not create modal classes without a base styling contract.
- Route prediction results should not be plain text; they are rendered as a synthetic tree preview inside the popup using `RouteCandidatePreview` with `MoleculeDrawing` and SVG paths, offering an intuitive experience.
- The route candidate preview must focus on reaction steps: multiple reactants render as structures separated by `+`, leading to the product via a clear arrow. As route candidate details can be long, they must use a result popup with `max-height` and internal scrolling rather than reusing unrestricted config popups.
- The Chemformer checkpoint depends on Python 3.10, PyTorch, and `aizynthmodels`, so it should not be mixed into the main project's Python 3.11 `uv` environment. It is exposed via a separate Conda sidecar HTTP API, and OrgSynFlow only performs health checks and unified route format conversions.
- Chemformer beam search may contain invalid SMILES, normalized duplicates, or cyclic candidates containing the target itself in the precursors. The adapter should request more raw beams than displayed, then filter the top 5 valid, de-duplicated, target-free candidates; `log_likelihood` should only be shown as the raw model score, not as a probability.
- Chemformer normalizes target SMILES. The route inserter must not rely solely on SMILES string equality to reuse existing target nodes; it should prioritize mapping `route.target_id` to the anchor node where the user initiated the prediction.
- `/compute/status` must not run full adapter scans for every backend on every call; WSL detection is slow, so it should compile status maps once and reuse them. Otherwise, the frontend engine selector will show an undetected state for a long time.
- The Gaussian optimization convergence chart can be extracted by parsing all `SCF Done:` and `Maximum Force` entries in the log file, rendering iteration details in `GaussianJobView` (similar to the implementation in `temp/main.py`).
- The "output preview" for Gaussian/TS tasks should not wait for computation completion. The status endpoints of the queue and TS workflow should read the latest `.log/.out` file in the current working directory, returning `log_tail` and structured `log_progress` (SCF cycles, optimization convergence tables, warnings/errors), which the frontend polls for real-time progress.
- The standard Gaussian queue must support termination during execution. The queue maintains a `threading.Event` for each job; `run_gaussian_job` terminates processes using `cancel_event`. The frontend displays a "Force Terminate Gaussian Process" button only for tasks with a `job_id` that are still running.
- The GJF preview in the standard Gaussian parameter window should regenerate in real-time as the task type, method, basis set, charge, or multiplicity changes. However, if the user manually edits the textarea, automatic overrides must pause, show "Manually Edited", and offer "Restore Auto Preview" to sync parameters again.
- TS initial conformation generation must not accept obvious fragment overlaps. After RDKit embeds dot-separated multi-molecule reactants, it must check the minimum heavy-atom distance between non-bonded fragments; if it falls below the threshold, extrapolate along the centroids of the fragments to prevent atomic interpenetration.
- The FastAPI backend must explicitly map all managers; if a new manager (such as `TsWorkflowManager`) is added, corresponding `GET / POST` routes must be added in `api/main.py` to prevent frontend 404 errors.

Chemical Result Presentation Lessons:

- Do not package heuristic/demo logic as authentic model results.
- AiZynthFinder, OPERA, RXNMapper, DRFP/RXNFP, xTB, CREST, GoodVibes, and cclib are optional tools; when unavailable, they must return a clear "unavailable/disabled/fallback" instead of throwing unhandled exceptions.
- The public weight audit conclusions are recorded in [docs/public-model-weights-audit.md](file:///C:/Users/Meta/Project/Workspaces/orgsynflow/docs/public-model-weights-audit.md): AiZynthFinder, OPERA, and RXNMapper are public models/weights directly relied upon; ASKCOS has public models and data but is heavy to deploy and licensed CC BY-NC-SA; DRFP requires no weights; RXNFP has a public pre-trained reaction BERT but is not a general yield predictor; no officially supported general organic reaction yield weights were found to integrate responsibly, so the yield module continues to show heuristic/features/no trained model.
- The official installation guide for `rxn4chemistry/rxn_yields` is still based on Python 3.6 and RDKit 2020.03.3, and the official README explicitly notes that the USPTO yield distribution varies by mass scale, limiting model applicability. It cannot be installed directly into the current `orgsynflow-chem` environment or wrapped as a general yield model; if evaluated later, use an isolated environment and present reaction families, datasets, and applicability domains in the UI.
- Computation backend survey: xTB's official repository is `grimme-lab/xtb`; CREST's official repository/documentation are `crest-lab/crest` and `crest-lab.github.io/crest-docs`; cclib can parse various quantum chemistry outputs; GoodVibes calculates quasi-harmonic thermochemical corrections from Gaussian/ORCA/NWChem/Q-Chem/xTB/ASE results; PySCF, Psi4, geomeTRIC, and ASE are open-source quantum chemistry/optimization/workflow backend candidates.
- Gaussian is commercial proprietary software and cannot be installed from GitHub or public sources; WSL integration requires the user to provide a valid Gaussian installer, license, and environment variable info.
- Local Windows has Gaussian 16W installed: `C:\Users\Meta\AppData\Local\Programs\g16w\g16.exe`. WSL can invoke this Windows executable via `/mnt/c/Users/Meta/AppData/Local/Programs/g16w/g16.exe`; `core.gaussian_runner.find_gaussian_executable()` has been hardened to check PATH, then check `GAUSS_EXEDIR`, and finally scan common paths of Windows Gaussian mounted in WSL.
- WSL `orgsynflow-chem` computation toolchain is currently available: xTB 6.7.1, CREST 3.0.2, Open Babel 3.1.0, ASE 3.28.0, geomeTRIC 1.1.1, PySCF 2.13.1, Psi4 1.10.1, cclib, GoodVibes, RDKit.
- If the Windows backend service cannot directly locate xTB/CREST/Open Babel/Psi4/geomeTRIC, it can bridge to the fixed WSL `orgsynflow-chem` path: `wsl:/home/meta/.local/opt/miniforge3/envs/orgsynflow-chem/bin/<tool>`. `adapters/xtb_adapter.py` supports writing XYZ to WSL `/tmp/codex/orgsynflow/...` via stdin and running the CLI, avoiding Windows/WSL path translation and encoding issues.
- Computational backend status is unified and exposed via `/compute/status`, including `available/executable/source` for Gaussian, xTB, CREST, Open Babel, GoodVibes, PySCF, Psi4, geomeTRIC, and ASE. The frontend's right-side task panel displays these statuses.
- OPERA 2.9 is installed in WSL under `/home/meta/.local/opt/OPERA2.9` and can be run via `/home/meta/.local/bin/opera`. The Windows backend must bridge via `wsl:/home/meta/.local/bin/opera`; otherwise, "RDKit + OPERA" degrades to unavailable.
- The AiZynthFinder CLI is installed in WSL `orgsynflow-chem`: `/home/meta/.local/opt/miniforge3/envs/orgsynflow-chem/bin/aizynthcli`. However, the CLI requires real `--config`/policy/stock/model files; if unconfigured, route predictions must return a clear demo fallback candidate, and not display an empty success state or fake real predictions.
- The molecular task panel has xTB and CREST buttons. The current implementation uses RDKit to generate a 3D XYZ from SMILES, then calls `/compute/xtb` or `/compute/crest`; results and stdout/stderr return to the middle results panel.
- The default Gaussian opt/freq action should generate a GJF and submit it to the queue directly; only open the "Gaussian Advanced Config" popup when method/basis/charge/multiplicity modifications are needed. Do not make users click "Generate GJF" and then "Submit Job" as the primary path.
- Route prediction results must serve as a viewable candidate set, rather than just showing a status. The candidate set should support viewing details from the right-side cards, inserting them into the current canvas (connected to the clicked molecule), or creating a new route cell for the entire route.
- When calling WSL CLI from Windows, explicitly set `encoding="utf-8", errors="replace"`; otherwise, UTF-8 characters in CREST/xTB outputs may disrupt the GBK decoding thread, causing `stdout` to be `None` or tests to crash.
- When long-running CREST / WSL tasks are forcibly interrupted, hanging `wsl.exe` clients may be left behind, causing all WSL-dependent features (AiZynthFinder, OPERA, RXNMapper, DRFP, xTB, CREST, etc.) to show as "missing/unavailable". Recovery order: stop the OrgSynFlow API/Web, precisely clean up residual `wsl.exe` instances spawned by the API with command lines containing `/tmp/codex/orgsynflow` or `orgsynflow-chem` in command line, then verify basic WSL via `wsl -e true`; upgrade to restarting `WslService`/WSL only if failure persists after cleanup.
- TS-related features must only claim to be "planned/candidate/unverified/verification level", never claiming to automatically find the correct transition state.
- Dot-separated multi-molecule canvas blocks must distinguish between "route node identity" and "molecular computation identity": the route still treats `A.B` as a single node, but molecular-level tasks must bind to the specific component clicked by the user inside the node; result keys use `node-id:component:index`, and identical SMILES must not be merged.
- General TS scans must not hardcode all bond-forming/breaking equilibrium distances to 1.5 Å. They should be estimated using elemental covalent radii (e.g., C–Br is ~1.96 Å), and the scanning atoms must be physically moved to the target distance before submitting each constrained optimization point, otherwise Gaussian may fail during the NewRed/RedCar internal coordinate conversion phase.
- The launcher `g16.exe` of Windows Gaussian 16W may exit leaving independent `l*.exe` Link processes. When canceling a TS workflow, in addition to terminating the launcher, precisely terminate the corresponding Link processes containing the workflow directory in their command lines, rather than ending all Gaussian computations globally.
- Yield outputs must include `method`, `confidence`, `applicability_domain`, and `note`.
- The results popup should not display long stretches of raw stdout/stderr/JSON by default. The frontend should prioritize structured summaries, key values, warnings, and paths; raw logs belong in expandable "Raw Logs / Raw Data" sections. Results containing XYZ/GJF coordinates must render interactive 3D molecular views first.
- Dependency isolation and environment unification: Gradio, py3Dmol, and matplotlib must be declared and installed in both Windows (uv) and WSL (mamba). In the TS library, use `core.gaussian_runner.find_gaussian_executable()` instead of hardcoded `g16.exe` paths to ensure the calculation service automatically discovers and invokes Gaussian executables across Windows and WSL, writing intermediate results to the unified project directory.
- EAS TS App Debugging Lessons: If `app/eas_ts_app.py` is run directly via `python app/eas_ts_app.py`, the `app/` directory becomes the working directory, and `from core.eas_ts_lib import *` throws a `ModuleNotFoundError` because `core` is not in `sys.path`. The fix is adding `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` at the top of the file, which also applies to `core/eas_ts_lib.py` referencing `core.gaussian_runner`.
- Running Windows Gaussian under WSL: Calling `g16.exe` with Linux paths directly in WSL bash throws `Thread and Process ID are zero in wsystem: No such file or directory`, and passing UNC paths throws `PGFIO/stdio: No such file or directory`. Correct approach: ① Map `OUT_DIR` under `/mnt/c/...` instead of `/home/...`; ② Launch via `cmd.exe /c 'g16.exe input.gjf'` instead of direct `subprocess.Popen(['g16.exe', ...])`.
- Gradio UI Lockups: If a Gradio callback contains a synchronous `process.wait()`, the entire Gradio event loop freezes, making the UI unresponsive. It must be refactored into a generator function, polling with `time.sleep(2)` + `process.poll()`, yielding progress to Gradio on each loop, which enables both UI updates and cancellation requests.
- Conda/Miniforge Path: The conda/mamba installation on this local WSL is at `~/.local/opt/miniforge3` rather than `~/miniconda3` or `~/anaconda3`. Correct initialization command: `source ~/.local/opt/miniforge3/etc/profile.d/conda.sh && conda activate orgsynflow-chem`.
- WSL Gradio Browser Error: When running in WSL without a desktop environment, Gradio's `inbrowser=True` triggers `gio: http://localhost:7861/: Operation not supported`. This is harmless and does not indicate startup failure; set `server_name="0.0.0.0"` in WSL and access WSL ports from a Windows browser.

Service & Startup Lessons:

- The desktop toggle script `scripts/orgsynflow-toggle.ps1` determines status using ports 8765 and 5173.
- Background processes `uv run python run_api.py` and `npm run dev` are launched on startup.
- Double-clicking the same desktop `.cmd` script again shuts down the services.
- PowerShell scripts must remain compatible with Windows PowerShell 5.1; avoid PowerShell 7 exclusive syntax like `??`.
- Do not use `timeout /t` in `.cmd` files as it fails in non-interactive environments; use `powershell Start-Sleep` instead.
- Every time changes are made to Python adapter code (e.g., `adapters/aizynth_adapter.py`), the API backend (Uvicorn process) must be restarted via `scripts/orgsynflow-toggle.ps1`. Otherwise, the process keeps loading old memory modules and ignores new path resolution logic, causing the API backend to report unconfigured policy/stock/config and fall back to built-in demo routes even after successful WSL setup.

Data & Testing Lessons:

- `data/workspaces/example-workspace.json` is easily dirtied during browser tests, workspace saves, or automated clicks. Do not include test-created cells, route candidates, or modified `updated_at` fields in commits unless explicitly intending to update the fixture.
- Vite/Ketcher builds will emit large chunk warnings; this is expected and does not mean build failure.
- For browser automation selecting by button text, note that "Add" and "Add to Canvas" can trigger fuzzy match conflicts; use exact matching.
- Windows and WSL project directories do not sync automatically. After pushing Windows commits, run `git pull --ff-only` in `/home/meta/Project/Workspaces/orgsynflow` on WSL to sync.
- If the default workspace file `data/workspaces/example-workspace.json` contains cached warnings/fallback states (e.g., status/used_fallback records in `molecule:mol-ethanol:retrosynthesis`), the page will immediately display warning banners like "AiZynthFinder detected but not configured..." on initial load. Such task result caches must be manually cleaned to restore the initial "uncomputed" state, allowing users to run real retrosynthesis calculations.
- The `children` in AiZynthFinder's JSON tree alternate between molecule and reaction nodes; the `smiles` of a reaction node is a retrosynthesis reaction SMILES and must never be inserted into the route as an ordinary molecule. Skip reaction nodes during parsing, read their molecule children as precursors, and generate forward `precursor>>product` equations.
- When predicting routes for a single component inside a multi-molecule container node, the inserter must preserve the selected `MoleculeComponent`: reuse its outer canvas node as the route target, rather than creating duplicate targets or `target -> anchor` fake reaction edges.
- Each `precursor_id` in the route must generate an independent molecular node and an independent `precursor -> product` edge, rather than merging all precursors of the same step into a dot-separated pseudo-molecule; the layout width of multi-component nodes is estimated by actual card width, otherwise adjacent nodes overlap and cause forward arrows to visually double back.
- WSL's `/tmp` may be cleared upon reboot. AiZynthFinder must execute `mkdir -p /tmp/codex/orgsynflow` before each run, without relying on legacy persistence.
- React Flow selection sync: When using React Flow's built-in `onNodesChange` / `onEdgesChange` interactions (like Shift+Click toggle, box selection, etc.), the locally tracked `selectedNodeId` and `selectedEdgeId` must be synced or cleared via `useEffect`. Otherwise, the "Delete Selected" button may show incorrectly when nothing is selected, and clicking it could delete untargeted nodes or crash due to deleting non-existent nodes.
- When updating the workspace via `onUpdate` to add new components (like adding SMILES via the input box), do not pass an empty `canvas: { nodes: [], edges: [] }` state, otherwise React Flow will reset all previously dragged nodes to default grid positions, causing the layout to fall apart.
- Orthogonal path search algorithm must avoid using O(N log N) `Array.sort` inside the while-loop for A*/Dijkstra-style priority queues. `runOrthogonalSearch` caused severe UI lag on layout changes. Using an O(log N) binary insertion sort to maintain the priority queue eliminates the lag.

## 3. Task Board

Current Status:

- [done] 2026-06-20 Fixed UI layout wipeout ("completely falls apart") when adding new molecules, by preserving the canvas state instead of resetting it to empty arrays during `onUpdate`.
- [done] 2026-06-20 Fixed inexplicable UI lag during edge layout updates by replacing O(N log N) `Array.sort` inside the `runOrthogonalSearch` queue loop with O(log N) binary insertion sort.
- [done] 2026-06-20 Added Chemformer single-step retrosynthesis option: reuses the local Conda sidecar and checkpoint of `chem-ai/work-4`, returning Top 5 valid candidates without demo fallback. AiZynthFinder, ASKCOS, and Chemformer candidates uniformly display molecular structures, `+`, and reaction arrows. A one-click script automatically manages 8000/8765/5173 services and logs to `%LOCALAPPDATA%\Temp\.agents\orgsynflow`.
- [done] 2026-06-20 Added route de-duplication and cyclic path interception based on RDKit Canonical SMILES to AiZynthFinder and ASKCOS adapters (automatically pruning redundant nodes if a precursor is identical to the target or ancestor), resolving duplicates.
- [done] 2026-06-20 Fixed issue where the "Delete Selected" button showed without selection or caused hangs/accidental deletions: updated `web/src/App.tsx` rendering checks and deletion logic to target only selected nodes/edges, and added a `useEffect` to sync selection status, ensuring `selectedNodeId` and `selectedEdgeId` clear appropriately on deselect and update the task panel.
- [done] 2026-06-20 Merged three transition state search/plotting files under `temp/` into Windows/WSL repositories and updated Python dependencies (gradio, py3Dmol, matplotlib installed and verified via import tests).
- [done] 2026-06-20 Fixed EAS TS app integration failure by diagnosing three root causes: ① `from core.eas_ts_lib import *` failed because `sys.path` did not contain the project root; ② sync `process.wait()` blocked Gradio event loop and locked UI; ③ calling `g16.exe` directly under WSL threw `wsystem`/UNC path errors. Fixed by adding `sys.path` bootstrap, yielding progress from generator function, mapping `OUT_DIR` under `/mnt/c/...`, and wrapping `g16.exe` with `cmd.exe /c`. Verified: running `conda activate orgsynflow-chem && python app/eas_ts_app.py` under WSL starts Gradio service without abnormal exit.
- [done] 2026-06-20 Added SMILES block deletion: selected blocks can be explicitly deleted, clearing adjacent arrows, associated reactions, and selection/connection states; deletion persists across page refreshes.
- [done] 2026-06-20 Fixed retrosynthesis route insertion for inner components of multi-molecule blocks: AiZynthFinder reaction nodes are no longer mistaken for molecules; multiple precursors are split into independent nodes; reuse the selected target node; routes and original arrows keep the precursor-to-product forward direction; multi-component width and downstream spacing are corrected.
- [done] 2026-06-20 Fixed retrosynthesis candidate insertion semantics: when predicting a route from an existing SMILES block, reuse that product block; precursors of the same step are grouped into a single dot-separated reactant block pointing to the product via a single arrow.
- [done] 2026-06-20 Fixed route arrow endpoints for dot-separated multi-molecule targets: when initiating prediction from an inner component, the new reaction edge persists `targetComponentIndex` to edge data, rendering the endpoint on the target component's edge and treating other components in the block as routing obstacles.
- [done] 2026-06-20 Fixed duplicate target nodes in route candidates: when opening candidates from task logs/old results, find matching target molecules/components in the current cell using `target_smiles`. Map all route molecules with identical SMILES to the original node and skip self-loop edges.
- [done] 2026-06-20 Optimized task panel completed tasks: clicking green completed task buttons to view results/candidates includes a "Recompute" button at the bottom, while failed states continue using the error retry popup.
- [done] Three-phase plan written to `plan.md`.
- [done] Established basic CLI, adapters, API, and test suite.
- [done] OPERA downloaded and installed by user to WSL local opt path and globally accessible.
- [done] React/Vite main workspace frontend established.
- [done] Dark permanent sidebar removed.
- [done] Top workspace dropdown menu implemented.
- [done] White collapsible cell sidebar implemented.
- [done] General chemistry cells replaced UI-level hardcoded Molecule/Reaction/Route cell types.
- [done] Molecular nodes changed to structure diagram rendering, removing giant titles.
- [done] Supported multi-component structure drawing for dot-separated small molecule mixtures like `CO2.H2O`; inputs unable to be resolved fallback to formula SVGs rather than hanging on "Rendering...".
- [done] Results/logs panel moved inside the middle workspace panel with a light background.
- [done] Hand-drawn canvas arrows can be selected and deleted, self-connections are forbidden, and they no longer open irrelevant reaction tasks.
- [done] Allowed duplicate SMILES/structures to be added as independent nodes on the canvas.
- [done] Molecular node handles expanded to 8 handles.
- [done] Hidden blue handle dots around molecular nodes; connections are drawn via "Connect Molecules" continuous mode (toggled via button or Shift); connection lines are thicker and darker, and a "Delete All Connections" function is provided.
- [done] Connection lines automatically choose top/bottom or left/right center anchors based on relative node positions and draw as straight lines, avoiding bends and offsets.
- [done] WSL can reuse Windows Gaussian 16W; the project Gaussian runner automatically discovers the executable across Windows/WSL paths.
- [done] WSL `orgsynflow-chem` calculation tools confirmed (xTB, CREST, Open Babel, ASE, geomeTRIC, PySCF, Psi4, cclib, GoodVibes, RDKit).
- [done] Windows backend bridges WSL OPERA and WSL AiZynthFinder CLI, exposing statuses in `/compute/status`.
- [done] Route prediction UI changed to candidate cards, allowing insertion into the current canvas or creating new route cells; displays clear demo fallback when AiZynthFinder config is missing.
- [done] Gaussian molecular tasks submit opt/freq directly by default; advanced config popup provides job type, method, basis, charge, multiplicity, and GJF preview.
- [done] Removed permanent backend status, route candidates, and Gaussian queues from the right panel; backend status moved to a top-right compact popup, and candidates/queues moved to secondary popups under active tasks.
- [done] Task results shown via modals, removing the permanent center results panel; route predictions open candidate modals directly for insertion.
- [done] Task buttons standardized as "Compute Task (Engine)", integrating blue/yellow/green/red persistent states, result viewing, error messages, and retry flows.
- [done] Gaussian Opt/Freq merged into a single button; config popup generates default GJF, allowing parameter/input edits before submission.
- [done] Collapsible task log drawer restored at the bottom of the middle panel; cell counts and equation previews removed from left cell cards.
- [done] Added atomic update endpoint for cell task results; Gaussian queue status updates task records via polling, and sync tasks that cannot be restored after refresh are marked failed.
- [done] Replaced edge markers with non-wedge closed arrows; legacy edges recalculate nearest side handles upon loading, and edge labels are hidden by default.
- [done] Route insertion groups multiple precursors into a single dot-separated reactant node, connecting to the product with a single arrow.
- [done] Added cell delete button.
- [done] Created and verified desktop one-click toggle script.
- [done] `AIREADME.md`已按项目日志结构重写。 (AIREADME.md rewritten according to the project log structure)
- [done] "View Job Queue (Gaussian)" and "View Route Candidates" permanent buttons removed from molecular/reaction panels, with queues consolidated in task logs.
- [done] Route candidate popup serves as the direct interactive modal for successful retrosynthesis predictions and log/result reviews.
- [done] Ketcher drawing window isolated modal classes globally and refactored layout to Flexbox, resolving off-center popups, Wasm interaction misalignments, and collapsed editor boxes.
- [done] Deployed official AiZynthFinder models and stock databases to WSL, and configured default `config.yml` paths for authentic route predictions.
- [done] Created ASKCOS retrosynthesis route prediction adapter, querying Docker or downgrading gracefully to Mock/demo when offline.
- [done] Modified `/route/predict` API to support `engine` parameter dispatch, adding an engine selector popup to the frontend.
- [done] 2026-06-20 Checked and confirmed AiZynthFinder public weights in WSL: `/home/meta/data/aizynthfinder/config.yml`, `uspto_model.onnx`, etc. API smoke test for aspirin returns `used_fallback=false`.
- [done] RXNMapper and DRFP modified to fallback query WSL `orgsynflow-chem`, showing available in `/compute/status`.
- [done] Changed phenol acetylation example to single dot-separated reactant node `O=C(O)c1ccccc1O.CC(=O)OC(C)=O` pointing to aspirin, clearing stale results.
- [done] Transition state tasks merged into a single "Compute Transition State (Gaussian)" action; clicking opens a parameterized window with TS search recommendations, method/basis/charge/multiplicity/job type, displacement/rotation sliders, 3D conformation previews, and GJF previews.
- [done] Reaction/route edges changed to smart orthogonal routing, supporting side-center automatic handle selection, horizontal/vertical segments, obstacle bypass, and ranking by length/bends/segment length.
- [done] Completed public weight audit in [docs/public-model-weights-audit.md](file:///C:/Users/Meta/Project/Workspaces/orgsynflow/docs/public-model-weights-audit.md), documenting AiZynthFinder/OPERA/RXNMapper/DRFP statuses, and limitations of ASKCOS, RXNFP, Yield-BERT, and Chemprop.
- [done] Summarized results display: xTB/CREST/Gaussian parse key values, warnings, and log tails, folding raw logs; xTB/CREST returns `data.input_xyz` for 3Dmol interactive rendering.
- [done] Transition State Conformation Editor modal integrated base class `.osf-config-modal`, restoring white background, shadows, overflow clip, and correct positioning.
- [done] Supported clicking specific components inside dot-separated multi-molecule canvas blocks; molecular tasks, results, and Gaussian object IDs isolate to components, while routes/reactions use the outer container node.
- [done] Added persistent Gaussian TS workflow: RXNMapper mapping, three initial conformations, 1D/2D scanning, adaptive refinement, TS/Freq, imaginary frequency mode projection, IRC, endpoint thermochemistry, pause/resume/cancel/export, and API/CLI/React boards.
- [done] Updated default TS theory level to wB97XD/def2SVP; charge/multiplicity are auto-inferred, and method, basis, solvent, resources, temperature, and imaginary frequency threshold are editable.
- [done] Restarted WSL service under admin elevation, restoring Ubuntu WSL; validated AiZynthFinder/RXNMapper/OPERA files and real runtime inference. AiZynthFinder for aspirin returns 2 real routes with `used_fallback=false`; RXNMapper maps `CCO>>CC=O` with confidence `0.998663`; OPERA returns 5 QSAR predictions for ethanol.

Currently Runable Entries:

- [ready] Desktop double-click `C:\Users\Meta\Desktop\OrgSynFlow Toggle.cmd` to start/stop services.
- [ready] Frontend: `http://127.0.0.1:5173/`.
- [ready] API: `http://127.0.0.1:8765/health`.
- [ready] CLI: `uv run python run_cli.py ...`.
- [ready] WSL Mirror: `/home/meta/Project/Workspaces/orgsynflow`.

To Be Enhanced:

- [todo] The route candidate preview window needs to function more like a "Route Candidate Browser": previewing multiple paths, selecting the preferred path, and then inserting it into the current workspace canvas.
- [todo] Multi-step reaction layouts on the route canvas still need optimization, especially hierarchical layouts when multiple reactions, reactants, and products are present.
- [done] Visual feedback for reaction arrows should be clearer: arrows should be selectable, display step labels, and open reaction tasks.
- [done] Ketcher drawing input verified: modal centered and isolated from `.editor-strip`, Ketcher internal controls loaded properly; `CCO` fills the input and closes via Ketcher API, and clicking "Add to Canvas" adds a React Flow node rendering the structure SVG.
- [todo] Workspace save/autosave policies need to be clearer to avoid dirtying fixtures when testing or opening examples.
- [todo] Real AiZynthFinder config, stock/policy paths, and route tree parsing can be further reinforced.
- [todo] OPERA output fields need better structured display in the UI.
- [done] Gaussian TS features reaction center mapping, editable scan coordinates, 1D/2D scanning, freq/IRC feedback, and validation level loop closing; subsequent focus shifts to benchmarking more reaction types and long-term calculation validations.
- [done] WSL calculation tool status and Gaussian bridge status are exposed to `/compute/status` and the right-side task panel.
- [done] xTB/CREST are integrated into molecular task buttons, runnable directly from the frontend, sending outputs to the middle results panel.
- [todo] Integrate PySCF/Psi4/geomeTRIC into specific task buttons, rather than just showing environmental availability.
- [todo] Yield/kinetics/thermodynamics results need to aggregate to route-level scoring: overall yield, highest energy barrier, rate-determining step, major risks.
- [todo] If a real ML yield layer is needed, prioritize evaluating `rxn4chemistry/rxn_yields` or other niche-domain public models, forcing UI display of training sources, reaction families/applicable domains, and uncertainties; do not display RXNFP/DRFP features as predicted yields.
- [todo] Some React workspace descriptions in the README may lag behind the current "General Chemistry Cell" design and can be updated later.

Most Recent Verification Baseline:

- 2026-06-20 SMILES block delete regression: `cd web; npm run build` succeeded; in browser, deleting the first connected node in a 4-node/2-edge scenario resulted in 3 nodes/1 edge, and persisted after saving and refreshing. Workspace file restored from `%LOCALAPPDATA%\Temp\codex\orgsynflow-smiles-delete-test\` after testing, and verified 4 nodes/2 edges with identical SHA256 before testing.
- 2026-06-20 Component-level route regression: `uv run pytest -q tests/test_aizynth_adapter.py tests/test_route_layout.py` passed with 3; `cd web; npm run build` succeeded. Real AiZynthFinder execution in isolated workspace returned 1 step and 2 precursors; adding to canvas yielded two independent precursor nodes at `x=40`, reused group target at `x=300`, and original downstream product moved to `x=738`; two new edges were precursor → group target, and original edge was group target → product, with all markers at endpoints. Deleted isolated workspace after testing.
- `uv run pytest -q`: 36 passed.
- Frontend build command: `cd web; npm run build`.
- Task panel state regression: browser confirmed blue `rgb(37,99,235)`, yellow `rgb(244,180,0)`, green `rgb(22,128,60)`, and red `rgb(201,52,52)`. Success/failed states persist after refresh, and clicking a failed button opens the error window.
- Task panel layout regression: no horizontal scrollbar at 1280px and 819px viewports. At 819px, the three columns are ~210/369/240px, buttons do not wrap character-by-character, left sidebar is empty, and bottom log drawer is visible.
- `CO2.H2O` UI regression check: Chrome + Playwright opened `http://127.0.0.1:5173/`, added node, and confirmed multi-component structure SVG rendered. Screenshot stored at `%LOCALAPPDATA%\Temp\codex\orgsynflow\co2-h2o-component-structures-ui-check.png`.
- Layout/edge UI regression check: Chrome + Playwright confirmed results panel is inside `.detail` and light-themed. Hand-drawn canvas edges can be created and deleted via "Delete Arrow"; middle panel width is ~280px at 819px viewport. Screenshot stored at `%LOCALAPPDATA%\Temp\codex\orgsynflow\layout-edge-fix-ui-check.png`.
- Duplicate structure/connections UI regression check: Chrome + Playwright inputted `CCO\nCCO` to add 2 CCO nodes. Each node has 8 handles. Screenshot stored at `%LOCALAPPDATA%\Temp\codex\orgsynflow\duplicate-molecule-handles-ui-check.png`.
- WSL computation environment check: Windows `g16.exe` can be invoked from WSL; `core.gaussian_runner.run_gaussian_job()` ran H2O HF/STO-3G smoke test in WSL, parsing final energy/HOMO/LUMO. xTB, CREST, Open Babel, ASE, geomeTRIC, PySCF, Psi4, cclib, GoodVibes, and RDKit are functional.
- WSL quantum chemistry smoke test: PySCF H2/STO-3G energy `-1.11675931`; Psi4 H2/STO-3G energy `-1.11678332`; Gaussian16W H2O HF/STO-3G finished successfully.
- Computation API smoke test: `/compute/status` returns Gaussian Windows bridge and WSL xTB/CREST/Open Babel/PySCF/Psi4/geomeTRIC/GoodVibes/ASE; `/compute/xtb` for `O` returns `total_energy_hartree=-5.06897994546`; `/compute/crest` for `O` exits with code 0.
- Frontend UI check: browser opened `http://127.0.0.1:5173/` and right panel displayed computation backend statuses. Selecting CCO shows "xTB Opt/Energy" and "CREST Conformation Search". Clicking xTB shows `xTB CLI via WSL` and `/tmp/codex/orgsynflow/xtb_jobs/...` in results panel.
- WSL OPERA/AiZynthFinder check: `/compute/status` returns `opera` as `wsl:/home/meta/.local/bin/opera`, and `aizynthfinder` as `wsl:/home/meta/.local/opt/miniforge3/envs/orgsynflow-chem/bin/aizynthcli`. `/molecule/properties include_opera=true` for `CCO` returns OPERA `melting_point=-114`, `boiling_point=78`, `logp=-0.31`.
- Route candidate UI check: selecting CCO in browser shows "RDKit + OPERA QSAR Properties", "Predict Retrosynthetic Route", "Submit Gaussian Opt/Freq", and "Gaussian Advanced Config". Clicking route prediction opens candidate cards, fallback alerts, "Add to Current Canvas", and "Create Route Cell".
- Secondary window/edges UI check: when no object is selected, the right panel shows only task hints, hiding the backend list, candidate cards, or queue. Top-right "Backend" button launches popup. Backend/routes/queues are shown inside popups; reaction/route edges have arrow markers, and the count of visible edge labels defaults to 0.
- Route prediction direct popup check: clicking "Predict Retrosynthetic Route" displays the "Route Candidates" modal with 2 candidate cards and direct buttons for "Add to Current Canvas" and "Create Route Cell". There are 0 permanent results panels in the center.
- Dot-separated route insertion regression: multiple precursors of the same step now merge into a single dot-separated SMILES node. Verified `O=C(O)c1ccccc1O.CC(=O)OC(C)=O` as a single node pointing to aspirin via an arrow.
- Connection UI check: added three CCOs in browser, entered "Connect Molecules", clicked all three, and got `edgeCount=2` and `visibleHandles=0` with connection mode remaining active. Clicking "Delete All Connections" reset `edgeCount=0`.
- Straight connection UI check: arranged two nodes vertically, entered "Connect Molecules", clicked bottom A then top B, generating `react-flow__edge-straight canvas-edge` with path `M 315,317.5L 315,196.5` and `visibleHandles=0`. Restored example data after testing.
- Desktop toggle script: verified start, stop, and restart of 8765/5173.
- 2026-06-20 Validation: `uv run pytest -q` passed with 36; `cd web; npm run build` succeeded (Vite large chunk warning only); API `/compute/status` returns AiZynthFinder, RXNMapper, and DRFP as available. API `/route/predict` for aspirin returns `used_fallback=false`. Verified frontend `http://127.0.0.1:5173/` opens, task log defaults to expanded, route contains a single dot-separated reactant node and a marker-ended arrow, reaction selection displays only a TS button, and the TS window contains 6 displacement/rotation sliders and a 3D canvas.
- 2026-06-20 Orthogonal edge validation: `cd web; npm run build` succeeded; browser reload of `http://127.0.0.1:5173/` shows example reaction edge path as `M 310,344L 402,344L 402,336.5L 430,336.5`, all segments are horizontal/vertical, and retain `marker-end`.
- 2026-06-20 Results display validation: `cd web; npm run build` succeeded; `/compute/xtb` on `O` returns `data.input_xyz` for 3D rendering. `uv run pytest -q tests/test_route_layout.py tests/test_v5_yield.py` passed with 3. Standard `uv run pytest -q` and `tests/test_v6_api_service.py` timed out due to environmental detection blocks under WSL.
- 2026-06-20 TS white background regression: before fix, browser computed style was `background=rgba(0,0,0,0)`, `overflow=visible`, and `position=static`. Using `.osf-config-modal.ts-config-modal` restored `background=rgb(255,255,255)`, `overflow=hidden`, `position=relative`, and modal shadows. Confirmed white content layer completely covers the 1000x648 viewport.
- 2026-06-20 Component/TS workflow validation: frontend builds successfully; browser confirmed salicylic acid and acetic anhydride components can be independently selected, and the task panel uses the selected SMILES only. TS/Gaussian/API core regressions passed 17, and non-external test suites passed 25. SN2 configuration for `CBr.[Cl-]>>CCl.[Br-]` returned RXNMapper confidence=1.000, C–Cl forming / C–Br breaking, 3 candidates, and a 5x5 grid; full DFT grid calculation was not completed within the turn; the cancellation path was verified, and no residual Gaussian Link processes remained. Legacy phase1/phase2/v6 external adapters are still affected by WSL detection hangs.
- 2026-06-20 Public weights recovery validation: restarted `WslService`. `/compute/status` shows AiZynthFinder, OPERA, RXNMapper, DRFP, and WSL computation backends as available. `/route/predict` on aspirin returns `Loaded 2 route(s) from AiZynthFinder via WSL.` and `used_fallback=false`. RXNMapper mapping for `CCO>>CC=O` yields `[CH3:1][CH2:2][OH:3]>>[CH3:1][CH:2]=[O:3]` with confidence `0.998663`. OPERA on CCO returns melting point `-114`, boiling point `78`, LogP `-0.31`, water solubility `1.26`, vapor pressure `1.77`, all with AD=1.
- 2026-06-20 WSL hang recovery validation: stopped services, found API-spawned CREST and `/compute/status` WSL query left orphaned `wsl.exe`. Terminates/shutdown commands timed out under non-admin shell. Terminated 10 `wsl.exe` instances containing `/tmp/codex/orgsynflow` or `orgsynflow-chem` in command line, restoring `wsl -e true` to exit code 0. Restarted services; aspirin retrosynthesis returns `used_fallback=false` and `available=true`; CCO properties return melting point `-114`, boiling point `78`, etc. Status shows AiZynthFinder, OPERA, RXNMapper, DRFP, and CREST as available.
- 2026-06-20 Completed task recompute validation: `cd web; npm run build` succeeded (Vite large chunk warning only); added CCO node in browser and ran "Compute Molecular Descriptors (RDKit)". Task button changed to `task-status-succeeded`. Both the initial result popup and subsequent clicks on the green button display "Recompute" at the bottom. Restored `data/workspaces/example-workspace.json` from backup, keeping SHA256 identical before testing.
- 2026-06-20 Retrosynthesis candidate insertion validation: `cd web; npm run build` succeeded (Vite large chunk warning only); `uv run pytest -q tests/test_route_layout.py tests/test_workspace_api.py` passed with 5. Code inspection confirmed `addRouteCandidateToCell()` reuses the selected target node and maps precursors of the same step into a single dot-separated reactant node.
- 2026-06-20 Component-level route arrow endpoint validation: `cd web; npm run build` succeeded (Vite large chunk warning only); `uv run pytest -q tests/test_route_layout.py tests/test_workspace_api.py` passed with 5. In temporary workspace `c1ccccc1.O=C1CCC(=O)N1Br`, predicting from the second component and inserting candidates resulted in edge path `M 528,337.5L 678,337.5L 678,252L 706,252`, landing on the left edge of the target component and bypassing adjacent components. Deleted temporary workspace after testing.
- 2026-06-20 Duplicate target node regression validation: `cd web; npm run build` succeeded (Vite large chunk warning only); `uv run pytest -q tests/test_route_layout.py tests/test_workspace_api.py` passed with 5. Set up candidate route in temporary workspace where `target` and `dup` molecule IDs share `O=C1CCC(=O)N1Br`. Insertion resulted in `targetStandaloneNodes=[]`, keeping only the original component card, with path `M 468,297.5L 678,297.5L 678,252L 706,252`. Deleted temporary workspace after testing.
- 2026-06-20 Gaussian/TS output preview validation: `uv run pytest -q tests/test_v3_gaussian.py tests/test_gaussian_runner.py tests/test_ts_workflow.py tests/test_workspace_api.py` passed with 17; `cd web; npm run build` succeeded. The Gaussian parser extracts SCF cycles, convergence status, warnings/errors, final coordinates, and imaginary frequency displacements; `/jobs` and `/ts/workflow/{id}` return latest log tails/progress. TS window switches from GJF preview to output preview upon submission. TS candidate generation separates overlapping fragments, passing H-transfer distance regression checks.
- 2026-06-20 Gaussian force-termination and real-time input preview validation: `uv run pytest -q tests/test_gaussian_job_queue.py tests/test_gaussian_runner.py tests/test_v3_gaussian.py tests/test_ts_workflow.py tests/test_workspace_api.py` passed with 18; `cd web; npm run build` succeeded. Standard running Gaussian jobs can be force-terminated via cancel event, changing status to `cancelled`. Running task buttons display "Force Terminate Gaussian Process", and active TS footer shows "Force Terminate Process". Ordinary Gaussian parameter changes refresh GJF, pausing auto-sync on manual edits.
- 2026-06-20 TS input preview and availability validation: `uv run pytest -q tests/test_ts_workflow.py tests/test_gaussian_runner.py tests/test_gaussian_job_queue.py` passed with 12; `cd web; npm run build` succeeded. TS config window features editable GJF textarea, auto-sync status, and "Restore Auto Preview". Manual edits pause auto-sync, which can be restored to regenerate with wB97XD/def2SVP. `preparing`/`queued` workflows display input preview; output preview shows once running. TS footer retains "Force Terminate Process". Backend restarted and healthy.
- 2026-06-20 3D Conformation Editor fix validation: 3Dmol loaded via local import, preventing flex viewer height collapse. Atoms are labeled with indices off by default. Standard dragging controls rotation; Shift/Ctrl select clicked fragments dynamically, allowing translation and rotation within camera views. Preview coordinates sync with GJF inputs. Browser tests: dragging with Shift on component 2 translates component 2 only; dragging with Ctrl on component 1 rotates component 1 only. `npm run build` succeeded.
- 2026-06-20 CREST failure state validation: task buttons correctly map `available/status` fields from task payloads, reflecting failures with reasons instead of falsely marking failed or unavailable CREST runs as successful. Conformation search for water completed via WSL CREST 3.0.2 with exit code 0.
- 2026-06-20 Ketcher drawing editor modal fix validation: `KetcherModal` mounted via React Portal under `document.body` to bypass `.editor-strip` styling pollution. Removed duplicate modal wrappers, and added pre-bundling exclusions for Wasm worker paths. Verified `npm run build` builds successfully. Opened Ketcher in browser: modal centered at 1180x754, verified `portalEscapedEditorStrip=true`, returned `CCO` to input, and confirmed structure node added in React Flow.
- 2026-06-20 Fix canvas UI interactions: allow dragging blocks from sub-molecules, and add selected styling to single-molecule blocks.
- 2026-06-20 Gaussian/TS real-time output preview validation: enhanced `core.gaussian` parser to extract SCF energy, convergence status, warnings, and log tails. The frontend displays real-time progress inside result modals and TS config drawers. Submission switches the TS modal directly to the output preview. Fixed `run_gaussian_job` cancel parameters and added fragment overlap checks for TS candidate generation.
- 2026-06-20 Force termination and real-time GJF preview validation: standard Gaussian running jobs terminate via cancel events. Task buttons display "Force Terminate Gaussian Process" and active TS footers display "Force Terminate Process". Ordinary Gaussian parameter updates refresh GJF previews dynamically, pausing on manual edits.
- 2026-06-20 Yield estimation public weights validation: confirmed no default yield models exist in environment. Niche models like `rxn4chemistry/rxn_yields` remain future candidates. Added DeepSeek LLM estimations under `/reaction/yield` using `DEEPSEEK_API_KEY`, defaulting to `deepseek-v4-flash`. `trained_model.available` remains false to prevent misrepresenting LLM outputs as dedicated chemical yield models. All 54 tests passed; `cd web; npm run build` succeeded.
