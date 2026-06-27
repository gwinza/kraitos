"""
Decision architecture — orchestrates thesis, opportunity, conviction, cost, and aggression.

Anti-paralysis: strong expectancy + structure always earns at least probe participation.
No module vetoes; modules feed conviction and opportunity scores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from strategies.adaptive_aggression_engine import (
    AdaptiveAggressionEngine,
    get_adaptive_aggression_engine,
)
from strategies.conviction_engine import ConvictionAssessment, ConvictionEngine
from strategies.opportunity_cost_engine import (
    OpportunityCostEngine,
    get_opportunity_cost_engine,
)
from strategies.opportunity_engine import OpportunityAssessment, OpportunityEngine
from strategies.thesis_engine import ThesisEngine, TradeThesis

if TYPE_CHECKING:
    import pandas as pd

    from strategies.models import MarketContext, MicroScalpSignal, MultiTimeframeBiasResult


@dataclass(frozen=True)
class ParticipationDecision:
    """Participation assessment without rebuilding an external thesis."""

    opportunity: OpportunityAssessment
    conviction: ConvictionAssessment
    aggression_multiplier: float
    effective_size_multiplier: float
    should_participate: bool
    participation_mode: str
    summary: str
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "opportunity": self.opportunity.to_dict(),
            "conviction": self.conviction.to_dict(),
            "aggression_multiplier": round(self.aggression_multiplier, 3),
            "effective_size_multiplier": round(self.effective_size_multiplier, 3),
            "should_participate": self.should_participate,
            "participation_mode": self.participation_mode,
            "summary": self.summary,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class DecisionResult:
    """Complete decision architecture output for one opportunity."""

    thesis: TradeThesis
    opportunity: OpportunityAssessment
    conviction: ConvictionAssessment
    aggression_multiplier: float
    effective_size_multiplier: float
    should_participate: bool
    participation_mode: str
    summary: str
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "thesis": self.thesis.to_dict(),
            "opportunity": self.opportunity.to_dict(),
            "conviction": self.conviction.to_dict(),
            "aggression_multiplier": round(self.aggression_multiplier, 3),
            "effective_size_multiplier": round(self.effective_size_multiplier, 3),
            "should_participate": self.should_participate,
            "participation_mode": self.participation_mode,
            "summary": self.summary,
            "evidence": list(self.evidence),
        }


class DecisionArchitecture:
    """Next-generation capital allocation pipeline."""

    def __init__(
        self,
        *,
        thesis_engine: ThesisEngine | None = None,
        opportunity_engine: OpportunityEngine | None = None,
        conviction_engine: ConvictionEngine | None = None,
        cost_engine: OpportunityCostEngine | None = None,
        aggression_engine: AdaptiveAggressionEngine | None = None,
    ) -> None:
        self._thesis = thesis_engine or ThesisEngine()
        self._opportunity = opportunity_engine or OpportunityEngine()
        self._conviction = conviction_engine or ConvictionEngine()
        self._cost = cost_engine or get_opportunity_cost_engine()
        self._aggression = aggression_engine or get_adaptive_aggression_engine()

    def evaluate_participation(
        self,
        *,
        symbol: str,
        side: str,
        bias: MultiTimeframeBiasResult | None,
        structure: MarketContext | None,
        market_story: str = "",
        story_clear: bool = False,
        opportunity_type: str | None = None,
        candles: dict[str, pd.DataFrame] | None = None,
        momentum: MicroScalpSignal | None = None,
        reward_risk: float = 1.0,
        invalidation_level: float | None = None,
        trend_quality_score: int | None = None,
        is_tradeable: bool = True,
    ) -> ParticipationDecision:
        """Evaluate opportunity + conviction without replacing an external thesis."""
        aggression = self._aggression.assess()
        cost_boost = self._cost.conviction_floor_boost()
        filter_mult = self._cost.filter_relaxation_multiplier()

        opportunity = self._opportunity.evaluate(
            side=side,
            bias=bias,
            structure=structure,
            story_clear=story_clear,
            opportunity_type=opportunity_type,
            story_text=market_story,
            candles=candles,
            momentum=momentum,
            reward_risk=reward_risk,
            trend_quality_score=trend_quality_score,
        )

        struct_quality = None
        if structure is not None and structure.trend in {"bullish", "bearish"}:
            struct_quality = 0.75

        conviction = self._conviction.evaluate(
            side=side,
            bias=bias,  # type: ignore[arg-type]
            structure=structure,  # type: ignore[arg-type]
            story=market_story,
            story_clear=story_clear,
            opportunity_type=opportunity_type,
            opportunity_score=opportunity.opportunity_score / 100.0,
            candles=candles,
            momentum=momentum,
            invalidation_level=invalidation_level,
            aggression_multiplier=aggression.aggression_multiplier * filter_mult,
            expected_r=opportunity.expected_R,
            structure_quality=struct_quality,
        )

        adjusted_score = min(100.0, conviction.conviction_score + cost_boost)
        if adjusted_score > conviction.conviction_score:
            conviction = self._reapply_floor(conviction, adjusted_score)

        effective_size = conviction.size_multiplier * aggression.aggression_multiplier * filter_mult
        effective_size = min(1.0, max(0.10, effective_size))

        should_participate = is_tradeable and conviction.participation_mode != "avoid"
        if conviction.anti_paralysis_override:
            should_participate = is_tradeable

        evidence = (
            *conviction.evidence,
            *opportunity.reasons_to_trade[:3],
            aggression.explanation,
        )
        summary = (
            f"{symbol} {side} | opp={opportunity.opportunity_score:.0f} "
            f"conv={conviction.conviction_score:.0f} ({conviction.participation_mode}) "
            f"size={effective_size:.0%} | {market_story[:60]}"
        )

        return ParticipationDecision(
            opportunity=opportunity,
            conviction=conviction,
            aggression_multiplier=aggression.aggression_multiplier,
            effective_size_multiplier=effective_size,
            should_participate=should_participate,
            participation_mode=conviction.participation_mode,
            summary=summary,
            evidence=tuple(evidence),
        )

    def evaluate(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        bias: MultiTimeframeBiasResult | None,
        structure: MarketContext | None,
        market_story: str = "",
        story_clear: bool = False,
        opportunity_type: str | None = None,
        candles: dict[str, pd.DataFrame] | None = None,
        momentum: MicroScalpSignal | None = None,
        pip_size: float = 0.0001,
        spread_pips: float = 0.0,
        spread_limit: float = 3.0,
        expected_target_pips: float | None = None,
        invalidation_level: float | None = None,
        trend_quality_score: int | None = None,
    ) -> DecisionResult:
        aggression = self._aggression.assess()
        cost_boost = self._cost.conviction_floor_boost()
        filter_mult = self._cost.filter_relaxation_multiplier()

        thesis = self._thesis.build(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            structure=structure,
            bias=bias,
            market_story=market_story,
            pip_size=pip_size,
            spread_pips=spread_pips,
            spread_limit=spread_limit,
            expected_target_pips=expected_target_pips,
            opportunity_type=opportunity_type,
            invalidation_level=invalidation_level,
        )

        participation = self.evaluate_participation(
            symbol=symbol,
            side=side,
            bias=bias,
            structure=structure,
            market_story=market_story,
            story_clear=story_clear,
            opportunity_type=opportunity_type,
            candles=candles,
            momentum=momentum,
            reward_risk=thesis.reward_risk_ratio,
            invalidation_level=thesis.invalidation_level or invalidation_level,
            trend_quality_score=trend_quality_score,
            is_tradeable=thesis.is_tradeable,
        )

        return DecisionResult(
            thesis=thesis,
            opportunity=participation.opportunity,
            conviction=participation.conviction,
            aggression_multiplier=participation.aggression_multiplier,
            effective_size_multiplier=participation.effective_size_multiplier,
            should_participate=participation.should_participate,
            participation_mode=participation.participation_mode,
            summary=participation.summary,
            evidence=participation.evidence,
        )

    @staticmethod
    def _reapply_floor(
        conviction: ConvictionAssessment,
        adjusted_score: float,
    ) -> ConvictionAssessment:
        from dataclasses import replace

        from strategies.conviction_engine import ConvictionEngine

        mode, timing, size_mult, staged, initial_frac = ConvictionEngine._participation(
            adjusted_score
        )
        conviction_class = ConvictionEngine._classify(adjusted_score)
        return replace(
            conviction,
            conviction_score=adjusted_score,
            conviction_class=conviction_class,
            participation_mode=mode,
            timing_mode=timing,
            size_multiplier=size_mult,
            staged_entry=staged,
            initial_size_fraction=initial_frac,
        )


__all__ = [
    "DecisionArchitecture",
    "DecisionResult",
    "ParticipationDecision",
]
