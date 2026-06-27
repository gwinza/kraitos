"""Scout / commit participation — thesis is not a trade until the market accepts it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from strategies.location_quality_engine import LocationQualityResult
from strategies.market_acceptance_engine import MarketAcceptanceResult
from strategies.models import MicroScalpSignal
from strategies.timing_quality_engine import TimingQualityResult

ParticipationStage = Literal[
    "idea",
    "scout",
    "commit",
    "press",
    "scratch",
    "reduce",
    "exit",
]
ScoutOrCommit = Literal["none", "scout", "commit"]
MomentumClarity = Literal["clear", "unclear", "aligned", "opposing"]
LossClassHint = Literal[
    "bad_idea",
    "good_idea_early",
    "good_idea_poor_location",
    "good_idea_no_acceptance",
    "accepted_then_failed",
    "late_entry",
    "spread_slippage",
    "true_thesis_failure",
    "unknown",
]


@dataclass(frozen=True)
class ScoutCommitConfig:
    excellent_location: int = 72
    scout_location_floor: int = 62
    commit_acceptance_scalp: int = 58
    commit_acceptance_harvest: int = 65
    harvest_location_floor: int = 65
    harvest_trend_floor: int = 55
    scout_size_scalp: float = 0.22
    scout_size_harvest: float = 0.28
    commit_size_scalp: float = 0.85
    commit_size_harvest: float = 0.90
    press_size: float = 1.0
    unclear_momentum_scout_cap: float = 0.25
    idea_scout_cap: float = 0.18


@dataclass(frozen=True)
class ScoutCommitResult:
    participation_stage: ParticipationStage
    scout_or_commit: ScoutOrCommit
    size_multiplier: float
    momentum_clarity: MomentumClarity
    harvest_qualified: bool
    effective_setup_kind: str
    commit_threshold: int
    acceptance_required: bool
    scratch_eligible: bool
    commit_requirements: tuple[str, ...]
    press_requirements: tuple[str, ...]
    scratch_plan: str
    explanation: str
    loss_class_hint: LossClassHint = "unknown"
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "participation_stage": self.participation_stage,
            "scout_or_commit": self.scout_or_commit,
            "size_multiplier": round(self.size_multiplier, 3),
            "momentum_clarity": self.momentum_clarity,
            "harvest_qualified": self.harvest_qualified,
            "effective_setup_kind": self.effective_setup_kind,
            "commit_threshold": self.commit_threshold,
            "acceptance_required": self.acceptance_required,
            "scratch_eligible": self.scratch_eligible,
            "commit_requirements": list(self.commit_requirements),
            "press_requirements": list(self.press_requirements),
            "scratch_plan": self.scratch_plan,
            "explanation": self.explanation,
            "loss_class_hint": self.loss_class_hint,
            "evidence": list(self.evidence),
        }


class ScoutCommitEngine:
    """Grandmaster entry sequence — scout early, commit only after acceptance."""

    def __init__(self, config: ScoutCommitConfig | None = None) -> None:
        self.config = config or ScoutCommitConfig()

    def evaluate_entry(
        self,
        *,
        side: str,
        setup_kind: str,
        maturity_stage: str,
        direction_quality: int,
        location: LocationQualityResult,
        timing: TimingQualityResult,
        acceptance: MarketAcceptanceResult,
        momentum: MicroScalpSignal | None = None,
        story_clear: bool = False,
        market_phase: str = "",
        trend_quality: int = 50,
        conviction_score: float | None = None,
        maturity_score: int = 50,
        stop_pips: float = 99.0,
        spread_pips: float = 1.0,
        symbol: str = "",
    ) -> ScoutCommitResult:
        cfg = self.config
        sym = symbol.strip().upper()
        is_scalp = setup_kind == "micro_scalp"
        is_harvest = setup_kind == "harvest"
        momentum_clarity = self._momentum_clarity(side, momentum)
        commit_threshold = (
            cfg.commit_acceptance_harvest if is_harvest else cfg.commit_acceptance_scalp
        )

        harvest_ok = self._harvest_qualified(
            is_harvest=is_harvest,
            story_clear=story_clear,
            market_phase=market_phase,
            trend_quality=trend_quality,
            location_score=location.location_quality_score,
            acceptance_score=acceptance.acceptance_score,
            momentum_clarity=momentum_clarity,
            direction_quality=direction_quality,
        )
        effective_kind = setup_kind
        if is_harvest and not harvest_ok:
            effective_kind = "micro_scalp"

        clean_risk = stop_pips <= 25 or (sym == "GBPJPY" and stop_pips <= 35)
        reward_open = location.reward_window_open
        excellent_loc = location.location_quality_score >= cfg.excellent_location
        scout_loc = location.location_quality_score >= cfg.scout_location_floor
        not_rejected = not acceptance.acceptance_state.startswith("rejecting")
        not_late = not timing.entry_too_late
        acceptance_met = acceptance.acceptance_score >= commit_threshold
        direction_clear = direction_quality >= 52
        timing_ok = timing.timing_quality_score >= 52 or timing.reaction_detected
        conv = conviction_score or 50.0

        scout_justified = (
            scout_loc
            and clean_risk
            and reward_open
            and not_rejected
            and not_late
            and conv >= 46
        )
        evidence: list[str] = []
        commit_req: list[str] = []
        press_req: list[str] = [
            "trade moves as expected",
            "acceptance strengthens",
            "trend health improves",
        ]

        if not acceptance_met:
            commit_req.append(f"acceptance_score >= {commit_threshold}")
        if not direction_clear:
            commit_req.append("direction_quality clear")
        if not timing_ok:
            commit_req.append("timing quality improves")
        commit_req.append("positive expectancy after spread")

        scratch_plan = (
            f"Scratch if acceptance fails to improve within adaptive window "
            f"(threshold {commit_threshold}, current {acceptance.acceptance_score})"
        )

        if acceptance.acceptance_state.startswith("rejecting"):
            return ScoutCommitResult(
                participation_stage="exit",
                scout_or_commit="none",
                size_multiplier=0.0,
                momentum_clarity=momentum_clarity,
                harvest_qualified=harvest_ok,
                effective_setup_kind=effective_kind,
                commit_threshold=commit_threshold,
                acceptance_required=True,
                scratch_eligible=False,
                commit_requirements=tuple(commit_req),
                press_requirements=tuple(press_req),
                scratch_plan=scratch_plan,
                explanation="Market rejecting thesis — no participation",
                loss_class_hint="good_idea_no_acceptance",
                evidence=("thesis rejected at entry",),
            )

        if momentum_clarity == "unclear":
            evidence.append("momentum unclear — scout only, no normal commit")
            if not excellent_loc:
                evidence.append("location not excellent enough for unclear-momentum scout")
                return ScoutCommitResult(
                    participation_stage="idea",
                    scout_or_commit="none",
                    size_multiplier=0.12 if scout_justified else 0.0,
                    momentum_clarity=momentum_clarity,
                    harvest_qualified=harvest_ok,
                    effective_setup_kind=effective_kind,
                    commit_threshold=commit_threshold,
                    acceptance_required=True,
                    scratch_eligible=scout_justified,
                    commit_requirements=tuple(commit_req),
                    press_requirements=tuple(press_req),
                    scratch_plan=scratch_plan,
                    explanation="Unclear momentum — scout only with excellent location",
                    loss_class_hint="good_idea_early",
                    evidence=tuple(evidence),
                )
            mult = min(cfg.unclear_momentum_scout_cap, cfg.scout_size_scalp)
            return ScoutCommitResult(
                participation_stage="scout",
                scout_or_commit="scout",
                size_multiplier=mult,
                momentum_clarity=momentum_clarity,
                harvest_qualified=harvest_ok,
                effective_setup_kind=effective_kind,
                commit_threshold=commit_threshold,
                acceptance_required=True,
                scratch_eligible=True,
                commit_requirements=tuple(commit_req),
                press_requirements=tuple(press_req),
                scratch_plan=scratch_plan,
                explanation=(
                    f"Unclear momentum scout @ {mult:.0%} — acceptance must improve quickly"
                ),
                loss_class_hint="good_idea_early",
                evidence=tuple(evidence),
            )

        if maturity_stage == "ready" and acceptance_met and direction_clear and timing_ok:
            if is_harvest and harvest_ok:
                mult = cfg.commit_size_harvest if sym != "GBPJPY" else 0.70
                stage: ParticipationStage = "commit"
                if conv >= 75 and maturity_score >= 78 and location.location_quality_score >= 65:
                    stage = "press"
                    mult = min(cfg.press_size, mult + 0.10)
                evidence.append(f"acceptance {acceptance.acceptance_score} >= {commit_threshold}")
                return ScoutCommitResult(
                    participation_stage=stage,
                    scout_or_commit="commit",
                    size_multiplier=min(1.0, mult),
                    momentum_clarity=momentum_clarity,
                    harvest_qualified=True,
                    effective_setup_kind="harvest",
                    commit_threshold=commit_threshold,
                    acceptance_required=False,
                    scratch_eligible=False,
                    commit_requirements=(),
                    press_requirements=tuple(press_req),
                    scratch_plan=scratch_plan,
                    explanation=f"Harvest commit — market accepted thesis ({acceptance.acceptance_score}/100)",
                    evidence=tuple(evidence),
                )
            if is_scalp or effective_kind == "micro_scalp":
                mult = cfg.commit_size_scalp if sym != "GBPJPY" else 0.65
                return ScoutCommitResult(
                    participation_stage="commit",
                    scout_or_commit="commit",
                    size_multiplier=mult,
                    momentum_clarity=momentum_clarity,
                    harvest_qualified=harvest_ok,
                    effective_setup_kind=effective_kind,
                    commit_threshold=commit_threshold,
                    acceptance_required=False,
                    scratch_eligible=False,
                    commit_requirements=(),
                    press_requirements=tuple(press_req),
                    scratch_plan=scratch_plan,
                    explanation=f"Scalp commit — acceptance confirmed ({acceptance.acceptance_score}/100)",
                    evidence=(f"acceptance {acceptance.acceptance_score}",),
                )

        if maturity_stage in {"ready", "developing", "idea"} and scout_justified:
            base = cfg.scout_size_scalp if is_scalp or effective_kind == "micro_scalp" else cfg.scout_size_harvest
            if maturity_stage == "idea":
                base = min(base, cfg.idea_scout_cap)
            elif maturity_stage == "developing":
                base = min(base, 0.32)
            if sym == "GBPJPY":
                base = min(base, 0.28)
            if maturity_stage == "ready" and not acceptance_met:
                evidence.append(
                    f"maturity ready but acceptance {acceptance.acceptance_score} < {commit_threshold} — scout not commit"
                )
            return ScoutCommitResult(
                participation_stage="scout",
                scout_or_commit="scout",
                size_multiplier=base,
                momentum_clarity=momentum_clarity,
                harvest_qualified=harvest_ok,
                effective_setup_kind=effective_kind,
                commit_threshold=commit_threshold,
                acceptance_required=True,
                scratch_eligible=True,
                commit_requirements=tuple(commit_req),
                press_requirements=tuple(press_req),
                scratch_plan=scratch_plan,
                explanation=(
                    f"Scout @ {base:.0%} — stalking thesis until acceptance "
                    f"({acceptance.acceptance_score}/{commit_threshold})"
                ),
                loss_class_hint="good_idea_early" if not acceptance_met else "unknown",
                evidence=tuple(evidence) or ("scout justified by location and clean risk",),
            )

        mult = 0.12 if conv >= 46 and scout_loc else 0.0
        return ScoutCommitResult(
            participation_stage="idea",
            scout_or_commit="scout" if mult > 0 else "none",
            size_multiplier=mult,
            momentum_clarity=momentum_clarity,
            harvest_qualified=harvest_ok,
            effective_setup_kind=effective_kind,
            commit_threshold=commit_threshold,
            acceptance_required=True,
            scratch_eligible=mult > 0,
            commit_requirements=tuple(commit_req),
            press_requirements=tuple(press_req),
            scratch_plan=scratch_plan,
            explanation="Idea stage — minimal scout only when location supports stalking",
            loss_class_hint="bad_idea" if mult == 0 else "good_idea_early",
            evidence=("insufficient scout justification",) if mult == 0 else ("minimal idea scout",),
        )

    @staticmethod
    def _momentum_clarity(side: str, momentum: MicroScalpSignal | None) -> MomentumClarity:
        if momentum is None:
            return "unclear"
        action = str(getattr(momentum, "action", "no_trade") or "no_trade")
        if action in {"", "no_trade", "wait", "none"}:
            return "unclear"
        if side == "buy" and action == "buy":
            return "aligned"
        if side == "sell" and action == "sell":
            return "aligned"
        if action in {"buy", "sell"}:
            return "opposing"
        return "unclear"

    def _harvest_qualified(
        self,
        *,
        is_harvest: bool,
        story_clear: bool,
        market_phase: str,
        trend_quality: int,
        location_score: int,
        acceptance_score: int,
        momentum_clarity: MomentumClarity,
        direction_quality: int,
    ) -> bool:
        if not is_harvest:
            return True
        phase = str(market_phase or "").lower()
        if phase in {"unclear", "unknown", ""}:
            return False
        if not story_clear and direction_quality < 58:
            return False
        if trend_quality < self.config.harvest_trend_floor:
            return False
        if location_score < self.config.harvest_location_floor:
            return False
        if acceptance_score < self.config.commit_acceptance_harvest:
            return False
        if momentum_clarity == "unclear":
            return False
        return True


__all__ = [
    "LossClassHint",
    "MomentumClarity",
    "ParticipationStage",
    "ScoutCommitConfig",
    "ScoutCommitEngine",
    "ScoutCommitResult",
    "ScoutOrCommit",
]
