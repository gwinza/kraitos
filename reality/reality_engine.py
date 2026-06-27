"""Reality Engine — V8 orchestrator: evidence → world models → elimination → convergence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from council.cognitive_brain import CognitiveBrain
from council.cognitive_context import MarketCognitiveContext
from council.cognitive_models import HardVeto
from intelligence.harvest_opportunity_score import infer_session
from intelligence.market_mind_departments import MacroDepartment, NarratorDepartment
from intelligence.market_mind_tuning import (
    blended_confidence,
    participation_from_confidence,
)
from intelligence.market_storyteller_engine import LiveStoryEngine
from intelligence.picture_fusion_engine import PictureFusionEngine
from intelligence.strategy_playbook import PROFESSIONAL_STRATEGY_PLAYBOOK
from intelligence.strategy_selection_engine import StrategySelectionEngine
from reality.division_investigator import DivisionInvestigator
from reality.elimination_engine import ConvergenceEngine, EliminationEngine
from reality.reality_efficiency import (
    DEFER_REALITY_STATE_PERSIST,
    MAX_INVESTIGATIONS_STORED,
    STRATEGY_RANK_TOP_N,
)
from reality.reality_models import RealityDecision
from reality.reality_state import RealityStateSnapshot, RealityStateStore
from reality.reality_synthesizer import RealitySynthesizer
from reality.world_model_catalog import world_models_for_event

if TYPE_CHECKING:
    from brains.models import TradeCandidate

CONVERGENCE_THESIS_MIN = 52.0
CONVERGENCE_DOMINANT_MIN = 48.0


class RealityEngine:
    """
    Kraitos V8 — The Reality Engine.

    Reconstruct market reality from evidence. Trading is expression of the
    surviving Reality Model after scientific elimination.
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
        self._strategy_selector = StrategySelectionEngine()
        self._macro_dept = MacroDepartment()
        self._narrator_dept = NarratorDepartment()
        self._investigator = DivisionInvestigator()
        self._elimination = EliminationEngine()
        self._convergence = ConvergenceEngine()
        self._synthesizer = RealitySynthesizer()
        self._state = RealityStateStore(project_root)
        self._playbook_by_id = {s.strategy_id: s for s in PROFESSIONAL_STRATEGY_PLAYBOOK}
        self._latest: dict[str, RealityDecision] = {}

    def evaluate(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment=None,
    ) -> RealityDecision:
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

        picture = self._fusion.fuse(
            symbol=candidate.symbol,
            departments=tuple(departments),
            regime_label=context.regime_label,
        )

        event_sig = f"{live_story.narrative} {picture.summary} {picture.regime}"
        direction_hint = picture.dominant_side if picture.dominant_side != "neutral" else "neutral"
        world_models = world_models_for_event(
            event_signature=event_sig,
            direction_hint=direction_hint,
        )

        investigations = self._investigator.investigate_all(
            models=world_models,
            departments=tuple(departments),
            council_observations=cognitive.council_observations,
        )
        models_after_elimination = self._elimination.eliminate(world_models, investigations)
        models_converged = self._convergence.converge(models_after_elimination)

        dom_id, conv_score, uncertainty, conv_summary = self._convergence.convergence_summary(
            models_converged
        )
        dominant = next(
            (m for m in models_converged if m.status == "dominant"),
            next((m for m in models_converged if m.model_id == dom_id), None),
        )

        convergence = self._synthesizer.build_convergence(
            models=models_converged,
            dominant_id=dom_id,
            convergence_score=conv_score,
            uncertainty=uncertainty,
            summary=conv_summary,
        )

        strategy_rankings = self._strategy_selector.rank_top(
            picture=picture,
            story=live_story,
            n=STRATEGY_RANK_TOP_N,
        )
        top_strategy = strategy_rankings[0] if strategy_rankings else None
        strategy_fit = top_strategy.fit_score if top_strategy else 0.0

        confidence = blended_confidence(
            picture_confidence=picture.confidence,
            story_confidence=live_story.confidence,
            cio_confidence=float(cognitive.thesis.confidence),
            strategy_fit=strategy_fit,
        )
        confidence = min(100.0, confidence * 0.7 + conv_score * 0.3)

        hard_vetoes = self._hard_vetoes(context)
        participation, allocation = participation_from_confidence(
            confidence,
            picture,
            hard_blocked=bool(hard_vetoes),
        )

        if conv_score >= 75 and dominant is not None and dominant.status == "dominant":
            allocation = min(1.0, allocation * 1.1)
            participation = "scale_in" if allocation >= 0.9 else participation

        narrative = self._synthesizer.synthesize_narrative(
            dominant=dominant,
            models=models_converged,
            convergence=convergence,
            market_context=live_story.narrative,
        )

        thesis_clear = (
            not hard_vetoes
            and conv_score >= CONVERGENCE_THESIS_MIN
            and dominant is not None
            and dominant.explanatory_power >= CONVERGENCE_DOMINANT_MIN
            and allocation >= 0.12
            and dominant.direction in {"bullish", "bearish"}
        )

        rejection = ""
        if hard_vetoes:
            rejection = hard_vetoes[0].reason
        elif not thesis_clear:
            if dominant is None:
                rejection = "Reality has not converged — competing models remain viable"
            elif conv_score < CONVERGENCE_THESIS_MIN:
                rejection = f"Convergence {conv_score:.0f}/100 — observe until reality clarifies"
            else:
                rejection = "Surviving reality model lacks directional expression"

        playbook = (
            self._playbook_by_id.get(top_strategy.strategy_id)
            if top_strategy is not None
            else None
        )

        thesis = self._synthesizer.build_thesis(
            symbol=candidate.symbol,
            dominant=dominant,
            convergence=convergence,
            narrative=narrative,
            selected_strategy=top_strategy.strategy_name if top_strategy else "none",
            entry_logic=top_strategy.entry_model if top_strategy else "Await reality convergence",
            stop_logic=top_strategy.stop_model if top_strategy else "N/A",
            target_logic=top_strategy.target_model if top_strategy else "N/A",
            confidence=confidence,
            allocation=allocation,
            thesis_clear=thesis_clear,
            rejection=rejection,
        )

        reason = conv_summary if thesis_clear else (rejection or conv_summary)
        change_note = self._state.evidence_change_note(
            candidate.symbol,
            new_dominant_id=dom_id,
            new_score=conv_score,
        )
        if change_note:
            reason = f"{change_note}. {reason}"

        self._state.update(
            RealityStateSnapshot(
                symbol=candidate.symbol,
                dominant_model_id=dom_id,
                dominant_model_name=convergence.dominant_model_name,
                convergence_score=conv_score,
                updated_at=(
                    evaluation_moment.isoformat()
                    if evaluation_moment is not None
                    else datetime.now(timezone.utc).isoformat()
                ),
            ),
            persist=not DEFER_REALITY_STATE_PERSIST,
        )

        stored_investigations = self._trim_investigations(investigations)

        decision = RealityDecision(
            symbol=candidate.symbol,
            world_models=models_converged,
            investigations=stored_investigations,
            convergence=convergence,
            thesis=thesis,
            participation=participation,
            allocation_multiplier=allocation,
            reason=reason,
            hard_risk_blocked=bool(hard_vetoes),
            cognitive_snapshot=self._slim_cognitive_snapshot(cognitive),
        )
        self._latest[candidate.symbol] = decision
        return decision

    def flush_state(self) -> None:
        """Persist deferred reality state after a full symbol batch."""
        self._state.flush()

    @staticmethod
    def _trim_investigations(investigations: tuple) -> tuple:
        """Keep only meaningful investigations for logs — drop inconclusive noise."""
        meaningful = [
            inv
            for inv in investigations
            if inv.strengthens or inv.weakens
        ]
        if len(meaningful) <= MAX_INVESTIGATIONS_STORED:
            return tuple(meaningful)
        meaningful.sort(key=lambda i: i.confidence, reverse=True)
        return tuple(meaningful[:MAX_INVESTIGATIONS_STORED])

    @staticmethod
    def _slim_cognitive_snapshot(cognitive) -> dict:
        """Store minimal CIO snapshot — full deliberation is expensive to serialize."""
        return {
            "symbol": cognitive.symbol,
            "summary": cognitive.summary,
            "can_trade": cognitive.can_trade,
            "thesis": {
                "side": cognitive.thesis.side,
                "confidence": cognitive.thesis.confidence,
            },
            "execution": {
                "allocation_multiplier": cognitive.execution.allocation_multiplier,
                "timing_guidance": cognitive.execution.timing_guidance,
            },
        }

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

    def latest(self, symbol: str) -> RealityDecision | None:
        return self._latest.get(symbol)

    @property
    def cognitive_brain(self) -> CognitiveBrain:
        return self._cognitive
