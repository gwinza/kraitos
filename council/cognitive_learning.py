"""Post-trade council calibration — councils evolve from outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from council.cognitive_models import CIODecision, CouncilObservation

if TYPE_CHECKING:
    from council.council_memory import CouncilMemory


@dataclass(frozen=True)
class CouncilOutcomeReview:
    """Which councils were right, wrong, and what mattered."""

    symbol: str
    regime: str
    won: bool
    r_multiple: float
    correct_councils: tuple[str, ...]
    wrong_councils: tuple[str, ...]
    signal_evidence: tuple[str, ...]
    noise_evidence: tuple[str, ...]
    summary: str


class CognitiveLearningLoop:
    """Update council influence after every completed trade."""

    def __init__(self, memory: CouncilMemory) -> None:
        self._memory = memory

    def review_trade(
        self,
        *,
        decision: CIODecision | None,
        won: bool,
        r_multiple: float,
        side: str,
    ) -> CouncilOutcomeReview | None:
        if decision is None:
            return None

        trade_direction = "bullish" if side == "buy" else "bearish"
        correct: list[str] = []
        wrong: list[str] = []
        signal: list[str] = []
        noise: list[str] = []

        for obs in decision.council_observations:
            if won and obs.direction == trade_direction and obs.confidence >= 55:
                correct.append(obs.council)
                signal.extend(obs.evidence[:1])
            elif not won and obs.direction == trade_direction and obs.confidence >= 65:
                wrong.append(obs.council)
                noise.extend(obs.evidence[:1])
            elif not won and obs.direction != trade_direction and obs.direction != "neutral":
                correct.append(obs.council)
                signal.extend(obs.evidence[:1])
            elif won and obs.direction != trade_direction and obs.direction != "neutral":
                wrong.append(obs.council)
                noise.extend(obs.evidence[:1])

        for obs in decision.council_observations:
            self._memory.record_outcome(
                member=obs.council,
                regime=decision.regime,
                confidence=obs.confidence,
                success=obs.council in correct,
            )

        self._memory.save()
        summary = (
            f"Trade {'won' if won else 'lost'} {r_multiple:+.2f}R — "
            f"correct councils: {', '.join(correct) or 'none'}; "
            f"wrong/noise: {', '.join(wrong) or 'none'}"
        )
        return CouncilOutcomeReview(
            symbol=decision.symbol,
            regime=decision.regime,
            won=won,
            r_multiple=r_multiple,
            correct_councils=tuple(correct),
            wrong_councils=tuple(wrong),
            signal_evidence=tuple(signal[:6]),
            noise_evidence=tuple(noise[:6]),
            summary=summary,
        )

    @staticmethod
    def direction_from_observation(obs: CouncilObservation) -> str:
        return obs.direction
