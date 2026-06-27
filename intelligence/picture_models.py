"""Kraitos V4 — Market Storyteller / Picture Theory data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PictureClarity = Literal["clear", "incomplete", "conflicted"]
PictureRegime = Literal["trending", "ranging", "volatile", "compressed", "transitional"]
ParticipationMode = Literal["trade", "wait", "probe", "scale_in", "stand_aside"]


@dataclass(frozen=True)
class DepartmentContribution:
    """One department's piece of the market puzzle — never a gate."""

    department: str
    observation: str
    evidence: tuple[str, ...] = ()
    confidence: float = 50.0
    contradictions: tuple[str, ...] = ()
    implications: tuple[str, ...] = ()
    uncertainty: str = ""

    def to_dict(self) -> dict:
        return {
            "department": self.department,
            "observation": self.observation,
            "evidence": list(self.evidence),
            "confidence": round(self.confidence, 2),
            "contradictions": list(self.contradictions),
            "implications": list(self.implications),
            "uncertainty": self.uncertainty,
        }


@dataclass(frozen=True)
class LiveMarketStory:
    """Continuous narrative answers to what / why / who / liquidity / objective / next chapter."""

    symbol: str
    what_is_happening: str
    why_it_is_happening: str
    who_is_in_control: str
    who_is_trapped: str
    liquidity_location: str
    market_objective: str
    next_likely_chapter: str
    narrative: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "what_is_happening": self.what_is_happening,
            "why_it_is_happening": self.why_it_is_happening,
            "who_is_in_control": self.who_is_in_control,
            "who_is_trapped": self.who_is_trapped,
            "liquidity_location": self.liquidity_location,
            "market_objective": self.market_objective,
            "next_likely_chapter": self.next_likely_chapter,
            "narrative": self.narrative,
            "confidence": round(self.confidence, 2),
        }


@dataclass(frozen=True)
class MarketPicture:
    """Fused market picture — all department observations as one coherent canvas."""

    symbol: str
    clarity: PictureClarity
    regime: PictureRegime
    dominant_side: str
    coherent_story: bool
    summary: str
    supporting_evidence: tuple[str, ...]
    contradictions: tuple[str, ...]
    noise_evidence: tuple[str, ...]
    key_evidence: tuple[str, ...]
    departments: tuple[DepartmentContribution, ...]
    confidence: float
    professional_thesis_supported: bool
    reason_not_clear: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "clarity": self.clarity,
            "regime": self.regime,
            "dominant_side": self.dominant_side,
            "coherent_story": self.coherent_story,
            "summary": self.summary,
            "supporting_evidence": list(self.supporting_evidence),
            "contradictions": list(self.contradictions),
            "noise_evidence": list(self.noise_evidence),
            "key_evidence": list(self.key_evidence),
            "departments": [d.to_dict() for d in self.departments],
            "confidence": round(self.confidence, 2),
            "professional_thesis_supported": self.professional_thesis_supported,
            "reason_not_clear": self.reason_not_clear,
        }


@dataclass(frozen=True)
class NarratorOutput:
    """Plain-English market narration — part of reasoning, not decoration."""

    symbol: str
    opening: str
    institutions: str
    retail: str
    liquidity: str
    momentum: str
    volatility: str
    next_event: str
    confidence_statement: str
    invalidation: str
    full_narration: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "opening": self.opening,
            "institutions": self.institutions,
            "retail": self.retail,
            "liquidity": self.liquidity,
            "momentum": self.momentum,
            "volatility": self.volatility,
            "next_event": self.next_event,
            "confidence_statement": self.confidence_statement,
            "invalidation": self.invalidation,
            "full_narration": self.full_narration,
        }


@dataclass(frozen=True)
class StrategyFit:
    """Ranked strategy candidate for the current market picture."""

    strategy_id: str
    strategy_name: str
    fit_score: float
    rationale: str
    entry_model: str
    stop_model: str
    target_model: str
    failure_signs: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "fit_score": round(self.fit_score, 2),
            "rationale": self.rationale,
            "entry_model": self.entry_model,
            "stop_model": self.stop_model,
            "target_model": self.target_model,
            "failure_signs": list(self.failure_signs),
        }


@dataclass(frozen=True)
class StoryTradeThesis:
    """Complete thesis — trade is the logical consequence of understanding."""

    symbol: str
    side: str
    market_story: str
    selected_strategy: str
    supporting_evidence: tuple[str, ...]
    contradictory_evidence: tuple[str, ...]
    expected_path: str
    entry_logic: str
    stop_logic: str
    target_logic: str
    scaling_plan: str
    invalidation: str
    confidence: float
    risk_allocation: float
    management_plan: str
    thesis_clear: bool
    rejection_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "market_story": self.market_story,
            "selected_strategy": self.selected_strategy,
            "supporting_evidence": list(self.supporting_evidence),
            "contradictory_evidence": list(self.contradictory_evidence),
            "expected_path": self.expected_path,
            "entry_logic": self.entry_logic,
            "stop_logic": self.stop_logic,
            "target_logic": self.target_logic,
            "scaling_plan": self.scaling_plan,
            "invalidation": self.invalidation,
            "confidence": round(self.confidence, 2),
            "risk_allocation": round(self.risk_allocation, 4),
            "management_plan": self.management_plan,
            "thesis_clear": self.thesis_clear,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True)
class StorytellerDecision:
    """Full V4 cycle output: STORY → PICTURE → THESIS → STRATEGY → EXECUTION guidance."""

    symbol: str
    story: LiveMarketStory
    picture: MarketPicture
    narration: NarratorOutput
    strategy_rankings: tuple[StrategyFit, ...]
    thesis: StoryTradeThesis
    participation: ParticipationMode
    allocation_multiplier: float
    cio_summary: str
    reason: str
    hard_risk_blocked: bool = False

    def to_dict(self) -> dict:
        return {
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
            "hard_risk_blocked": self.hard_risk_blocked,
        }


V4_DEPARTMENTS: tuple[str, ...] = (
    "story",
    "trend",
    "structure",
    "liquidity",
    "volume",
    "volatility",
    "order_flow",
    "session",
    "psychology",
    "memory",
    "strategy",
    "risk",
    "execution",
    "review",
)

ALLOCATION_BY_CONFIDENCE: tuple[tuple[float, ParticipationMode, float], ...] = (
    (92.0, "scale_in", 1.0),
    (82.0, "trade", 0.85),
    (72.0, "trade", 0.65),
    (62.0, "probe", 0.40),
    (52.0, "probe", 0.22),
    (42.0, "wait", 0.12),
    (0.0, "stand_aside", 0.0),
)
