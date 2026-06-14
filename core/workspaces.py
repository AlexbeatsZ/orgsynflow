from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = ROOT / "data" / "workspaces"


def list_workspaces() -> list[dict[str, Any]]:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in sorted(WORKSPACE_DIR.glob("*.json")):
        try:
            payload = _read_json(path)
        except Exception:
            continue
        items.append(
            {
                "id": payload.get("id", path.stem),
                "title": payload.get("title", path.stem),
                "path": str(path),
                "cell_count": len(payload.get("cells", [])),
                "updated_at": payload.get("updated_at"),
            }
        )
    return items


def create_workspace(title: str = "Untitled workspace") -> dict[str, Any]:
    workspace_id = _slugify(title) or f"workspace-{uuid.uuid4().hex[:8]}"
    path = _path_for(workspace_id)
    if path.exists():
        workspace_id = f"{workspace_id}-{uuid.uuid4().hex[:6]}"
        path = _path_for(workspace_id)

    now = _now()
    workspace = {
        "schema_version": 1,
        "id": workspace_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "cells": [],
        "route_candidate_sets": [],
        "jobs": [],
    }
    save_workspace(workspace_id, workspace)
    return workspace


def get_workspace(workspace_id: str) -> dict[str, Any]:
    path = _path_for(workspace_id)
    if not path.exists():
        raise FileNotFoundError(f"Workspace not found: {workspace_id}")
    return _read_json(path)


def save_workspace(workspace_id: str, workspace: dict[str, Any]) -> dict[str, Any]:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {**workspace, "id": workspace_id, "updated_at": _now()}
    path = _path_for(workspace_id)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return payload


def delete_workspace(workspace_id: str) -> dict[str, Any]:
    path = _path_for(workspace_id)
    if not path.exists():
        raise FileNotFoundError(f"Workspace not found: {workspace_id}")
    path.unlink()
    return {"deleted": True, "id": workspace_id}


def add_cell(workspace_id: str, cell_type: str, title: str, objects: dict[str, Any]) -> dict[str, Any]:
    workspace = get_workspace(workspace_id)
    now = _now()
    cell = {
        "id": f"cell-{uuid.uuid4().hex[:8]}",
        "type": cell_type,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "canvas": {"nodes": [], "edges": []},
        "objects": objects,
        "results": {},
    }
    workspace.setdefault("cells", []).append(cell)
    save_workspace(workspace_id, workspace)
    return cell


def append_result(
    workspace_id: str,
    cell_id: str,
    result_key: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    workspace = get_workspace(workspace_id)
    for cell in workspace.get("cells", []):
        if cell.get("id") == cell_id:
            cell.setdefault("results", {})[result_key] = {
                "status": "succeeded",
                "updated_at": _now(),
                "payload": result,
            }
            cell["updated_at"] = _now()
            save_workspace(workspace_id, workspace)
            return cell["results"][result_key]
    raise FileNotFoundError(f"Cell not found: {cell_id}")


def _path_for(workspace_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", workspace_id):
        raise ValueError("Workspace id may only contain letters, numbers, dot, dash, and underscore.")
    return WORKSPACE_DIR / f"{workspace_id}.json"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-").lower()
    return slug[:80]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
