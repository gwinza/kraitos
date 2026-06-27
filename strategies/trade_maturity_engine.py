"""
Trade maturity engine — grandmaster hierarchy: direction → location → timing →
confirmation → execution → management.

Teaches Kraitos WHEN an idea has matured into a trade — not more rejection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from strategies.location_quality_engine import LocationQualityEngine, LocationQualityResult
from strategies.market_acceptance_engine import MarketAcceptanceEngine, MarketAcceptanceResult
from strategies.models import MarketContext, MicroScalpSignal, MultiTimeframeBiasResult
from strategies.scout_commit_engine import ScoutCommitEngine, ScoutCommitResult
from strategies.timing_quality_engine import TimingQualityEngine, TimingQualityResult

MaturityStage = Literal[
    "idea",
    "developing",
    "ready",
    "active",
    "failing",
    "invalidated",
]

ParticipationCommitment = Literal[
    "wait",
    "watchlist",
    "micro_probe",
    "probe",
    "normal",
    "aggressive",
    "reduce",
    "scratch",
    "exit",
]


@dataclass(frozen=True)
class TradeMaturityResult:
    maturity_score: int
    maturity_stage: MaturityStage
    direction_quality: int
    location_quality: int
    timing_quality: int
    confirmation_quality: int
    execution_quality: int
    management_quality: int
    commitment: ParticipationCommitment
    size_multiplier: float
    explanation: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    location: LocationQualityResult | None = None
    timing: TimingQualityResult | None = None
    acceptance: MarketAcceptanceResult | None = None
    scout_commit: ScoutCommitResult | None = None

    def to_dict(self) -> dict:
        return {
            "maturity_score": self.maturity_score,
            "maturity_stage": self.maturity_stage,
            "direction_quality": self.direction_quality,
            "location_quality": self.location_quality,
            "timing_quality": self.timing_quality,
            "confirmation_quality": self.confirmation_quality,
            "execution_quality": self.execution_quality,
            "management_quality": self.management_quality,
            "commitment": self.commitment,
            "size_multiplier": round(self.size_multiplier, 3),
            "explanation": self.explanation,
            "evidence": list(self.evidence),
            "location": self.location.to_dict() if self.location else None,
            "timing": self.timing.to_dict() if self.timing else None,
            "acceptance": self.acceptance.to_dict() if self.acceptance else None,
            "scout_commit": self.scout_commit.to_dict() if self.scout_commit else None,
        }


@dataclass(frozen=True)
class TradeMaturityConfig:
    ready_threshold: int = 68
    developing_threshold: int = 52
    excellent_location: int = 72
    gbpjpy_ready_floor: int = 72
    gbpjpy_probe_floor: int = 58
    scalp_ready_floor: int = 65
    harvest_patience_bonus: int = 8
    scalp_scratch_r: float = -0.25


class TradeMaturityEngine:
    """Recognise trade maturity — strike when all six layers align."""

    def __init__(
        self,
        config: TradeMaturityConfig | None = None,
        *,
        location: LocationQualityEngine | None = None,
        timing: TimingQualityEngine | None = None,
        acceptance: MarketAcceptanceEngine | None = None,
    ) -> None:
        self.config = config or TradeMaturityConfig()
        self._location = location or LocationQualityEngine()
        self._timing = timing or TimingQualityEngine()
        self._acceptance = acceptance or MarketAcceptanceEngine()
        self._scout_commit = ScoutCommitEngine()

    def evaluate_entry(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        target_price: float | None,
        spread_pips: float,
        pip_size: float,
        setup_kind: str = "harvest",
        bias: MultiTimeframeBiasResult | None = None,
        structure: MarketContext | None = None,
        candles: dict[str, pd.DataFrame] | None = None,
        momentum: MicroScalpSignal | None = None,
        invalidation_level: float | None = None,
        institutional_structure: object | None = None,
        range_intelligence: object | None = None,
        execution_score: int | None = None,
        conviction_score: float | None = None,
        story_clear: bool = False,
        market_phase: str = "",
        trend_quality: int = 50,
    ) -> TradeMaturityResult:
        m5 = candles.get("M5") if candles else None
        if not isinstance(m5, pd.DataFrame):
            m5 = candles.get("M1") if candles else None

        direction = self._direction_quality(side, bias, structure, story_clear)
        loc = self._location.evaluate(
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            spread_pips=spread_pips,
            pip_size=pip_size,
            candles=m5 if isinstance(m5, pd.DataFrame) else None,
            institutional_structure=institutional_structure,
            range_intelligence=range_intelligence,
        )
        timing = self._timing.evaluate(
            side=side,
            candles=m5 if isinstance(m5, pd.DataFrame) else None,
            key_level=invalidation_level,
        )
        accept = self._acceptance.evaluate(
            side=side,
            candles=m5 if isinstance(m5, pd.DataFrame) else None,
            invalidation_level=invalidation_level,
            structure=structure,
            spread_pips=spread_pips,
        )
        confirmation = self._confirmation_quality(accept, timing, momentum)
        execution = execution_score if execution_score is not None else self._execution_quality(
            timing, loc, spread_pips
        )
        management = 55 if setup_kind == "harvest" else 50

        weights = {
            "direction": 0.18,
            "location": 0.22,
            "timing": 0.22,
            "confirmation": 0.20,
            "execution": 0.12,
            "management": 0.06,
        }
        if setup_kind == "harvest":
            weights["direction"] = 0.22
            weights["timing"] = 0.16
            management = min(100, management + self.config.harvest_patience_bonus)

        maturity_score = int(
            direction * weights["direction"]
            + loc.location_quality_score * weights["location"]
            + timing.timing_quality_score * weights["timing"]
            + confirmation * weights["confirmation"]
            + execution * weights["execution"]
            + management * weights["management"]
        )
        core_min = min(
            loc.location_quality_score,
            timing.timing_quality_score,
            confirmation,
        )

        stage = self._stage(
            maturity_score=maturity_score,
            core_min=core_min,
            direction=direction,
            timing=timing,
            acceptance=accept,
            setup_kind=setup_kind,
        )
        commitment, size_mult = self._commitment(
            stage=stage,
            symbol=symbol,
            setup_kind=setup_kind,
            location=loc,
            timing=timing,
            acceptance=accept,
            conviction_score=conviction_score,
            maturity_score=maturity_score,
            stop_pips=abs(entry_price - stop_loss) / pip_size if pip_size > 0 else 99,
            spread_pips=spread_pips,
            direction=direction,
            momentum=momentum,
            story_clear=story_clear,
            market_phase=market_phase,
            trend_quality=trend_quality,
        )
        scout = self._scout_commit.evaluate_entry(
            side=side,
            setup_kind=setup_kind,
            maturity_stage=stage,
            direction_quality=direction,
            location=loc,
            timing=timing,
            acceptance=accept,
            momentum=momentum,
            story_clear=story_clear,
            market_phase=market_phase,
            trend_quality=trend_quality,
            conviction_score=conviction_score,
            maturity_score=maturity_score,
            stop_pips=abs(entry_price - stop_loss) / pip_size if pip_size > 0 else 99,
            spread_pips=spread_pips,
            symbol=symbol,
        )
        commitment, size_mult = self._map_scout_commit(scout, commitment, size_mult)

        evidence = (
            f"direction={direction}",
            f"location={loc.location_quality_score}",
            f"timing={timing.timing_quality_score}",
            f"confirmation={confirmation}",
            f"execution={execution}",
            *loc.evidence[:2],
            *timing.evidence[:2],
            *accept.evidence[:2],
        )
        explanation = (
            f"Maturity {maturity_score}/100 ({stage}) — {commitment} @ {size_mult:.0%}. "
            f"{loc.explanation.split(' |')[0]}; {timing.explanation.split(' |')[0]}"
        )

        return TradeMaturityResult(
            maturity_score=maturity_score,
            maturity_stage=stage,
            direction_quality=direction,
            location_quality=loc.location_quality_score,
            timing_quality=timing.timing_quality_score,
            confirmation_quality=confirmation,
            execution_quality=execution,
            management_quality=management,
            commitment=commitment,
            size_multiplier=size_mult,
            explanation=explanation,
            evidence=evidence,
            location=loc,
            timing=timing,
            acceptance=accept,
            scout_commit=scout,
        )

    def evaluate_open(
        self,
        *,
        side: str,
        current_r: float,
        setup_kind: str,
        acceptance: MarketAcceptanceResult | None = None,
        timing: TimingQualityResult | None = None,
        trend_health: int = 50,
    ) -> TradeMaturityResult:
        """Management layer for open trades — active / failing / invalidated."""
        rejection = acceptance.rejection_score if acceptance else 50
        acceptance_score = acceptance.acceptance_score if acceptance else 50

        if current_r <= self.config.scalp_scratch_r and setup_kind == "micro_scalp":
            stage: MaturityStage = "failing"
            commitment: ParticipationCommitment = "scratch"
            size_mult = 0.0
        elif rejection >= 75 or (
            acceptance
            and acceptance.acceptance_state.startswith("rejecting")
            and current_r < 0
        ):
            stage = "invalidated"
            commitment = "exit"
            size_mult = 0.0
        elif current_r < -0.35 and rejection > acceptance_score:
            stage = "failing"
            commitment = "reduce" if setup_kind == "harvest" else "scratch"
            size_mult = 0.5 if setup_kind == "harvest" else 0.0
        elif current_r > 0.5 and acceptance_score >= 60:
            stage = "active"
            commitment = "normal"
            size_mult = 1.0
        elif setup_kind == "harvest" and trend_health >= 55 and current_r > -0.5:
            stage = "active"
            commitment = "normal"
            size_mult = 1.0
        else:
            stage = "active"
            commitment = "normal"
            size_mult = 1.0

        score = max(0, min(100, int(50 + current_r * 20 + acceptance_score * 0.3)))
        return TradeMaturityResult(
            maturity_score=score,
            maturity_stage=stage,
            direction_quality=50,
            location_quality=50,
            timing_quality=timing.timing_quality_score if timing else 50,
            confirmation_quality=acceptance_score,
            execution_quality=50,
            management_quality=trend_health,
            commitment=commitment,
            size_multiplier=size_mult,
            explanation=f"Open trade maturity: {stage} — {commitment} at {current_r:.2f}R",
            evidence=(f"current_r={current_r:.2f}", f"setup={setup_kind}"),
            acceptance=acceptance,
            timing=timing,
        )

    @staticmethod
    def _direction_quality(
        side: str,
        bias: MultiTimeframeBiasResult | None,
        structure: MarketContext | None,
        story_clear: bool,
    ) -> int:
        score = 45
        if bias is not None:
            if side == "buy" and bias.bias == "bullish":
                score += int(bias.confidence * 35)
            elif side == "sell" and bias.bias == "bearish":
                score += int(bias.confidence * 35)
            elif bias.bias == "neutral":
                score -= 10
            else:
                score -= 18
        if structure is not None:
            if side == "buy" and structure.trend == "bullish":
                score += 15
            elif side == "sell" and structure.trend == "bearish":
                score += 15
            elif structure.trend == "ranging":
                score += 5
            else:
                score -= 12
        if story_clear:
            score += 8
        return max(0, min(100, score))

    @staticmethod
    def _confirmation_quality(
        accept: MarketAcceptanceResult,
        timing: TimingQualityResult,
        momentum: MicroScalpSignal | None,
    ) -> int:
        score = int(accept.acceptance_score * 0.65 + timing.timing_quality_score * 0.35)
        if accept.acceptance_state.startswith("rejecting"):
            score -= 20
        if accept.acceptance_state.startswith("accepting"):
            score += 10
        if momentum is not None and momentum.action in {"buy", "sell"}:
            score += 8
        return max(0, min(100, score))

    @staticmethod
    def _execution_quality(
        timing: TimingQualityResult,
        location: LocationQualityResult,
        spread_pips: float,
    ) -> int:
        score = 55
        if timing.entry_too_late:
            score -= 25
        if timing.entry_too_early:
            score -= 15
        if timing.reaction_detected or timing.reclaim_detected:
            score += 18
        if location.chase_risk > 0.6:
            score -= 20
        if location.reward_window_open:
            score += 12
        if spread_pips > 2.5:
            score -= 8
        return max(0, min(100, score))

    def _stage(
        self,
        *,
        maturity_score: int,
        core_min: int,
        direction: int,
        timing: TimingQualityResult,
        acceptance: MarketAcceptanceResult,
        setup_kind: str,
    ) -> MaturityStage:
        if acceptance.acceptance_state.startswith("rejecting"):
            return "developing" if maturity_score >= self.config.developing_threshold else "idea"
        if direction < 42:
            return "idea"
        if timing.entry_too_early and not timing.reaction_detected:
            return "idea"
        if maturity_score >= self.config.ready_threshold and core_min >= 58:
            if setup_kind == "micro_scalp" and maturity_score < self.config.scalp_ready_floor:
                return "developing"
            return "ready"
        if maturity_score >= self.config.developing_threshold or core_min >= 52:
            return "developing"
        return "idea"

    def _commitment(
        self,
        *,
        stage: MaturityStage,
        symbol: str,
        setup_kind: str,
        location: LocationQualityResult,
        timing: TimingQualityResult,
        acceptance: MarketAcceptanceResult,
        conviction_score: float | None,
        maturity_score: int,
        stop_pips: float,
        spread_pips: float,
        direction: int = 50,
        momentum: MicroScalpSignal | None = None,
        story_clear: bool = False,
        market_phase: str = "",
        trend_quality: int = 50,
    ) -> tuple[ParticipationCommitment, float]:
        sym = symbol.strip().upper()
        is_gbpjpy = sym == "GBPJPY"
        is_scalp = setup_kind == "micro_scalp"

        if stage == "idea":
            conv = conviction_score or 50.0
            mult = 0.35 if conv >= 55 else 0.25 if conv >= 46 else 0.15
            if is_scalp:
                mult = min(mult, 0.30)
            if is_gbpjpy:
                mult = min(mult, 0.22)
            return "micro_probe" if is_scalp else "probe", mult

        if stage == "developing":
            excellent_loc = location.location_quality_score >= self.config.excellent_location
            clean_risk = stop_pips <= 25 or (is_gbpjpy and stop_pips <= 35)
            reward_ok = location.reward_window_open
            not_rejected = not acceptance.acceptance_state.startswith("rejecting")
            not_late = not timing.entry_too_late
            probe_floor = self.config.gbpjpy_probe_floor if is_gbpjpy else 0
            conv = conviction_score or 50.0

            if (
                excellent_loc
                and clean_risk
                and reward_ok
                and not_rejected
                and not_late
                and maturity_score >= max(self.config.developing_threshold, probe_floor)
            ):
                mult = 0.20 if is_scalp else 0.30
            else:
                mult = 0.30 if conv >= 55 else 0.22 if conv >= 46 else 0.18
            if is_gbpjpy:
                mult = min(mult, 0.28)
            if is_scalp:
                mult = min(mult, 0.35)
            return "micro_probe" if is_scalp else "probe", mult

        # ready
        if is_gbpjpy and maturity_score < self.config.gbpjpy_ready_floor:
            return "probe", 0.28

        conv = conviction_score or 55.0
        if conv >= 75 and maturity_score >= 78 and location.location_quality_score >= 65:
            mult = 1.0 if not is_gbpjpy else 0.75
            return "aggressive", mult
        if is_scalp:
            if timing.timing_quality_score >= 60 and acceptance.acceptance_score >= 55:
                return "normal", 0.85 if not is_gbpjpy else 0.65
            return "probe", 0.35
        return "normal", 0.90 if not is_gbpjpy else 0.70

    @staticmethod
    def _map_scout_commit(
        scout: ScoutCommitResult,
        fallback_commitment: ParticipationCommitment,
        fallback_size: float,
    ) -> tuple[ParticipationCommitment, float]:
        stage = scout.participation_stage
        if scout.size_multiplier <= 0:
            return "scratch", 0.0
        if stage == "exit":
            return "exit", 0.0
        if stage == "press":
            return "aggressive", scout.size_multiplier
        if stage == "commit":
            return "normal", scout.size_multiplier
        if stage == "scout":
            if scout.effective_setup_kind == "micro_scalp":
                return "micro_probe", scout.size_multiplier
            return "probe", scout.size_multiplier
        if stage == "idea" and scout.scout_or_commit == "scout":
            return "micro_probe", scout.size_multiplier
        return fallback_commitment, min(fallback_size, scout.size_multiplier)


__all__ = [
    "TradeMaturityEngine",
    "TradeMaturityResult",
    "TradeMaturityConfig",
    "MaturityStage",
    "ParticipationCommitment",
]
