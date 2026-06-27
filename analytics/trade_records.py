"""Shared enriched trade records for self-improvement analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

TradeOutcome = Literal["win", "loss", "breakeven"]
RegimeLabel = Literal["trend", "range", "breakout", "reversal", "chaos", "unknown"]
DecisionType = Literal["accepted", "rejected"]


@dataclass(frozen=True)
class EnrichedTradeRecord:
    """Closed trade with intelligence metadata for analytics."""

    trade_id: str
    symbol: str
    side: str
    exit_time: datetime
    pnl: float
    r_multiple: float
    outcome: TradeOutcome
    conviction_score: float = 0.0
    conviction_class: str = ""
    participation_mode: str = ""
    thesis_confidence: float = 0.0
    thesis_correct: bool | None = None
    thesis_partial: bool = False
    invalidation_quality: float = 0.0
    exit_quality: float = 0.0
    primary_regime: RegimeLabel = "unknown"
    market_mode: str = ""
    balance: float | None = None
    session: str = "unknown"

    @property
    def won(self) -> bool:
        return self.r_multiple > 0 or self.pnl > 0

    @property
    def lost(self) -> bool:
        return self.r_multiple < 0 or self.pnl < 0


@dataclass(frozen=True)
class RejectedOpportunityRecord:
    """A trade Kraitos rejected that would have been profitable (or not)."""

    symbol: str
    side: str
    decision_time: datetime
    reason: str
    missed_r: float = 0.0
    missed_profit: float = 0.0
    would_have_won: bool = False
    conviction_score: float = 0.0
    primary_regime: RegimeLabel = "unknown"


@dataclass(frozen=True)
class SkippedPeriodMetrics:
    """Trade count trend for over-caution detection."""

    period_label: str
    trade_count: int
    rejected_count: int
    rejected_winners: int
