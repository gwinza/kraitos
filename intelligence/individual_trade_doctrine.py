"""
Kraitos DNA v1.1 — Individual Trade Doctrine.

Every trade is an individual negotiation: personality, readiness, TP geometry,
size, and dynamic exit — without replacing Story / Participation / Thesis doctrine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Literal

import pandas as pd

from core.helpers import pip_size_for_symbol

TradePersonalityKind = Literal[
    "TREND_CONTINUATION",
    "LIQUIDITY_SWEEP_REVERSAL",
    "LIQUIDITY_SWEEP_CONTINUATION",
    "RANGE_MEAN_REVERSION",
    "SESSION_BREAKOUT",
    "EXHAUSTION_REVERSAL",
    "CHOPPY_FRAGILE_SETUP",
    "UNKNOWN",
]

ReadinessState = Literal["READY_NOW", "SKIP_WEAK_OPPORTUNITY"]

TPMode = Literal["FAST_TP", "NORMAL_TP", "EXPANSION_TP"]

ExitDecision = Literal[
    "HOLD",
    "REDUCE_RISK",
    "EXIT_EARLY",
    "MOVE_TO_BREAKEVEN",
    "TRAIL_RUNNER",
]

TradeGrade = Literal["A+", "B", "C", "D"]

STRONG_REWARD_R = 0.80
STAGNATION_BARS_M5 = 12
STAGNATION_DEAD_R = 0.05
MIN_REALISTIC_R_FOR_NORMAL = 0.70


class _PersonalityDefaults(Enum):
    TREND_CONTINUATION = (
        "requires_travel",
        "NORMAL_TP",
        True,
        1.0,
    )
    LIQUIDITY_SWEEP_REVERSAL = (
        "requires_reclaim",
        "NORMAL_TP",
        False,
        0.75,
    )
    LIQUIDITY_SWEEP_CONTINUATION = (
        "requires_impulse",
        "NORMAL_TP",
        False,
        0.50,
    )
    RANGE_MEAN_REVERSION = (
        "requires_travel",
        "FAST_TP",
        False,
        0.50,
    )
    SESSION_BREAKOUT = (
        "requires_hold",
        "EXPANSION_TP",
        True,
        1.0,
    )
    EXHAUSTION_REVERSAL = (
        "requires_reclaim",
        "FAST_TP",
        False,
        0.50,
    )
    CHOPPY_FRAGILE_SETUP = (
        "fragile",
        "FAST_TP",
        False,
        0.25,
    )
    UNKNOWN = (
        "skip",
        "FAST_TP",
        False,
        0.0,
    )


@dataclass(frozen=True)
class TradePersonality:
    kind: TradePersonalityKind
    label: str
    requires_travel: bool = True
    default_tp_mode: TPMode = "NORMAL_TP"
    runner_default: bool = False
    base_size_cap: float = 1.0
    notes: str = ""


@dataclass(frozen=True)
class TradeReadinessAssessment:
    state: ReadinessState
    projected_reward_r: float = 0.0
    thesis_confidence: float = 0.0
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class DynamicExitPlan:
    stagnation_bars_limit: int = STAGNATION_BARS_M5
    min_progress_r: float = 0.20
    spread_exit_multiple: float = 1.5
    enable_early_exit: bool = True
    enable_stagnation_exit: bool = True


@dataclass(frozen=True)
class IndividualTradePlan:
    personality: TradePersonality
    readiness: TradeReadinessAssessment
    tp_mode: TPMode
    tp1_r: float
    tp2_r: float
    runner_allowed: bool
    size_multiplier: float
    grade: TradeGrade
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    realistic_r_available: float
    exit_plan: DynamicExitPlan
    entry_allowed: bool
    summary: str = ""


@dataclass
class IndividualTradeTracker:
    """Runtime stats for reporting."""

    evaluated: int = 0
    ready_now: int = 0
    skip_weak: int = 0
    early_exits: int = 0
    full_stops_avoided: int = 0
    personality_counts: dict[str, int] = field(default_factory=dict)
    tp_mode_counts: dict[str, int] = field(default_factory=dict)
    grade_counts: dict[str, int] = field(default_factory=dict)

    def record(self, plan: IndividualTradePlan) -> None:
        self.evaluated += 1
        if plan.readiness.state == "READY_NOW":
            self.ready_now += 1
        else:
            self.skip_weak += 1
        self.personality_counts[plan.personality.kind] = (
            self.personality_counts.get(plan.personality.kind, 0) + 1
        )
        self.tp_mode_counts[plan.tp_mode] = self.tp_mode_counts.get(plan.tp_mode, 0) + 1
        self.grade_counts[plan.grade] = self.grade_counts.get(plan.grade, 0) + 1

    def record_early_exit(self) -> None:
        self.early_exits += 1

    def summary(self) -> dict:
        return {
            "evaluated": self.evaluated,
            "ready_now": self.ready_now,
            "skip_weak": self.skip_weak,
            "early_exits": self.early_exits,
            "personality_counts": dict(self.personality_counts),
            "tp_mode_counts": dict(self.tp_mode_counts),
            "grade_counts": dict(self.grade_counts),
        }


_tracker = IndividualTradeTracker()
_tracker_lock = Lock()


def get_individual_trade_tracker() -> IndividualTradeTracker:
    return _tracker


def reset_individual_trade_tracker() -> IndividualTradeTracker:
    global _tracker
    with _tracker_lock:
        _tracker = IndividualTradeTracker()
    return _tracker


PERSONALITY_PROFILES: dict[TradePersonalityKind, TradePersonality] = {
    "TREND_CONTINUATION": TradePersonality(
        kind="TREND_CONTINUATION",
        label="Trend continuation",
        requires_travel=False,
        default_tp_mode="NORMAL_TP",
        runner_default=True,
        base_size_cap=1.0,
    ),
    "LIQUIDITY_SWEEP_REVERSAL": TradePersonality(
        kind="LIQUIDITY_SWEEP_REVERSAL",
        label="Liquidity sweep reversal",
        requires_travel=False,
        default_tp_mode="NORMAL_TP",
        runner_default=False,
        base_size_cap=0.75,
        notes="Requires reclaim of swept level",
    ),
    "LIQUIDITY_SWEEP_CONTINUATION": TradePersonality(
        kind="LIQUIDITY_SWEEP_CONTINUATION",
        label="Liquidity sweep continuation",
        requires_travel=False,
        default_tp_mode="NORMAL_TP",
        runner_default=False,
        base_size_cap=0.50,
        notes="Requires post-sweep impulse — not sweep alone",
    ),
    "RANGE_MEAN_REVERSION": TradePersonality(
        kind="RANGE_MEAN_REVERSION",
        label="Range mean reversion",
        requires_travel=False,
        default_tp_mode="FAST_TP",
        runner_default=False,
        base_size_cap=0.50,
    ),
    "SESSION_BREAKOUT": TradePersonality(
        kind="SESSION_BREAKOUT",
        label="Session breakout",
        requires_travel=False,
        default_tp_mode="EXPANSION_TP",
        runner_default=True,
        base_size_cap=1.0,
    ),
    "EXHAUSTION_REVERSAL": TradePersonality(
        kind="EXHAUSTION_REVERSAL",
        label="Exhaustion reversal",
        requires_travel=False,
        default_tp_mode="FAST_TP",
        runner_default=False,
        base_size_cap=0.50,
    ),
    "CHOPPY_FRAGILE_SETUP": TradePersonality(
        kind="CHOPPY_FRAGILE_SETUP",
        label="Choppy fragile setup",
        requires_travel=False,
        default_tp_mode="FAST_TP",
        runner_default=False,
        base_size_cap=0.25,
    ),
    "UNKNOWN": TradePersonality(
        kind="UNKNOWN",
        label="Unknown",
        requires_travel=False,
        default_tp_mode="FAST_TP",
        runner_default=False,
        base_size_cap=0.0,
    ),
}


class TradePersonalityClassifier:
    """Map story/regime context to trade personality."""

    @staticmethod
    def classify(
        *,
        opportunity_type: str | None,
        regime_label: str,
        story_clear: bool,
        structure_trend: str,
        bias: str,
    ) -> TradePersonality:
        opp = (opportunity_type or "").strip().lower()

        if regime_label == "ranging" and not story_clear:
            return PERSONALITY_PROFILES["CHOPPY_FRAGILE_SETUP"]

        if "breakout" in opp or "breakout_retest" in opp:
            return PERSONALITY_PROFILES["SESSION_BREAKOUT"]
        if "mean_reversion" in opp or "snapback" in opp:
            return PERSONALITY_PROFILES["RANGE_MEAN_REVERSION"]
        if "exhaustion" in opp:
            return PERSONALITY_PROFILES["EXHAUSTION_REVERSAL"]
        if "pullback_continuation" in opp or "trend_pause" in opp:
            return PERSONALITY_PROFILES["TREND_CONTINUATION"]
        if "liquidity_sweep" in opp or "sweep" in opp:
            if structure_trend == bias and structure_trend in {"bullish", "bearish"}:
                return PERSONALITY_PROFILES["LIQUIDITY_SWEEP_CONTINUATION"]
            return PERSONALITY_PROFILES["LIQUIDITY_SWEEP_REVERSAL"]
        if regime_label == "ranging":
            return PERSONALITY_PROFILES["RANGE_MEAN_REVERSION"]
        if regime_label == "trending" and structure_trend in {"bullish", "bearish"}:
            return PERSONALITY_PROFILES["TREND_CONTINUATION"]
        if not story_clear:
            return PERSONALITY_PROFILES["UNKNOWN"]
        if regime_label in {"volatile", "transitional"}:
            return PERSONALITY_PROFILES["CHOPPY_FRAGILE_SETUP"]
        return PERSONALITY_PROFILES["LIQUIDITY_SWEEP_REVERSAL"]


class ThesisProjectionEngine:
    """Story thesis projects entry, stop, and target — discretionary trader planning."""

    @staticmethod
    def assess(
        *,
        side: str,
        entry_price: float,
        stop_loss: float,
        target_liquidity: float,
        personality: TradePersonality,
        story_clear: bool,
        thesis_confidence: float,
        thesis_reward_risk: float,
        spread_pips: float,
        spread_limit: float,
    ) -> TradeReadinessAssessment:
        risk = abs(entry_price - stop_loss)
        if risk <= 0:
            return TradeReadinessAssessment(
                state="SKIP_WEAK_OPPORTUNITY",
                reasons=("Invalid stop geometry — thesis cannot project levels",),
            )

        if personality.kind == "UNKNOWN":
            return TradeReadinessAssessment(
                state="SKIP_WEAK_OPPORTUNITY",
                reasons=("Unknown personality — observe only",),
            )

        if not story_clear:
            return TradeReadinessAssessment(
                state="SKIP_WEAK_OPPORTUNITY",
                reasons=("Story not clear — thesis cannot project entry",),
            )

        if spread_pips > spread_limit:
            return TradeReadinessAssessment(
                state="SKIP_WEAK_OPPORTUNITY",
                reasons=(f"Spread {spread_pips:.1f}p exceeds limit {spread_limit:.1f}p",),
            )

        projected_r = abs(target_liquidity - entry_price) / risk
        if thesis_reward_risk < 0.35 or projected_r < 0.35:
            return TradeReadinessAssessment(
                state="SKIP_WEAK_OPPORTUNITY",
                projected_reward_r=projected_r,
                thesis_confidence=thesis_confidence,
                reasons=(
                    f"Weak thesis reward ({thesis_reward_risk:.2f}R net, "
                    f"{projected_r:.2f}R gross)",
                ),
            )

        return TradeReadinessAssessment(
            state="READY_NOW",
            projected_reward_r=round(projected_r, 3),
            thesis_confidence=thesis_confidence,
            reasons=(
                f"Thesis entry {entry_price:.5f} | stop {stop_loss:.5f} | "
                f"target {target_liquidity:.5f}",
                f"Projected {projected_r:.2f}R | confidence {thesis_confidence:.0f}%",
            ),
        )


class IndividualTPEngine:
    """Trade-specific TP geometry from available reward."""

    @staticmethod
    def compute(
        *,
        side: str,
        entry_price: float,
        stop_loss: float,
        target_liquidity: float,
        tp_mode: TPMode,
        personality: TradePersonality,
        runner_default: bool,
        pip_size: float,
        spread_pips: float,
        candles_m5: pd.DataFrame | None,
    ) -> tuple[float, float, float, bool, float]:
        risk = abs(entry_price - stop_loss)
        if risk <= 0:
            return 0.75, 1.0, entry_price, False, 0.0

        reward_dist = abs(target_liquidity - entry_price)
        realistic_r = max(0.0, (reward_dist / risk) - (spread_pips * pip_size / risk))

        avg_vol = IndividualTPEngine._recent_volatility_r(candles_m5, risk)
        vol_adj = min(realistic_r, max(avg_vol, realistic_r * 0.85))

        if tp_mode == "FAST_TP":
            tp1_r = min(0.90, max(0.60, vol_adj * 0.85))
            tp2_r = min(1.10, tp1_r + 0.15)
            runner = False
        elif tp_mode == "EXPANSION_TP":
            tp1_r = min(1.50, max(1.25, vol_adj * 0.95))
            tp2_r = min(2.50, max(tp1_r + 0.35, realistic_r))
            runner = runner_default and realistic_r >= 1.0
        else:
            tp1_r = min(1.25, max(1.00, vol_adj * 0.90))
            tp2_r = min(2.0, max(tp1_r + 0.25, realistic_r))
            runner = runner_default and realistic_r >= 0.90

        if realistic_r < MIN_REALISTIC_R_FOR_NORMAL and tp_mode != "FAST_TP":
            tp1_r = min(tp1_r, max(0.60, realistic_r * 0.95))
            runner = False

        if personality.kind in {"RANGE_MEAN_REVERSION", "EXHAUSTION_REVERSAL", "CHOPPY_FRAGILE_SETUP"}:
            runner = False

        if side == "buy":
            tp1 = entry_price + risk * tp1_r
            tp2 = entry_price + risk * tp2_r
        else:
            tp1 = entry_price - risk * tp1_r
            tp2 = entry_price - risk * tp2_r

        return round(tp1_r, 3), round(tp2_r, 3), tp1, tp2, runner, round(realistic_r, 3)

    @staticmethod
    def _recent_volatility_r(candles_m5: pd.DataFrame | None, risk: float) -> float:
        if candles_m5 is None or len(candles_m5) < 12 or risk <= 0:
            return 1.0
        tail = candles_m5.tail(12)
        ranges = (tail["high"] - tail["low"]).astype(float)
        avg = float(ranges.mean())
        return max(0.5, min(2.0, avg / risk))


@dataclass(frozen=True)
class DynamicExitEvaluation:
    decision: ExitDecision
    new_stop: float | None = None
    reason: str = ""


class DynamicExitEngine:
    """Three-phase lifecycle — thesis invalidation, then ATR regret trails."""

    @staticmethod
    def evaluate_open_position(
        *,
        side: str,
        entry_price: float,
        stop_loss: float,
        current_price: float,
        bars_since_entry: int,
        partial_taken: bool,
        spread_pips: float,
        spread_limit: float,
        exit_plan: DynamicExitPlan,
        structure_against: bool = False,
        candles: pd.DataFrame | None = None,
        best_price: float | None = None,
        tp2_taken: bool = False,
        invalidation_level: float | None = None,
        structure: MarketContext | None = None,
        candles_m15: pd.DataFrame | None = None,
    ) -> DynamicExitEvaluation:
        from execution.atr_timing_engine import should_exit
        from intelligence.thesis_trade_management import (
            check_thesis_invalidation,
            resolve_exit_phase,
        )

        exit_phase = resolve_exit_phase(
            partial_taken=partial_taken,
            tp2_taken=tp2_taken,
        )

        if spread_pips > spread_limit * exit_plan.spread_exit_multiple:
            return DynamicExitEvaluation(decision="EXIT_EARLY", reason="spread blowout")

        if exit_phase == "thesis_protection":
            if invalidation_level is not None and invalidation_level > 0:
                invalidated, reason = check_thesis_invalidation(
                    side=side,
                    current_price=current_price,
                    invalidation_level=invalidation_level,
                    structure=structure,
                    candles_m15=candles_m15,
                )
                if invalidated:
                    return DynamicExitEvaluation(
                        decision="EXIT_EARLY",
                        reason=f"thesis invalidation: {reason}",
                    )
            return DynamicExitEvaluation(
                decision="HOLD",
                reason="thesis protection — hold for invalidation or TP1",
            )

        if not exit_plan.enable_early_exit:
            return DynamicExitEvaluation(decision="HOLD")

        best = best_price if best_price is not None else current_price
        result = should_exit(
            side=side,
            entry_price=entry_price,
            current_price=current_price,
            stop_loss=stop_loss,
            candles=candles,
            bars_since_entry=bars_since_entry,
            best_price=best,
            partial_taken=partial_taken,
            exit_phase=exit_phase,
        )
        if result.action == "EXIT":
            return DynamicExitEvaluation(decision="EXIT_EARLY", reason=result.reason)
        if result.action == "TRAIL":
            return DynamicExitEvaluation(
                decision="MOVE_TO_BREAKEVEN",
                new_stop=result.new_stop,
                reason=result.reason,
            )
        return DynamicExitEvaluation(decision="HOLD", reason=result.reason)


def _progress_r(
    side: str,
    entry_price: float,
    stop_loss: float,
    current_price: float,
) -> float:
    risk = abs(entry_price - stop_loss)
    if risk <= 0:
        return 0.0
    if side == "buy":
        return (current_price - entry_price) / risk
    return (entry_price - current_price) / risk


class IndividualTradeDoctrineEngine:
    """Orchestrate personality → readiness → plan."""

    def __init__(self) -> None:
        self.classifier = TradePersonalityClassifier()
        self.projection = ThesisProjectionEngine()
        self.tp_engine = IndividualTPEngine()
        self.exit_engine = DynamicExitEngine()

    def build_plan(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        target_liquidity: float,
        opportunity_type: str | None,
        regime_label: str,
        story_clear: bool,
        structure_trend: str,
        bias_label: str,
        spread_pips: float,
        spread_limit: float,
        candles: dict[str, pd.DataFrame] | None = None,
        sweep_level: float | None = None,
        thesis_confidence: float = 50.0,
        thesis_reward_risk: float = 0.0,
        in_active_session: bool = True,
        projection_learning: object | None = None,
        conviction_assessment: object | None = None,
    ) -> IndividualTradePlan:
        from intelligence.thesis_projection_learning_engine import ThesisProjectionAdjustments

        personality = self.classifier.classify(
            opportunity_type=opportunity_type,
            regime_label=regime_label,
            story_clear=story_clear,
            structure_trend=structure_trend,
            bias=bias_label,
        )
        m5 = (candles or {}).get("M5")
        pip_size = pip_size_for_symbol(symbol)

        readiness = self.projection.assess(
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_liquidity=target_liquidity,
            personality=personality,
            story_clear=story_clear,
            thesis_confidence=thesis_confidence,
            thesis_reward_risk=thesis_reward_risk,
            spread_pips=spread_pips,
            spread_limit=spread_limit,
        )

        learning_adj = ThesisProjectionAdjustments()
        if projection_learning is not None and hasattr(projection_learning, "get_adjustments"):
            learning_adj = projection_learning.get_adjustments(
                personality=personality.kind,
                side=side,
                in_active_session=in_active_session,
            )

        tp_mode = personality.default_tp_mode
        if personality.kind == "CHOPPY_FRAGILE_SETUP":
            tp_mode = "FAST_TP"

        tp1_r, tp2_r, tp1, tp2, runner_allowed, realistic_r = self.tp_engine.compute(
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_liquidity=target_liquidity,
            tp_mode=tp_mode,
            personality=personality,
            runner_default=personality.runner_default,
            pip_size=pip_size,
            spread_pips=spread_pips,
            candles_m5=m5,
        )

        tp1_r = round(min(tp2_r, tp1_r * learning_adj.tp1_r_multiplier), 3)
        risk = abs(entry_price - stop_loss)
        if risk > 0:
            if side == "buy":
                tp1 = entry_price + risk * tp1_r
            else:
                tp1 = entry_price - risk * tp1_r

        grade, size_mult = self._grade_and_size(
            personality=personality,
            readiness=readiness,
            story_clear=story_clear,
            realistic_r=realistic_r,
            tp_mode=tp_mode,
            thesis_confidence=thesis_confidence,
        )

        if readiness.state == "SKIP_WEAK_OPPORTUNITY" or grade == "D":
            entry_allowed = False
        elif realistic_r < 0.35:
            grade = "D"
            size_mult = 0.0
            entry_allowed = False
        else:
            entry_allowed = grade in {"A+", "B", "C"} and size_mult > 0
            size_mult = max(
                0.10,
                min(1.0, size_mult + learning_adj.size_multiplier_delta),
            )

        timing_note = ""
        conviction_note = ""
        if conviction_assessment is not None:
            from strategies.conviction_engine import ConvictionAssessment

            if isinstance(conviction_assessment, ConvictionAssessment):
                conviction_note = (
                    f" | conviction={conviction_assessment.conviction_score:.0f}"
                    f" ({conviction_assessment.participation_mode})"
                )
                if conviction_assessment.participation_mode == "avoid" and not conviction_assessment.anti_paralysis_override:
                    entry_allowed = False
                    grade = "D"
                    size_mult = 0.0
                else:
                    size_mult = min(size_mult, conviction_assessment.size_multiplier)
                    if conviction_assessment.participation_mode in {"probe", "watchlist"}:
                        size_mult = min(size_mult, conviction_assessment.size_multiplier)
                    entry_allowed = entry_allowed and size_mult > 0
        elif entry_allowed and m5 is not None and len(m5) >= 8:
            from execution.atr_timing_engine import should_enter

            timing = should_enter(side=side, candles=m5)
            if not timing.allowed:
                entry_allowed = False
                timing_note = f" | timing wait: {timing.reason}"
            else:
                timing_note = f" | timing OK ({timing.trigger})"

        exit_plan = DynamicExitPlan(
            enable_early_exit=True,
        )

        summary = (
            f"{personality.label} | {readiness.state} | {tp_mode} TP1={tp1_r:.2f}R "
            f"| grade={grade} size={size_mult:.0%} | {', '.join(readiness.reasons[:2])}"
            f"{conviction_note}{timing_note}"
        )

        plan = IndividualTradePlan(
            personality=personality,
            readiness=readiness,
            tp_mode=tp_mode,
            tp1_r=tp1_r,
            tp2_r=tp2_r,
            runner_allowed=runner_allowed,
            size_multiplier=size_mult,
            grade=grade,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            realistic_r_available=realistic_r,
            exit_plan=exit_plan,
            entry_allowed=entry_allowed,
            summary=summary,
        )
        get_individual_trade_tracker().record(plan)
        return plan

    @staticmethod
    def _grade_and_size(
        *,
        personality: TradePersonality,
        readiness: TradeReadinessAssessment,
        story_clear: bool,
        realistic_r: float,
        tp_mode: TPMode,
        thesis_confidence: float = 0.0,
    ) -> tuple[TradeGrade, float]:
        if personality.kind == "UNKNOWN":
            return "D", 0.0
        if readiness.state == "SKIP_WEAK_OPPORTUNITY":
            return "D", 0.0
        if not story_clear:
            return "D", 0.0

        cap = personality.base_size_cap

        if (
            thesis_confidence >= 70
            and realistic_r >= 1.0
            and readiness.projected_reward_r >= STRONG_REWARD_R
        ):
            return "A+", min(1.0, cap)

        if thesis_confidence >= 55 and realistic_r >= 0.70:
            return "B", min(0.75, cap)

        if realistic_r >= 0.50:
            return "C", min(0.50, cap)

        if personality.kind == "CHOPPY_FRAGILE_SETUP":
            return "C", 0.25

        return "D", 0.0


__all__ = [
    "DynamicExitEngine",
    "DynamicExitEvaluation",
    "DynamicExitPlan",
    "ExitDecision",
    "IndividualTPEngine",
    "IndividualTradeDoctrineEngine",
    "IndividualTradePlan",
    "IndividualTradeTracker",
    "ThesisProjectionEngine",
    "TradePersonality",
    "TradePersonalityClassifier",
    "TradePersonalityKind",
    "TradeReadinessAssessment",
    "TPMode",
    "get_individual_trade_tracker",
    "reset_individual_trade_tracker",
]
