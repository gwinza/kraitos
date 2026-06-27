"""Persistent command-center control state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_STATE: dict[str, Any] = {
    "emergency_stop": {
        "active": False,
        "reason": "",
        "activated_at": None,
    },
    "manual_override": {
        "paused": False,
        "reason": "",
        "paused_at": None,
    },
}


def state_path(project_root: Path) -> Path:
    return project_root / "logs" / "command_center_state.json"


def load_state(project_root: Path) -> dict[str, Any]:
    path = state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_STATE))
    try:
        with path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULT_STATE))

    merged = json.loads(json.dumps(DEFAULT_STATE))
    if isinstance(raw.get("emergency_stop"), dict):
        merged["emergency_stop"].update(raw["emergency_stop"])
    if isinstance(raw.get("manual_override"), dict):
        merged["manual_override"].update(raw["manual_override"])
    return merged


def save_state(project_root: Path, state: dict[str, Any]) -> None:
    path = state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
