"""Market Mind Engine — V5 unified cognitive orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from council.cognitive_brain import CognitiveBrain
from council.cognitive_context import MarketCognitiveContext
from council.cognitive_models import CIODecision, HardVeto
from intelligence.harvest_opportunity_score import infer_session
from intelligence.market_mind_departments import MacroDepartment, NarratorDepartment
from intelligence.market_mind_models import MARKET_MIND_PHILOSOPHY, MarketMindDecision
from intelligence.market_storyteller_engine import (
    LiveStoryEngine,
    ReviewDepartment,
    StrategyDepartment,
)
from intelligence.narrator_engine import NarratorEngine
from intelligence.picture_fusion_engine import PictureFusionEngine
from intelligence.market_mind_tuning import (
    EVIDENCE_CHANGE_CONF_DELTA,
    blended_confidence,
    participation_from_confidence,
    thesis_is_clear,
)
from intelligence.picture_models import ParticipationMode
from intelligence.strategy_playbook import PROFESSIONAL_STRATEGY_PLAYBOOK
from intelligence.strategy_selection_engine import StrategySelectionEngine

if TYPE_CHECKING:
    from brains.models import TradeCandidate


class MarketMindEngine:
    """
    Kraitos V5 — The Market Mind.

    Every department observes simultaneously, communicates continuously, and
    updates confidence as evidence arrives. One coherent picture → one thesis.
    """

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        cognitive: CognitiveBrain | None = None,
    ) -> None:
        self._story_engine = LiveStoryEngine()
        self._cognitive = cognitive or CognitiveBrain(project_root)
        self._fusion = PictureFusionEngine()
        self._narrator = NarratorEngine()
        self._strategy_selector = StrategySelectionEngine()
        self._strategy_dept = StrategyDepartment()
        self._review_dept = ReviewDepartment()
        self._macro_dept = MacroDepartment()
        self._narrator_dept = NarratorDepartment()
        self._latest: dict[str, MarketMindDecision] = {}

    def evaluate(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment=None,
    ) -> MarketMindDecision:
        hour = evaluation_moment.hour if evaluation_moment is not None else 12
        session = infer_session(hour)
        context = MarketCognitiveContext.from_candidate(
            candidate,
            evaluation_moment=evaluation_moment,
            session_label=session,
        )

        live_story = self._story_engine.build(candidate)
        cognitive = self._cognitive.deliberate(candidate, evaluation_moment=evaluation_moment)

        departments = [
            PictureFusionEngine.contribution_from_council(obs)
            for obs in cognitive.council_observations
        ]
        departments.append(self._macro_dept.analyze(candidate))
        departments.append(self._narrator_dept.analyze(story=live_story))

        preliminary_picture = self._fusion.fuse(
            symbol=candidate.symbol,
            departments=tuple(departments),
            regime_label=context.regime_label,
        )

        # Narrator challenges preliminary picture — second pass updates confidence
        narrator_update = self._narrator_dept.analyze(
            story=live_story,
            picture=preliminary_picture,
        )
        departments = [d for d in departments if d.department != "narrator"]
        departments.append(narrator_update)

        strategy_rankings = self._strategy_selector.rank(
            picture=preliminary_picture,
            story=live_story,
        )
        departments.append(self._strategy_dept.analyze(candidate, strategy_rankings))
        departments.append(self._review_dept.analyze(candidate))

        picture = self._fusion.fuse(
            symbol=candidate.symbol,
            departments=tuple(departments),
            regime_label=context.regime_label,
        )
        narration = self._narrator.narrate(
            story=live_story,
            picture=picture,
            departments=tuple(departments),
        )

        evidence_changes = self._evidence_changes(preliminary_picture, picture)
        mind_state = self._mind_state(picture, evidence_changes)
        hard_vetoes = self._hard_vetoes(context)
        side = self._resolve_side(picture, cognitive.thesis.side)

        top_strategy = strategy_rankings[0] if strategy_rankings else None
        strategy_fit = top_strategy.fit_score if top_strategy else 0.0
        confidence = blended_confidence(
            picture_confidence=picture.confidence,
            story_confidence=live_story.confidence,
            cio_confidence=float(cognitive.thesis.confidence),
            strategy_fit=strategy_fit,
        )
        participation, allocation = participation_from_confidence(
            confidence,
            picture,
            hard_blocked=bool(hard_vetoes),
        )

        scaling_plan = "Observe"
        if top_strategy is not None:
            playbook = next(
                (s for s in PROFESSIONAL_STRATEGY_PLAYBOOK if s.strategy_id == top_strategy.strategy_id),
                None,
            )
            scaling_plan = playbook.scaling_rules if playbook else "Standard scaling on acceptance"

        thesis_clear = thesis_is_clear(
            picture=picture,
            side=side,
            participation=participation,
            allocation=allocation,
            strategy_fit=strategy_fit,
            hard_blocked=bool(hard_vetoes),
        )
        rejection = self._rejection_reason(hard_vetoes, picture, side, thesis_clear)

        thesis = self._build_thesis(
            candidate=candidate,
            narration=narration,
            picture=picture,
            live_story=live_story,
            top_strategy=top_strategy,
            scaling_plan=scaling_plan,
            side=side,
            confidence=confidence,
            allocation=allocation,
            cognitive=cognitive,
            thesis_clear=thesis_clear,
            rejection=rejection,
        )

        reason = cognitive.summary
        if not thesis_clear:
            reason = rejection or f"Picture {picture.clarity}: {participation}"

        decision = MarketMindDecision(
            symbol=candidate.symbol,
            story=live_story,
            picture=picture,
            narration=narration,
            strategy_rankings=strategy_rankings[:6],
            thesis=thesis,
            participation=participation,
            allocation_multiplier=allocation,
            cio_summary=cognitive.summary,
            reason=reason,
            cognitive=cognitive,
            mind_state=mind_state,
            evidence_changes=evidence_changes,
            hard_risk_blocked=bool(hard_vetoes),
        )
        self._latest[candidate.symbol] = decision
        return decision

    @staticmethod
    def _evidence_changes(before, after) -> tuple[str, ...]:
        changes: list[str] = []
        if before.clarity != after.clarity:
            changes.append(f"Picture clarity {before.clarity} → {after.clarity}")
        if before.dominant_side != after.dominant_side:
            changes.append(f"Dominant side {before.dominant_side} → {after.dominant_side}")
        if abs(before.confidence - after.confidence) >= EVIDENCE_CHANGE_CONF_DELTA:
            changes.append(
                f"Confidence {before.confidence:.0f} → {after.confidence:.0f}"
            )
        new_contradictions = set(after.contradictions) - set(before.contradictions)
        for item in list(new_contradictions)[:3]:
            changes.append(f"New tension: {item[:80]}")
        return tuple(changes)

    @staticmethod
    def _mind_state(picture, evidence_changes: tuple[str, ...]) -> str:
        if picture.clarity == "clear" and picture.coherent_story:
            return "coherent"
        if evidence_changes:
            return "updating"
        if picture.clarity == "conflicted":
            return "conflicted"
        return "forming"

    @staticmethod
    def _rejection_reason(
        hard_vetoes: tuple[HardVeto, ...],
        picture,
        side: str,
        thesis_clear: bool,
    ) -> str:
        if hard_vetoes:
            return hard_vetoes[0].reason
        if thesis_clear:
            return ""
        if side not in {"buy", "sell"}:
            return "No directional side resolved from market picture"
        if not picture.professional_thesis_supported:
            return picture.reason_not_clear or "Picture still forming — reduced participation"
        return ""

    @staticmethod
    def _build_thesis(**kwargs):
        from intelligence.picture_models import StoryTradeThesis

        candidate = kwargs["candidate"]
        narration = kwargs["narration"]
        picture = kwargs["picture"]
        live_story = kwargs["live_story"]
        top_strategy = kwargs["top_strategy"]
        side = kwargs["side"]

        return StoryTradeThesis(
            symbol=candidate.symbol,
            side=side if side in {"buy", "sell"} else "observe",
            market_story=narration.full_narration[:600],
            selected_strategy=top_strategy.strategy_name if top_strategy else "none",
            supporting_evidence=picture.supporting_evidence,
            contradictory_evidence=picture.contradictions,
            expected_path=live_story.next_likely_chapter,
            entry_logic=top_strategy.entry_model if top_strategy else "Wait for picture clarity",
            stop_logic=top_strategy.stop_model if top_strategy else "N/A",
            target_logic=top_strategy.target_model if top_strategy else "N/A",
            scaling_plan=kwargs["scaling_plan"],
            invalidation=narration.invalidation,
            confidence=kwargs["confidence"],
            risk_allocation=kwargs["allocation"],
            management_plan=kwargs["cognitive"].execution.timing_guidance,
            thesis_clear=kwargs["thesis_clear"],
            rejection_reason=kwargs["rejection"],
        )

    @staticmethod
    def _hard_vetoes(context: MarketCognitiveContext) -> tuple[HardVeto, ...]:
        vetoes: list[HardVeto] = []
        if context.spread_pips > context.spread_limit:
            vetoes.append(
                HardVeto(
                    code="spread_excessive",
                    reason=f"Spread {context.spread_pips:.1f} exceeds limit {context.spread_limit:.1f}",
                )
            )
        c = context.candidate
        if not c.pair_allowed:
            vetoes.append(HardVeto(code="pair_gated", reason="Pair trading not allowed"))
        if not c.news_allowed:
            vetoes.append(HardVeto(code="news_blackout", reason="News filter active"))
        return tuple(vetoes)

    @staticmethod
    def _resolve_side(picture, cio_side: str) -> str:
        if picture.dominant_side == "bullish":
            return "buy"
        if picture.dominant_side == "bearish":
            return "sell"
        if cio_side in {"buy", "sell"}:
            return cio_side
        return "observe"

    def latest(self, symbol: str) -> MarketMindDecision | None:
        return self._latest.get(symbol)

    @property
    def philosophy(self) -> str:
        return MARKET_MIND_PHILOSOPHY

    @property
    def cognitive_brain(self) -> CognitiveBrain:
        return self._cognitive
