"""Reinforcement learning harvester — learns from outcomes and missed edges."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EngineWeights:
    team_strength: float = 1.0
    coach: float = 1.0
    form: float = 1.0
    xg: float = 1.0
    market: float = 1.0
    context: float = 1.0
    monte_carlo: float = 1.0


class ReinforcementHarvester:
    """Adjust internal weighting based on historical prediction errors."""

    LEARNING_RATE = 0.05

    def __init__(self, project_root: Path | None = None) -> None:
        root = project_root or Path(__file__).resolve().parents[2]
        self.weights_path = root / "logs" / "sports_rl_weights.json"
        self.weights = self._load_weights()

    def get_weights(self) -> EngineWeights:
        return self.weights

    def record_outcome(
        self,
        *,
        match_id: str,
        won: bool,
        engine_contributions: dict[str, float],
        missed: bool = False,
    ) -> None:
        """Update weights from bet outcomes or missed opportunities."""
        signal = 1.0 if won else -0.5
        if missed:
            signal = 0.3

        for engine, contribution in engine_contributions.items():
            if not hasattr(self.weights, engine):
                continue
            current = getattr(self.weights, engine)
            adjustment = self.LEARNING_RATE * signal * contribution
            setattr(self.weights, engine, max(0.5, min(2.0, current + adjustment)))

        self._save_weights()
        self._append_journal(match_id, won, missed, engine_contributions)

    def _load_weights(self) -> EngineWeights:
        if self.weights_path.exists():
            data = json.loads(self.weights_path.read_text(encoding="utf-8"))
            return EngineWeights(**{k: v for k, v in data.items() if hasattr(EngineWeights, k)})
        return EngineWeights()

    def _save_weights(self) -> None:
        self.weights_path.parent.mkdir(parents=True, exist_ok=True)
        self.weights_path.write_text(
            json.dumps(self.weights.__dict__, indent=2),
            encoding="utf-8",
        )

    def _append_journal(
        self,
        match_id: str,
        won: bool,
        missed: bool,
        contributions: dict[str, float],
    ) -> None:
        journal = self.weights_path.parent / "sports_rl_journal.jsonl"
        entry = {
            "match_id": match_id,
            "won": won,
            "missed": missed,
            "contributions": contributions,
        }
        with journal.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
