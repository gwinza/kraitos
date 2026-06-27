"""Kraitos V5 — The Market Mind data models."""

from __future__ import annotations

from dataclasses import dataclass

from council.cognitive_models import CIODecision
from intelligence.picture_models import (
    LiveMarketStory,
    MarketPicture,
    NarratorOutput,
    StorytellerDecision,
    StrategyFit,
    StoryTradeThesis,
)

MARKET_MIND_PHILOSOPHY = (
    "Kraitos does not trade indicators, patterns, candles, or signals. "
    "Kraitos understands the behaviour creating them. "
    "The trade is the final expression of understanding — not the beginning of decision making."
)

V5_DEPARTMENTS: tuple[str, ...] = (
    "story",
    "trend",
    "structure",
    "liquidity",
    "volume",
    "volatility",
    "order_flow",
    "session",
    "macro",
    "psychology",
    "memory",
    "strategy",
    "risk",
    "execution",
    "review",
    "narrator",
)


@dataclass(frozen=True)
class MarketMindDecision:
    """
    V5 unified cycle: OBSERVE → PICTURE → REASON → THESIS → STRATEGY → EXECUTION.

    One living cognitive output — departments describe; the mind understands.
    """

    symbol: str
    story: LiveMarketStory
    picture: MarketPicture
    narration: NarratorOutput
    strategy_rankings: tuple[StrategyFit, ...]
    thesis: StoryTradeThesis
    participation: str
    allocation_multiplier: float
    cio_summary: str
    reason: str
    cognitive: CIODecision
    mind_state: str
    evidence_changes: tuple[str, ...]
    hard_risk_blocked: bool = False

    def to_dict(self) -> dict:
        return {
            "version": "v5",
            "philosophy": MARKET_MIND_PHILOSOPHY,
            "symbol": self.symbol,
            "story": self.story.to_dict(),
            "picture": self.picture.to_dict(),
            "narration": self.narration.to_dict(),
            "strategy_rankings": [s.to_dict() for s in self.strategy_rankings],
            "thesis": self.thesis.to_dict(),
            "participation": self.participation,
            "allocation_multiplier": round(self.allocation_multiplier, 4),
            "cio_summary": self.cio_summary,
            "reason": self.reason,
            "mind_state": self.mind_state,
            "evidence_changes": list(self.evidence_changes),
            "hard_risk_blocked": self.hard_risk_blocked,
            "cognitive": self.cognitive.to_dict(),
        }

    def as_storyteller(self) -> StorytellerDecision:
        """Backward-compatible V4 view for journal and legacy integrations."""
        return StorytellerDecision(
            symbol=self.symbol,
            story=self.story,
            picture=self.picture,
            narration=self.narration,
            strategy_rankings=self.strategy_rankings,
            thesis=self.thesis,
            participation=self.participation,  # type: ignore[arg-type]
            allocation_multiplier=self.allocation_multiplier,
            cio_summary=self.cio_summary,
            reason=self.reason,
            hard_risk_blocked=self.hard_risk_blocked,
        )
