"""Continuous Reality State — thinking never starts, thinking never stops."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class RealityStateSnapshot:
    """Last known reality convergence per symbol."""

    symbol: str
    dominant_model_id: str
    dominant_model_name: str
    convergence_score: float
    updated_at: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "dominant_model_id": self.dominant_model_id,
            "dominant_model_name": self.dominant_model_name,
            "convergence_score": self.convergence_score,
            "updated_at": self.updated_at,
        }


class RealityStateStore:
    """Persist continuous reality understanding between cycles."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._memory: dict[str, RealityStateSnapshot] = {}
        self._path = (
            project_root / "logs" / "json" / "reality_state.json"
            if project_root
            else None
        )
        if self._path and self._path.exists():
            self._load()

    def update(self, snapshot: RealityStateSnapshot, *, persist: bool = True) -> None:
        self._memory[snapshot.symbol.strip().upper()] = snapshot
        if persist:
            self._persist()

    def flush(self) -> None:
        """Persist in-memory state once per batch cycle."""
        self._persist()

    def get(self, symbol: str) -> RealityStateSnapshot | None:
        return self._memory.get(symbol.strip().upper())

    def evidence_change_note(
        self,
        symbol: str,
        *,
        new_dominant_id: str,
        new_score: float,
    ) -> str | None:
        prior = self.get(symbol)
        if prior is None:
            return None
        if prior.dominant_model_id != new_dominant_id:
            return (
                f"Reality shifted: {prior.dominant_model_name} → "
                f"new leading model (investigating)"
            )
        if abs(prior.convergence_score - new_score) >= 10:
            return (
                f"Convergence {prior.convergence_score:.0f} → {new_score:.0f} "
                f"for {prior.dominant_model_name}"
            )
        return None

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        for symbol, raw in data.items():
            if isinstance(raw, dict):
                self._memory[symbol] = RealityStateSnapshot(
                    symbol=str(raw.get("symbol", symbol)),
                    dominant_model_id=str(raw.get("dominant_model_id", "")),
                    dominant_model_name=str(raw.get("dominant_model_name", "")),
                    convergence_score=float(raw.get("convergence_score", 0)),
                    updated_at=str(raw.get("updated_at", "")),
                )

    def _persist(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v.to_dict() for k, v in self._memory.items()}
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
