"""
Opportunity engine — find reasons to trade, not reasons to avoid.

Asks: What opportunity exists?
Not: Why should I avoid this?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from strategies.models import MarketContext, MicroScalpSignal, MultiTimeframeBiasResult

OpportunityType = Literal[
    "pullback_continuation",
    "liquidity_sweep",
    "breakout_retest",
    "failed_breakout",
    "compression_breakout",
    "trend_pause_resume",
    "mean_reversion_snapback",
    "session_transition",
    "structure_alignment",
    "momentum_continuation",
    "none",
]

ParticipationRecommendation = Literal[
    "aggressive",
    "normal",
    "probe",
    "watchlist",
    "monitor",
]


@dataclass(frozen=True)
class OpportunityAssessment:
    """Positive-framed opportunity discovery result."""

    opportunity_score: float
    opportunity_type: OpportunityType
    expected_edge: float
    expected_R: float
    expected_duration: str
    participation_recommendation: ParticipationRecommendation
    reasons_to_trade: tuple[str, ...] = field(default_factory=tuple)
    edge_sources: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "opportunity_score": round(self.opportunity_score, 2),
            "opportunity_type": self.opportunity_type,
            "expected_edge": round(self.expected_edge, 3),
            "expected_R": round(self.expected_R, 3),
            "expected_duration": self.expected_duration,
            "participation_recommendation": self.participation_recommendation,
            "reasons_to_trade": list(self.reasons_to_trade),
            "edge_sources": list(self.edge_sources),
        }


@dataclass(frozen=True)
class OpportunityEngineConfig:
    """Scoring weights for opportunity discovery."""

    bias_weight: float = 0.25
    structure_weight: float = 0.25
    story_weight: float = 0.20
    momentum_weight: float = 0.15
    liquidity_weight: float = 0.15
    min_score_for_probe: float = 35.0


class OpportunityEngineError(Exception):
    """Raised when opportunity inputs are invalid."""


class OpportunityEngine:
    """Discover and score tradeable opportunities."""

    def __init__(self, config: OpportunityEngineConfig | None = None) -> None:
        self.config = config or OpportunityEngineConfig()

    def evaluate(
        self,
        *,
        side: str,
        bias: MultiTimeframeBiasResult | None,
        structure: MarketContext | None,
        story_clear: bool = False,
        opportunity_type: str | None = None,
        story_text: str = "",
        candles: dict[str, pd.DataFrame] | None = None,
        momentum: MicroScalpSignal | None = None,
        reward_risk: float = 1.0,
        trend_quality_score: int | None = None,
    ) -> OpportunityAssessment:
        reasons: list[str] = []
        edge_sources: list[str] = []

        opp_type = self._resolve_type(opportunity_type, side, structure, bias)
        bias_score = self._bias_edge(side, bias, reasons, edge_sources)
        struct_score = self._structure_edge(side, structure, reasons, edge_sources)
        story_score = self._story_edge(story_clear, story_text, reasons, edge_sources)
        mom_score = self._momentum_edge(side, momentum, reasons, edge_sources)
        liq_score = self._liquidity_edge(opp_type, structure, reasons, edge_sources)

        raw = (
            bias_score * self.config.bias_weight
            + struct_score * self.config.structure_weight
            + story_score * self.config.story_weight
            + mom_score * self.config.momentum_weight
            + liq_score * self.config.liquidity_weight
        )
        score = min(100.0, raw * 100.0)

        if trend_quality_score is not None and trend_quality_score >= 65:
            score = min(100.0, score + 8.0)
            reasons.append(f"Trend quality {trend_quality_score} supports continuation")

        expected_edge = min(1.0, score / 100.0)
        expected_r = self._expected_r(reward_risk, expected_edge, opp_type)
        duration = self._duration(opp_type, candles)
        participation = self._participation(score)

        if not reasons:
            reasons.append("Market structure offers a tradable asymmetry")

        return OpportunityAssessment(
            opportunity_score=round(score, 2),
            opportunity_type=opp_type,
            expected_edge=round(expected_edge, 3),
            expected_R=round(expected_r, 3),
            expected_duration=duration,
            participation_recommendation=participation,
            reasons_to_trade=tuple(reasons),
            edge_sources=tuple(edge_sources),
        )

    @staticmethod
    def _resolve_type(
        opportunity_type: str | None,
        side: str,
        structure: MarketContext | None,
        bias: MultiTimeframeBiasResult | None,
    ) -> OpportunityType:
        if opportunity_type:
            normalized = opportunity_type.lower().replace(" ", "_")
            valid: tuple[OpportunityType, ...] = (
                "pullback_continuation",
                "liquidity_sweep",
                "breakout_retest",
                "failed_breakout",
                "compression_breakout",
                "trend_pause_resume",
                "mean_reversion_snapback",
                "session_transition",
            )
            for tag in valid:
                if tag in normalized:
                    return tag

        if structure is not None:
            if structure.last_bos is not None:
                return "breakout_retest"
            if structure.trend in {"bullish", "bearish"}:
                return "pullback_continuation"

        if bias is not None and bias.confidence >= 0.55:
            return "momentum_continuation"

        if structure is not None and structure.trend != "neutral":
            return "structure_alignment"

        return "none"

    @staticmethod
    def _bias_edge(
        side: str,
        bias: MultiTimeframeBiasResult | None,
        reasons: list[str],
        edge_sources: list[str],
    ) -> float:
        if bias is None:
            return 0.35
        target = "bullish" if side == "buy" else "bearish"
        score = 0.30 + min(bias.confidence, 1.0) * 0.40
        if bias.bias == target:
            score += 0.25
            reasons.append(f"{target.capitalize()} MTF bias aligned")
            edge_sources.append("bias_alignment")
        elif bias.bias == "neutral":
            score += 0.10
        return min(1.0, score)

    @staticmethod
    def _structure_edge(
        side: str,
        structure: MarketContext | None,
        reasons: list[str],
        edge_sources: list[str],
    ) -> float:
        if structure is None:
            return 0.30
        score = 0.35
        if side == "buy":
            if structure.trend == "bullish" or (structure.higher_highs and structure.higher_lows):
                score += 0.40
                reasons.append("Bullish structure — higher highs and higher lows")
                edge_sources.append("structure_trend")
            if structure.support_zones:
                score += 0.10
                reasons.append("Support zone nearby for defined risk")
        else:
            if structure.trend == "bearish" or (structure.lower_highs and structure.lower_lows):
                score += 0.40
                reasons.append("Bearish structure — lower highs and lower lows")
                edge_sources.append("structure_trend")
            if structure.resistance_zones:
                score += 0.10
                reasons.append("Resistance zone nearby for defined risk")
        if structure.liquidity_zones:
            score += 0.10
            edge_sources.append("liquidity_pools")
        return min(1.0, score)

    @staticmethod
    def _story_edge(
        story_clear: bool,
        story_text: str,
        reasons: list[str],
        edge_sources: list[str],
    ) -> float:
        score = 0.70 if story_clear else 0.40
        if story_text:
            score += 0.10
            reasons.append(f"Clear market story: {story_text[:80]}")
            edge_sources.append("narrative_clarity")
        elif story_clear:
            reasons.append("Market story is coherent across timeframes")
        return min(1.0, score)

    @staticmethod
    def _momentum_edge(
        side: str,
        momentum: MicroScalpSignal | None,
        reasons: list[str],
        edge_sources: list[str],
    ) -> float:
        if momentum is None:
            return 0.35
        if momentum.action == side:
            reasons.append(f"M1 momentum confirms {side}")
            edge_sources.append("momentum_trigger")
            return 0.85
        if momentum.action == "no_trade":
            return 0.40
        return 0.25

    @staticmethod
    def _liquidity_edge(
        opp_type: OpportunityType,
        structure: MarketContext | None,
        reasons: list[str],
        edge_sources: list[str],
    ) -> float:
        score = 0.35
        if opp_type == "liquidity_sweep":
            score = 0.90
            reasons.append("Liquidity sweep offers asymmetric entry")
            edge_sources.append("liquidity_sweep")
        elif structure is not None and structure.liquidity_zones:
            score = 0.65
            reasons.append("Target liquidity identified")
            edge_sources.append("liquidity_target")
        return score

    @staticmethod
    def _expected_r(reward_risk: float, edge: float, opp_type: OpportunityType) -> float:
        base = max(reward_risk, 0.8)
        type_boost = {
            "liquidity_sweep": 0.35,
            "pullback_continuation": 0.25,
            "breakout_retest": 0.30,
            "compression_breakout": 0.28,
            "trend_pause_resume": 0.20,
        }.get(opp_type, 0.15)
        return round(base * (0.70 + edge * 0.30) + type_boost, 3)

    @staticmethod
    def _duration(opp_type: OpportunityType, candles: dict[str, pd.DataFrame] | None) -> str:
        scalp_types = {"liquidity_sweep", "mean_reversion_snapback", "session_transition"}
        swing_types = {"pullback_continuation", "breakout_retest", "compression_breakout"}
        if opp_type in scalp_types:
            return "15m–2h"
        if opp_type in swing_types:
            return "2h–8h"
        m15 = (candles or {}).get("M15")
        if m15 is not None and len(m15) >= 20:
            return "1h–4h"
        return "1h–6h"

    @staticmethod
    def _participation(score: float) -> ParticipationRecommendation:
        if score >= 75:
            return "aggressive"
        if score >= 55:
            return "normal"
        if score >= 35:
            return "probe"
        if score >= 20:
            return "watchlist"
        return "monitor"


__all__ = [
    "OpportunityAssessment",
    "OpportunityEngine",
    "OpportunityEngineConfig",
    "OpportunityEngineError",
    "OpportunityType",
    "ParticipationRecommendation",
]
