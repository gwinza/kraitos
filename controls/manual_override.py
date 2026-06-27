"""Manual override to pause or resume strategy execution."""

from __future__ import annotations

from pathlib import Path

from controls.state_store import load_state, save_state, utc_now


class ManualOverride:
    """Operator pause/resume control for strategy execution."""

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    @property
    def is_paused(self) -> bool:
        return bool(load_state(self._root)["manual_override"]["paused"])

    @property
    def reason(self) -> str:
        return str(load_state(self._root)["manual_override"].get("reason", ""))

    @property
    def paused_at(self) -> str | None:
        value = load_state(self._root)["manual_override"].get("paused_at")
        return str(value) if value else None

    def pause(self, reason: str = "Operator paused strategies") -> None:
        """Pause strategy evaluation and trade execution."""
        state = load_state(self._root)
        state["manual_override"] = {
            "paused": True,
            "reason": reason.strip() or "Operator paused strategies",
            "paused_at": utc_now(),
        }
        save_state(self._root, state)

    def resume(self) -> None:
        """Resume strategy evaluation and trade execution."""
        state = load_state(self._root)
        state["manual_override"] = {
            "paused": False,
            "reason": "",
            "paused_at": None,
        }
        save_state(self._root, state)
