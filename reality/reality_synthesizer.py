"""Reality Synthesizer — the CIO explains reality, never counts votes."""

from __future__ import annotations

from reality.reality_models import (
    REALITY_FIRST_LAW,
    RealityConvergence,
    RealityThesis,
    WorldModel,
)


class RealitySynthesizer:
    """Chief Intelligence Officer as Reality Synthesizer."""

    def synthesize_narrative(
        self,
        *,
        dominant: WorldModel | None,
        models: tuple[WorldModel, ...],
        convergence: RealityConvergence,
        market_context: str,
    ) -> str:
        if dominant is None:
            active = sorted(
                [m for m in models if m.status != "eliminated"],
                key=lambda m: m.explanatory_power,
                reverse=True,
            )
            if not active:
                return (
                    f"{REALITY_FIRST_LAW} "
                    "Current evidence is insufficient to reconstruct market reality."
                )
            lead = active[0]
            return (
                f"Reality has not converged. Leading explanation: {lead.name} — "
                f"{lead.description} Explanatory power {lead.explanatory_power:.0f}/100. "
                f"{convergence.summary}"
            )

        parts = [
            f"The most likely reality: {dominant.name}.",
            dominant.description,
            f"Explanatory power {dominant.explanatory_power:.0f}/100.",
            f"Convergence {convergence.convergence_score:.0f}/100.",
        ]
        if dominant.strengthening_evidence:
            parts.append(f"Supporting: {'; '.join(dominant.strengthening_evidence[:3])}.")
        if dominant.weakening_evidence:
            parts.append(f"Unexplained tension: {'; '.join(dominant.weakening_evidence[:2])}.")
        if dominant.expected_events:
            parts.append(f"Expected if correct: {dominant.expected_events[0]}.")
        if dominant.falsification_events:
            parts.append(f"Invalidated if: {dominant.falsification_events[0]}.")
        parts.append(market_context[:200])
        return " ".join(parts)

    def build_thesis(
        self,
        *,
        symbol: str,
        dominant: WorldModel | None,
        convergence: RealityConvergence,
        narrative: str,
        selected_strategy: str,
        entry_logic: str,
        stop_logic: str,
        target_logic: str,
        confidence: float,
        allocation: float,
        thesis_clear: bool,
        rejection: str,
    ) -> RealityThesis:
        side = "observe"
        if dominant is not None:
            if dominant.direction == "bullish":
                side = "buy"
            elif dominant.direction == "bearish":
                side = "sell"

        supporting = dominant.strengthening_evidence if dominant else ()
        contradictory = dominant.weakening_evidence if dominant else ()
        expected = dominant.expected_events[0] if dominant and dominant.expected_events else ""
        invalidation = (
            dominant.falsification_events[0]
            if dominant and dominant.falsification_events
            else "Reality model falsified by contradictory evidence"
        )

        return RealityThesis(
            symbol=symbol,
            side=side if thesis_clear else "observe",
            reality_model=dominant.name if dominant else "none",
            reality_narrative=narrative[:800],
            selected_strategy=selected_strategy,
            supporting_evidence=supporting,
            contradictory_evidence=contradictory,
            expected_path=expected,
            entry_logic=entry_logic,
            stop_logic=stop_logic,
            target_logic=target_logic,
            invalidation=invalidation,
            confidence=confidence,
            risk_allocation=allocation,
            thesis_clear=thesis_clear,
            rejection_reason=rejection,
        )

    def build_convergence(
        self,
        *,
        models: tuple[WorldModel, ...],
        dominant_id: str,
        convergence_score: float,
        uncertainty: float,
        summary: str,
    ) -> RealityConvergence:
        dominant = next((m for m in models if m.model_id == dominant_id), None)
        active = [m for m in models if m.status in {"active", "dominant", "weakened"}]
        eliminated = [m for m in models if m.status == "eliminated"]
        return RealityConvergence(
            dominant_model_id=dominant_id,
            dominant_model_name=dominant.name if dominant else "",
            convergence_score=convergence_score,
            uncertainty=uncertainty,
            active_count=len(active),
            eliminated_count=len(eliminated),
            summary=summary,
        )
