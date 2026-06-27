"""Market context bundle for parallel council analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brains.models import TradeCandidate


@dataclass(frozen=True)
class MarketCognitiveContext:
    """All market intelligence available to every council simultaneously."""

    symbol: str
    evaluation_moment: datetime | None
    bid: float
    ask: float
    spread_pips: float
    spread_limit: float
    regime_label: str
    session_label: str
    candidate: TradeCandidate

    @classmethod
    def from_candidate(
        cls,
        candidate: TradeCandidate,
        *,
        evaluation_moment: datetime | None = None,
        session_label: str = "unknown",
    ) -> MarketCognitiveContext:
        regime_label = candidate.regime.regime if candidate.regime else "unknown"
        return cls(
            symbol=candidate.symbol,
            evaluation_moment=evaluation_moment,
            bid=candidate.bid,
            ask=candidate.ask,
            spread_pips=candidate.spread_pips,
            spread_limit=candidate.spread_limit,
            regime_label=regime_label,
            session_label=session_label,
            candidate=candidate,
        )
