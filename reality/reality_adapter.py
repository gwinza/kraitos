"""Bridge RealityDecision to existing pipeline entry/sizing interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from council.cognitive_models import CIODecision
from reality.reality_models import RealityDecision


@dataclass
class _ThesisProxy:
    thesis_clear: bool
    side: str
    rejection_reason: str
    selected_strategy: str
    confidence: float


@dataclass
class RealityEntryProxy:
    """Minimal surface for trader_brain entry path — no confirmation gates."""

    hard_risk_blocked: bool
    participation: str
    allocation_multiplier: float
    mind_state: str
    reason: str
    thesis: _ThesisProxy
    cognitive: Any


def reality_as_entry_proxy(decision: RealityDecision) -> RealityEntryProxy:
    """Map V8 reality decision to entry/sizing interface used by TraderBrain."""
    if decision.convergence.convergence_score >= 70:
        mind_state = "converged"
    elif decision.convergence.convergence_score >= 50:
        mind_state = "converging"
    elif decision.convergence.uncertainty >= 70:
        mind_state = "uncertain"
    else:
        mind_state = "investigating"

    cognitive = None
    snap = decision.cognitive_snapshot
    if snap and "thesis" in snap:
        try:
            cognitive = CIODecision.from_snapshot_json(
                __import__("json").dumps(snap),
                symbol=decision.symbol,
            )
        except Exception:
            cognitive = None

    return RealityEntryProxy(
        hard_risk_blocked=decision.hard_risk_blocked,
        participation=decision.participation,
        allocation_multiplier=decision.allocation_multiplier,
        mind_state=mind_state,
        reason=decision.reason,
        thesis=_ThesisProxy(
            thesis_clear=decision.thesis.thesis_clear,
            side=decision.thesis.side,
            rejection_reason=decision.thesis.rejection_reason,
            selected_strategy=decision.thesis.selected_strategy,
            confidence=decision.thesis.confidence,
        ),
        cognitive=cognitive,
    )
