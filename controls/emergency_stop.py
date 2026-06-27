"""Emergency stop control — instantly disables all trading."""

from __future__ import annotations

from pathlib import Path

from controls.state_store import load_state, save_state, utc_now


class EmergencyStop:
    """Activate or clear a global trading halt."""

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    @property
    def is_active(self) -> bool:
        return bool(load_state(self._root)["emergency_stop"]["active"])

    @property
    def reason(self) -> str:
        return str(load_state(self._root)["emergency_stop"].get("reason", ""))

    @property
    def activated_at(self) -> str | None:
        value = load_state(self._root)["emergency_stop"].get("activated_at")
        return str(value) if value else None

    def activate(self, reason: str = "Operator emergency stop") -> None:
        """Immediately disable all trading activity."""
        state = load_state(self._root)
        state["emergency_stop"] = {
            "active": True,
            "reason": reason.strip() or "Operator emergency stop",
            "activated_at": utc_now(),
        }
        save_state(self._root, state)

    def clear(self) -> None:
        """Clear the emergency stop after operator review."""
        state = load_state(self._root)
        state["emergency_stop"] = {
            "active": False,
            "reason": "",
            "activated_at": None,
        }
        save_state(self._root, state)
