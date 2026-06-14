$ErrorActionPreference = "Stop"
uv run pyinstaller `
  --noconfirm `
  --clean `
  --name OrgSynFlowV6 `
  --windowed `
  --distpath dist_v6 `
  --workpath build_v6 `
  --add-data "data;data" `
  --add-data "reports;reports" `
  desktop_app.py
