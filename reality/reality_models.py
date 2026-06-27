"""V8 Reality Engine — data models for world models and convergence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

WorldModelStatus = Literal["active", "weakened", "eliminated", "dominant"]
ModelDirection = Literal["bullish", "bearish", "neutral"]

REALITY_FIRST_LAW = (
    "Reality exists. Kraitos' understanding does not. "
    "The market is always correct. Kraitos' interpretation is always provisional."
)

REALITY_PRIME_DIRECTIVE = (
    "Does this improve Kraitos' ability to reconstruct market reality "
    "more accurately and more quickly than before?"
)

V8_DIVISIONS: tuple[str, ...] = (
    "trend",
    "structure",
    "liquidity",
    "volume",
    "order_flow",
    "volatility",
    "behaviour",
    "session",
    "memory",
    "narrative",
    "strategy",
    "risk",
    "execution",
)


@dataclass(frozen=True)
class WorldModel:
    """One competing explanation of what the market is doing and why."""

    model_id: str
    name: str
    description: str
    direction: ModelDirection
    assumptions: tuple[str, ...]
    expected_events: tuple[str, ...]
    falsification_events: tuple[str, ...]
    explanatory_power: float = 50.0
    strengthening_evidence: tuple[str, ...] = ()
    weakening_evidence: tuple[str, ...] = ()
    unexplained: tuple[str, ...] = ()
    status: WorldModelStatus = "active"

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "description": self.description,
            "direction": self.direction,
            "assumptions": list(self.assumptions),
            "expected_events": list(self.expected_events),
            "falsification_events": list(self.falsification_events),
            "explanatory_power": round(self.explanatory_power, 2),
            "strengthening_evidence": list(self.strengthening_evidence),
            "weakening_evidence": list(self.weakening_evidence),
            "unexplained": list(self.unexplained),
            "status": self.status,
        }


@dataclass(frozen=True)
class DivisionInvestigation:
    """One division's investigation of one World Model — evidence only."""

    division: str
    world_model_id: str
    strengthens: bool
    weakens: bool
    evidence: tuple[str, ...]
    confidence: float
    unexplained: str = ""

    def to_dict(self) -> dict:
        return {
            "division": self.division,
            "world_model_id": self.world_model_id,
            "strengthens": self.strengthens,
            "weakens": self.weakens,
            "evidence": list(self.evidence),
            "confidence": round(self.confidence, 2),
            "unexplained": self.unexplained,
        }


@dataclass(frozen=True)
class RealityConvergence:
    """Reality continuously converges — no voting, no confirmation."""

    dominant_model_id: str
    dominant_model_name: str
    convergence_score: float
    uncertainty: float
    active_count: int
    eliminated_count: int
    summary: str

    def to_dict(self) -> dict:
        return {
            "dominant_model_id": self.dominant_model_id,
            "dominant_model_name": self.dominant_model_name,
            "convergence_score": round(self.convergence_score, 2),
            "uncertainty": round(self.uncertainty, 2),
            "active_count": self.active_count,
            "eliminated_count": self.eliminated_count,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class RealityThesis:
    """Trade thesis as expression of the surviving Reality Model."""

    symbol: str
    side: str
    reality_model: str
    reality_narrative: str
    selected_strategy: str
    supporting_evidence: tuple[str, ...]
    contradictory_evidence: tuple[str, ...]
    expected_path: str
    entry_logic: str
    stop_logic: str
    target_logic: str
    invalidation: str
    confidence: float
    risk_allocation: float
    thesis_clear: bool
    rejection_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "reality_model": self.reality_model,
            "reality_narrative": self.reality_narrative,
            "selected_strategy": self.selected_strategy,
            "supporting_evidence": list(self.supporting_evidence),
            "contradictory_evidence": list(self.contradictory_evidence),
            "expected_path": self.expected_path,
            "entry_logic": self.entry_logic,
            "stop_logic": self.stop_logic,
            "target_logic": self.target_logic,
            "invalidation": self.invalidation,
            "confidence": round(self.confidence, 2),
            "risk_allocation": round(self.risk_allocation, 4),
            "thesis_clear": self.thesis_clear,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True)
class RealityDecision:
    """Full V8 cycle: evidence → world models → elimination → convergence → expression."""

    symbol: str
    world_models: tuple[WorldModel, ...]
    investigations: tuple[DivisionInvestigation, ...]
    convergence: RealityConvergence
    thesis: RealityThesis
    participation: str
    allocation_multiplier: float
    reason: str
    hard_risk_blocked: bool = False
    cognitive_snapshot: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": "v8",
            "first_law": REALITY_FIRST_LAW,
            "symbol": self.symbol,
            "world_models": [m.to_dict() for m in self.world_models],
            "investigations": [i.to_dict() for i in self.investigations],
            "convergence": self.convergence.to_dict(),
            "thesis": self.thesis.to_dict(),
            "participation": self.participation,
            "allocation_multiplier": round(self.allocation_multiplier, 4),
            "reason": self.reason,
            "hard_risk_blocked": self.hard_risk_blocked,
        }
