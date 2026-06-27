"""
Opportunity cost engine — measure what filtering costs, not what it saves.

When Kraitos misses profitable trades, reduce over-filtering.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

FilterAdjustment = Literal["reduce_filtering", "maintain", "tighten_filtering"]


@dataclass(frozen=True)
class OpportunityCostSnapshot:
    """Point-in-time opportunity cost metrics."""

    rejected_winners: int
    accepted_losers: int
    missed_r: float
    missed_profit: float
    opportunity_cost_ratio: float
    filter_adjustment: FilterAdjustment
    over_filtering: bool
    explanation: str

    def to_dict(self) -> dict:
        return {
            "rejected_winners": self.rejected_winners,
            "accepted_losers": self.accepted_losers,
            "missed_r": round(self.missed_r, 3),
            "missed_profit": round(self.missed_profit, 3),
            "opportunity_cost_ratio": round(self.opportunity_cost_ratio, 3),
            "filter_adjustment": self.filter_adjustment,
            "over_filtering": self.over_filtering,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class OpportunityCostEngineConfig:
    """Thresholds for detecting over-filtering."""

    over_filter_ratio: float = 1.25
    reduce_filter_ratio: float = 0.85
    min_samples: int = 5
    max_history: int = 200
    filter_relaxation: float = 0.12


@dataclass
class _RejectedWinner:
    symbol: str
    side: str
    missed_r: float
    missed_profit: float
    reason: str


@dataclass
class _AcceptedLoser:
    symbol: str
    side: str
    lost_r: float
    reason: str


class OpportunityCostEngine:
    """Track filtering cost and recommend aggression adjustments."""

    def __init__(self, config: OpportunityCostEngineConfig | None = None) -> None:
        self.config = config or OpportunityCostEngineConfig()
        self._rejected_winners: deque[_RejectedWinner] = deque(maxlen=self.config.max_history)
        self._accepted_losers: deque[_AcceptedLoser] = deque(maxlen=self.config.max_history)
        self._lock = Lock()

    def record_rejected_winner(
        self,
        *,
        symbol: str,
        side: str,
        missed_r: float,
        missed_profit: float = 0.0,
        reason: str = "",
    ) -> None:
        with self._lock:
            self._rejected_winners.append(
                _RejectedWinner(symbol, side, missed_r, missed_profit, reason)
            )

    def record_accepted_loser(
        self,
        *,
        symbol: str,
        side: str,
        lost_r: float,
        reason: str = "",
    ) -> None:
        with self._lock:
            self._accepted_losers.append(_AcceptedLoser(symbol, side, lost_r, reason))

    def record_skip(self, *, reason: str = "low_conviction") -> None:
        """Legacy hook — skips may become rejected winners on post-hoc review."""
        pass

    def assess(self) -> OpportunityCostSnapshot:
        with self._lock:
            rejected = len(self._rejected_winners)
            accepted = len(self._accepted_losers)
            missed_r = sum(w.missed_r for w in self._rejected_winners)
            missed_profit = sum(w.missed_profit for w in self._rejected_winners)
            lost_r = sum(l.lost_r for l in self._accepted_losers)

        total = rejected + accepted
        if total < self.config.min_samples:
            return OpportunityCostSnapshot(
                rejected_winners=rejected,
                accepted_losers=accepted,
                missed_r=missed_r,
                missed_profit=missed_profit,
                opportunity_cost_ratio=0.0,
                filter_adjustment="maintain",
                over_filtering=False,
                explanation=f"Insufficient samples ({total}/{self.config.min_samples})",
            )

        ratio = missed_r / max(lost_r, 0.01)
        over_filtering = ratio >= self.config.over_filter_ratio and missed_r > lost_r

        if over_filtering:
            adjustment: FilterAdjustment = "reduce_filtering"
            explanation = (
                f"Missing {missed_r:.1f}R vs {lost_r:.1f}R taken — "
                f"ratio {ratio:.2f} suggests over-filtering"
            )
        elif ratio <= self.config.reduce_filter_ratio and lost_r > missed_r:
            adjustment = "tighten_filtering"
            explanation = (
                f"Accepted losers ({lost_r:.1f}R) exceed missed winners ({missed_r:.1f}R) — "
                "maintain discipline"
            )
        else:
            adjustment = "maintain"
            explanation = f"Opportunity cost balanced — ratio {ratio:.2f}"

        return OpportunityCostSnapshot(
            rejected_winners=rejected,
            accepted_losers=accepted,
            missed_r=missed_r,
            missed_profit=missed_profit,
            opportunity_cost_ratio=round(ratio, 3),
            filter_adjustment=adjustment,
            over_filtering=over_filtering,
            explanation=explanation,
        )

    def filter_relaxation_multiplier(self) -> float:
        """Multiplier to apply when over-filtering is detected."""
        snapshot = self.assess()
        if snapshot.filter_adjustment == "reduce_filtering":
            return 1.0 + self.config.filter_relaxation
        if snapshot.filter_adjustment == "tighten_filtering":
            return 1.0 - self.config.filter_relaxation * 0.5
        return 1.0

    def conviction_floor_boost(self) -> float:
        """Points to add to conviction floor when missing profitable trades."""
        snapshot = self.assess()
        if snapshot.over_filtering:
            return 8.0 + min(snapshot.missed_r * 2.0, 12.0)
        return 0.0

    def summary(self) -> dict:
        return self.assess().to_dict()

    def reset(self) -> None:
        with self._lock:
            self._rejected_winners.clear()
            self._accepted_losers.clear()


_global_engine: OpportunityCostEngine | None = None
_global_lock = Lock()


def get_opportunity_cost_engine() -> OpportunityCostEngine:
    global _global_engine
    with _global_lock:
        if _global_engine is None:
            _global_engine = OpportunityCostEngine()
        return _global_engine


def reset_opportunity_cost_engine() -> None:
    global _global_engine
    with _global_lock:
        if _global_engine is not None:
            _global_engine.reset()


__all__ = [
    "FilterAdjustment",
    "OpportunityCostEngine",
    "OpportunityCostEngineConfig",
    "OpportunityCostSnapshot",
    "get_opportunity_cost_engine",
    "reset_opportunity_cost_engine",
]
