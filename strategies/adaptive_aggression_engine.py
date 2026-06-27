"""
Adaptive aggression engine — scale participation with market-reading accuracy.

Strong market reading → increase aggression.
Weak market reading → reduce aggression.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

AggressionMode = Literal["surge", "normal", "cautious", "defensive"]


@dataclass(frozen=True)
class TradeOutcome:
    """Single closed trade for aggression calibration."""

    symbol: str
    side: str
    r_multiple: float
    profit: float
    thesis_correct: bool
    thesis_partial: bool = False


@dataclass(frozen=True)
class AggressionAssessment:
    """Current aggression state derived from recent performance."""

    aggression_multiplier: float
    aggression_mode: AggressionMode
    profit_factor: float
    expectancy: float
    thesis_accuracy: float
    sample_size: int
    explanation: str
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "aggression_multiplier": round(self.aggression_multiplier, 3),
            "aggression_mode": self.aggression_mode,
            "profit_factor": round(self.profit_factor, 3),
            "expectancy": round(self.expectancy, 4),
            "thesis_accuracy": round(self.thesis_accuracy, 3),
            "sample_size": self.sample_size,
            "explanation": self.explanation,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class AdaptiveAggressionEngineConfig:
    """Parameters for aggression scaling."""

    window_size: int = 20
    min_samples: int = 5
    surge_pf_threshold: float = 1.60
    surge_expectancy: float = 0.35
    surge_accuracy: float = 0.60
    defensive_pf_threshold: float = 0.85
    defensive_expectancy: float = -0.10
    defensive_accuracy: float = 0.40
    max_multiplier: float = 1.35
    min_multiplier: float = 0.65


class AdaptiveAggressionEngine:
    """Track last N trades and derive aggression multiplier."""

    def __init__(self, config: AdaptiveAggressionEngineConfig | None = None) -> None:
        self.config = config or AdaptiveAggressionEngineConfig()
        self._outcomes: deque[TradeOutcome] = deque(maxlen=self.config.window_size)
        self._lock = Lock()

    def record_outcome(
        self,
        *,
        symbol: str,
        side: str,
        r_multiple: float,
        profit: float = 0.0,
        thesis_correct: bool = False,
        thesis_partial: bool = False,
    ) -> None:
        with self._lock:
            self._outcomes.append(
                TradeOutcome(
                    symbol=symbol,
                    side=side,
                    r_multiple=r_multiple,
                    profit=profit,
                    thesis_correct=thesis_correct,
                    thesis_partial=thesis_partial,
                )
            )

    def assess(self) -> AggressionAssessment:
        with self._lock:
            outcomes = list(self._outcomes)

        n = len(outcomes)
        if n < self.config.min_samples:
            return AggressionAssessment(
                aggression_multiplier=1.0,
                aggression_mode="normal",
                profit_factor=1.0,
                expectancy=0.0,
                thesis_accuracy=0.5,
                sample_size=n,
                explanation=f"Warming up — {n}/{self.config.min_samples} trades recorded",
                evidence=("Insufficient sample for aggression adjustment",),
            )

        wins = [o for o in outcomes if o.r_multiple > 0]
        losses = [o for o in outcomes if o.r_multiple <= 0]
        gross_profit = sum(o.r_multiple for o in wins)
        gross_loss = abs(sum(o.r_multiple for o in losses))
        profit_factor = gross_profit / max(gross_loss, 0.01)
        expectancy = sum(o.r_multiple for o in outcomes) / n

        correct = sum(1 for o in outcomes if o.thesis_correct)
        partial = sum(1 for o in outcomes if o.thesis_partial and not o.thesis_correct)
        thesis_accuracy = (correct + partial * 0.5) / n

        evidence: list[str] = []
        evidence.append(f"Last {n} trades: PF={profit_factor:.2f}, E={expectancy:.2f}R")
        evidence.append(f"Thesis accuracy {thesis_accuracy:.0%}")

        mode, multiplier, explanation = self._derive_mode(
            profit_factor=profit_factor,
            expectancy=expectancy,
            thesis_accuracy=thesis_accuracy,
            evidence=evidence,
        )

        return AggressionAssessment(
            aggression_multiplier=multiplier,
            aggression_mode=mode,
            profit_factor=profit_factor,
            expectancy=expectancy,
            thesis_accuracy=thesis_accuracy,
            sample_size=n,
            explanation=explanation,
            evidence=tuple(evidence),
        )

    def _derive_mode(
        self,
        *,
        profit_factor: float,
        expectancy: float,
        thesis_accuracy: float,
        evidence: list[str],
    ) -> tuple[AggressionMode, float, str]:
        cfg = self.config

        reading_strong = (
            profit_factor >= cfg.surge_pf_threshold
            and expectancy >= cfg.surge_expectancy
            and thesis_accuracy >= cfg.surge_accuracy
        )
        reading_weak = (
            profit_factor <= cfg.defensive_pf_threshold
            or expectancy <= cfg.defensive_expectancy
            or thesis_accuracy <= cfg.defensive_accuracy
        )

        if reading_strong:
            boost = min(
                cfg.max_multiplier,
                1.0
                + (profit_factor - 1.0) * 0.15
                + expectancy * 0.20
                + (thesis_accuracy - 0.5) * 0.30,
            )
            evidence.append("Market reading strong — increasing aggression")
            return (
                "surge",
                round(boost, 3),
                f"Strong reading: PF {profit_factor:.2f}, E {expectancy:.2f}R, "
                f"accuracy {thesis_accuracy:.0%}",
            )

        if reading_weak:
            cut = max(
                cfg.min_multiplier,
                1.0
                - (1.0 - min(profit_factor, 1.0)) * 0.25
                - max(-expectancy, 0.0) * 0.30
                - max(0.5 - thesis_accuracy, 0.0) * 0.40,
            )
            evidence.append("Market reading weak — reducing aggression")
            return (
                "defensive",
                round(cut, 3),
                f"Weak reading: PF {profit_factor:.2f}, E {expectancy:.2f}R, "
                f"accuracy {thesis_accuracy:.0%}",
            )

        if expectancy > 0.15 and thesis_accuracy >= 0.50:
            evidence.append("Market reading adequate — normal aggression")
            return "normal", 1.0, "Balanced performance — maintain normal aggression"

        evidence.append("Mixed reading — cautious aggression")
        return "cautious", 0.85, "Mixed signals — slightly reduced aggression"

    def aggression_multiplier(self) -> float:
        return self.assess().aggression_multiplier

    def reset(self) -> None:
        with self._lock:
            self._outcomes.clear()


_global_engine: AdaptiveAggressionEngine | None = None
_global_lock = Lock()


def get_adaptive_aggression_engine() -> AdaptiveAggressionEngine:
    global _global_engine
    with _global_lock:
        if _global_engine is None:
            _global_engine = AdaptiveAggressionEngine()
        return _global_engine


def reset_adaptive_aggression_engine() -> None:
    global _global_engine
    with _global_lock:
        if _global_engine is not None:
            _global_engine.reset()


__all__ = [
    "AdaptiveAggressionEngine",
    "AdaptiveAggressionEngineConfig",
    "AggressionAssessment",
    "AggressionMode",
    "TradeOutcome",
    "get_adaptive_aggression_engine",
    "reset_adaptive_aggression_engine",
]
