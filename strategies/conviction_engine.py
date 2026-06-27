"""
Conviction engine — aggregate module signals into participation conviction.

All modules feed conviction. No module can directly veto a trade.
Uncertain setups probe with reduced size; strong expectancy + structure still trade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from strategies.models import MarketContext, MicroScalpSignal, MultiTimeframeBiasResult

ParticipationMode = Literal["avoid", "watchlist", "probe", "normal", "aggressive"]
ConvictionClass = Literal[
    "elite",
    "strong",
    "moderate",
    "developing",
    "uncertain",
]
# Legacy aliases for downstream consumers
ConvictionLevel = Literal["attack", "normal", "defensive", "no_trade"]
TimingMode = Literal["immediate", "standard", "strict", "skip"]

PROBE_SIZE = 0.35
WATCHLIST_SIZE = 0.20
AVOID_PROBE_FLOOR = 0.15


@dataclass(frozen=True)
class ModuleContribution:
    """Single module's contribution to conviction — informative, never veto."""

    module: str
    score: float
    weight: float
    note: str

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass(frozen=True)
class ConvictionAssessment:
    """Aggregated conviction for capital allocation — no hard veto."""

    conviction_score: float
    conviction_class: ConvictionClass
    participation_mode: ParticipationMode
    story: str
    invalidators: tuple[str, ...]
    evidence: tuple[str, ...]
    module_contributions: tuple[ModuleContribution, ...] = field(default_factory=tuple)
    timing_mode: TimingMode = "standard"
    size_multiplier: float = 1.0
    staged_entry: bool = False
    initial_size_fraction: float = 1.0
    anti_paralysis_override: bool = False

    @property
    def conviction_level(self) -> ConvictionLevel:
        """Legacy mapping for existing pipeline consumers."""
        if self.participation_mode == "aggressive":
            return "attack"
        if self.participation_mode == "normal":
            return "normal"
        if self.participation_mode in {"probe", "watchlist"}:
            return "defensive"
        if self.anti_paralysis_override:
            return "defensive"
        return "defensive"

    def to_dict(self) -> dict:
        return {
            "conviction_score": round(self.conviction_score, 2),
            "conviction_class": self.conviction_class,
            "participation_mode": self.participation_mode,
            "conviction_level": self.conviction_level,
            "story": self.story,
            "invalidators": list(self.invalidators),
            "evidence": list(self.evidence),
            "module_contributions": [
                {
                    "module": c.module,
                    "score": round(c.score, 2),
                    "weight": round(c.weight, 3),
                    "note": c.note,
                }
                for c in self.module_contributions
            ],
            "timing_mode": self.timing_mode,
            "size_multiplier": round(self.size_multiplier, 3),
            "staged_entry": self.staged_entry,
            "initial_size_fraction": round(self.initial_size_fraction, 3),
            "anti_paralysis_override": self.anti_paralysis_override,
        }


@dataclass(frozen=True)
class ConvictionEngineConfig:
    """Weights and thresholds for conviction aggregation."""

    bias_weight: float = 0.22
    structure_weight: float = 0.20
    story_weight: float = 0.18
    opportunity_weight: float = 0.15
    timing_weight: float = 0.12
    momentum_weight: float = 0.08
    aggression_weight: float = 0.05
    anti_paralysis_expectancy_floor: float = 0.55
    anti_paralysis_structure_floor: float = 0.60


def _layer_aligned(bias: MultiTimeframeBiasResult, side: str, tf: str) -> bool:
    target = "bullish" if side == "buy" else "bearish"
    for layer in bias.layers:
        if layer.timeframe == tf and layer.bias == target:
            return layer.score >= 0.45
    return False


def _structure_supports(side: str, structure: MarketContext) -> bool:
    if side == "buy":
        return structure.trend == "bullish" or (structure.higher_highs and structure.higher_lows)
    return structure.trend == "bearish" or (structure.lower_highs and structure.lower_lows)


def _pullback_quality(candles: dict[str, pd.DataFrame] | None) -> bool:
    m15 = (candles or {}).get("M15")
    if m15 is None or len(m15) < 6:
        return False
    tail = m15.tail(6)
    ranges = (tail["high"] - tail["low"]).astype(float)
    return float(ranges.std()) < float(ranges.mean()) * 0.85


def _m5_trigger_ok(candles: dict[str, pd.DataFrame] | None, side: str) -> bool:
    from execution.atr_timing_engine import should_enter

    m5 = (candles or {}).get("M5")
    if m5 is None:
        return False
    return should_enter(side=side, candles=m5).allowed


def _m1_precision_ok(momentum: MicroScalpSignal | None, side: str) -> bool:
    if momentum is None:
        return False
    return momentum.action == side


class ConvictionEngine:
    """Aggregate module signals into 0–100 conviction with participation mode."""

    def __init__(self, config: ConvictionEngineConfig | None = None) -> None:
        self.config = config or ConvictionEngineConfig()

    def evaluate(
        self,
        *,
        side: str,
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
        story: str,
        story_clear: bool,
        opportunity_type: str | None = None,
        opportunity_score: float | None = None,
        candles: dict[str, pd.DataFrame] | None = None,
        momentum: MicroScalpSignal | None = None,
        invalidation_level: float | None = None,
        aggression_multiplier: float = 1.0,
        expected_r: float | None = None,
        structure_quality: float | None = None,
    ) -> ConvictionAssessment:
        if side not in {"buy", "sell"}:
            return self._minimum_probe(
                story="No directional story — probe only if structure supports",
                invalidators=(),
                evidence=("Direction unclear",),
            )

        contributions: list[ModuleContribution] = []
        evidence: list[str] = []

        bias_score = self._bias_score(bias, side)
        contributions.append(
            ModuleContribution("bias", bias_score, self.config.bias_weight, "MTF bias alignment")
        )
        if bias_score >= 0.70:
            evidence.append(f"Bias aligned ({bias_score:.0%})")

        struct_score = 1.0 if _structure_supports(side, structure) else 0.35
        if structure_quality is not None:
            struct_score = max(struct_score, min(structure_quality, 1.0))
        contributions.append(
            ModuleContribution(
                "structure", struct_score, self.config.structure_weight, "H1 structure support"
            )
        )
        if struct_score >= 0.60:
            evidence.append("Structure supports thesis")

        story_score = 0.85 if story_clear else 0.45
        if story:
            story_score = min(1.0, story_score + 0.05)
        contributions.append(
            ModuleContribution("story", story_score, self.config.story_weight, "Market story clarity")
        )

        opp_score = opportunity_score if opportunity_score is not None else self._opportunity_score(
            opportunity_type
        )
        contributions.append(
            ModuleContribution(
                "opportunity", opp_score, self.config.opportunity_weight, "Opportunity edge"
            )
        )
        if opp_score >= 0.55:
            evidence.append(f"Opportunity edge ({opp_score:.0%})")

        timing_score = 0.0
        if _pullback_quality(candles):
            timing_score += 0.40
        if _m5_trigger_ok(candles, side):
            timing_score += 0.40
        if _m1_precision_ok(momentum, side):
            timing_score += 0.20
        timing_score = min(1.0, timing_score)
        contributions.append(
            ModuleContribution("timing", timing_score, self.config.timing_weight, "Entry timing")
        )

        mom_score = 0.65 if _m1_precision_ok(momentum, side) else 0.30
        contributions.append(
            ModuleContribution("momentum", mom_score, self.config.momentum_weight, "M1 momentum")
        )

        agg_score = min(1.0, max(0.0, aggression_multiplier))
        contributions.append(
            ModuleContribution(
                "aggression", agg_score, self.config.aggression_weight, "Adaptive aggression"
            )
        )

        raw = sum(c.weighted_score for c in contributions) * 100.0
        raw = min(100.0, raw * max(0.85, aggression_multiplier))

        expectancy = expected_r if expected_r is not None else opp_score
        struct_q = structure_quality if structure_quality is not None else struct_score
        anti_paralysis = (
            expectancy >= self.config.anti_paralysis_expectancy_floor
            and struct_q >= self.config.anti_paralysis_structure_floor
        )
        if anti_paralysis and raw < 46.0:
            raw = 46.0
            evidence.append("Anti-paralysis: strong expectancy + structure → probe floor")

        score = round(raw, 2)
        conviction_class = self._classify(score)
        mode, timing, size_mult, staged, initial_frac = self._participation(score)

        if mode == "avoid" and anti_paralysis:
            mode = "probe"
            size_mult = PROBE_SIZE
            timing = "strict"

        invalidators = self._invalidators(side, invalidation_level)

        return ConvictionAssessment(
            conviction_score=score,
            conviction_class=conviction_class,
            participation_mode=mode,
            story=story or "Market story pending",
            invalidators=invalidators,
            evidence=tuple(evidence),
            module_contributions=tuple(contributions),
            timing_mode=timing,
            size_multiplier=size_mult,
            staged_entry=staged,
            initial_size_fraction=initial_frac,
            anti_paralysis_override=anti_paralysis and raw >= 46.0,
        )

    @staticmethod
    def _bias_score(bias: MultiTimeframeBiasResult, side: str) -> float:
        target = "bullish" if side == "buy" else "bearish"
        score = 0.30
        if bias.bias == target:
            score += 0.35
        elif bias.bias == "neutral":
            score += 0.10
        if _layer_aligned(bias, side, "H8"):
            score += 0.15
        if _layer_aligned(bias, side, "H4"):
            score += 0.15
        score += min(bias.confidence, 1.0) * 0.15
        return min(1.0, score)

    @staticmethod
    def _opportunity_score(opportunity_type: str | None) -> float:
        if not opportunity_type:
            return 0.40
        opp = opportunity_type.lower()
        high_edge = {"liquidity_sweep", "pullback_continuation", "breakout_retest", "compression_breakout"}
        medium_edge = {"trend_pause_resume", "failed_breakout", "mean_reversion_snapback", "session_transition"}
        if any(tag in opp for tag in high_edge):
            return 0.80
        if any(tag in opp for tag in medium_edge):
            return 0.60
        return 0.45

    @staticmethod
    def _classify(score: float) -> ConvictionClass:
        if score >= 81:
            return "elite"
        if score >= 61:
            return "strong"
        if score >= 46:
            return "moderate"
        if score >= 26:
            return "developing"
        return "uncertain"

    @staticmethod
    def _participation(
        score: float,
    ) -> tuple[ParticipationMode, TimingMode, float, bool, float]:
        if score >= 81:
            return "aggressive", "immediate", 1.0, True, 0.50
        if score >= 61:
            return "normal", "standard", 1.0, False, 1.0
        if score >= 46:
            return "probe", "standard", PROBE_SIZE, False, PROBE_SIZE
        if score >= 26:
            return "watchlist", "strict", WATCHLIST_SIZE, False, WATCHLIST_SIZE
        return "avoid", "strict", AVOID_PROBE_FLOOR, False, AVOID_PROBE_FLOOR

    @staticmethod
    def _invalidators(side: str, invalidation_level: float | None) -> tuple[str, ...]:
        if side == "buy":
            base = (
                "H1 swing low breaks",
                "M15 structure flips bearish",
                "Opposing participation overwhelms",
                "Hard stop hit",
            )
        else:
            base = (
                "H1 swing high breaks",
                "M15 structure flips bullish",
                "Opposing participation overwhelms",
                "Hard stop hit",
            )
        if invalidation_level is not None:
            return (*base, f"Invalidation level {invalidation_level:.5f} breached")
        return base

    @staticmethod
    def _minimum_probe(
        *,
        story: str,
        invalidators: tuple[str, ...],
        evidence: tuple[str, ...],
    ) -> ConvictionAssessment:
        return ConvictionAssessment(
            conviction_score=46.0,
            conviction_class="moderate",
            participation_mode="probe",
            story=story,
            invalidators=invalidators,
            evidence=evidence,
            timing_mode="strict",
            size_multiplier=PROBE_SIZE,
            initial_size_fraction=PROBE_SIZE,
            anti_paralysis_override=True,
        )

    @staticmethod
    def entry_timing_allowed(
        assessment: ConvictionAssessment,
        *,
        side: str,
        candles: pd.DataFrame | None,
    ) -> tuple[bool, str]:
        """Adaptive confirmation — probe trades still enter with reduced size."""
        from execution.atr_timing_engine import should_enter

        if assessment.participation_mode == "avoid" and not assessment.anti_paralysis_override:
            return False, f"conviction {assessment.conviction_score:.0f}/100 — watch only"

        if assessment.timing_mode == "immediate":
            if candles is None or len(candles) < 8:
                return False, "insufficient bars for attack entry"
            timing = should_enter(side=side, candles=candles)
            if timing.trigger in {"consolidation", "retracement"}:
                return True, f"attack mode — enter on {timing.trigger}"
            return True, "attack mode — enter on first valid story trigger"

        timing = should_enter(side=side, candles=candles)
        if assessment.timing_mode == "strict":
            if timing.trigger == "retracement":
                return True, f"probe — retracement OK ({timing.reason})"
            if assessment.participation_mode in {"probe", "watchlist"}:
                return True, f"probe mode — reduced size entry ({timing.reason})"
            return False, f"defensive — await retracement ({timing.reason})"

        if timing.allowed:
            return True, f"normal — {timing.trigger}: {timing.reason}"
        if assessment.participation_mode in {"probe", "watchlist"}:
            return True, f"probe — enter with reduced size ({timing.reason})"
        return False, timing.reason


__all__ = [
    "ConvictionAssessment",
    "ConvictionClass",
    "ConvictionEngine",
    "ConvictionEngineConfig",
    "ConvictionLevel",
    "ModuleContribution",
    "ParticipationMode",
    "TimingMode",
]
