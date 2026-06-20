from __future__ import annotations

import os
from pathlib import Path


def orgsynflow_temp_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Temp" / ".agents"
    else:
        base = Path("/tmp") / "codex"
    return base / "orgsynflow"


def orgsynflow_temp_dir(kind: str, stamp: str) -> Path:
    return orgsynflow_temp_root() / kind / stamp
