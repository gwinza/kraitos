"""Market Storyteller Engine — V4 orchestrator: STORY → PICTURE → THESIS → STRATEGY."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from council.chief_intelligence_officer import ChiefIntelligenceOfficer
from council.cognitive_brain import CognitiveBrain
from council.cognitive_context import MarketCognitiveContext
from council.cognitive_models import CIODecision, HardVeto
from intelligence.harvest_opportunity_score import infer_session
from intelligence.narrator_engine import NarratorEngine
from intelligence.picture_fusion_engine import PictureFusionEngine
from intelligence.market_mind_tuning import (
    blended_confidence,
    participation_from_confidence,
    thesis_is_clear,
)
from intelligence.picture_models import (
    DepartmentContribution,
    LiveMarketStory,
    ParticipationMode,
    StorytellerDecision,
    StoryTradeThesis,
)
from intelligence.strategy_playbook import PROFESSIONAL_STRATEGY_PLAYBOOK
from intelligence.strategy_selection_engine import StrategySelectionEngine

if TYPE_CHECKING:
    from brains.models import TradeCandidate


class LiveStoryEngine:
    """Build continuous live market story from existing intelligence."""

    def build(self, candidate: TradeCandidate) -> LiveMarketStory:
        symbol = candidate.symbol
        what = "Price action is being assessed across timeframes."
        why = "Causal drivers are still forming."
        who = "Control is undetermined."
        trapped = "No clear trapped cohort identified."
        liquidity = "Liquidity location not yet mapped."
        objective = "Market objective unclear."
        next_chapter = "Awaiting next structural development."
        narrative = ""
        confidence = 40.0

        story = candidate.market_story
        brain = candidate.brain_story
        synthesis = getattr(story, "synthesis", None) if story is not None else None

        if synthesis is not None:
            what = getattr(synthesis, "current_explanation", what)
            confidence = float(getattr(synthesis, "confidence", confidence) or confidence)
            next_chapter = getattr(synthesis, "probable_next_event", next_chapter)
            narrative = what
            if getattr(synthesis, "dominant_direction", "neutral") != "neutral":
                who = f"{synthesis.dominant_direction} side has narrative edge"
        elif story is not None:
            what = getattr(story, "primary_story", what)
            narrative = what
            confidence = float(getattr(story, "overall_confidence", confidence) or confidence)
            direction = getattr(story, "direction", "neutral")
            if direction != "neutral":
                who = f"{direction} participants appear in control"
        elif brain is not None:
            what = getattr(brain, "narrative", what)
            narrative = what
            confidence = float(getattr(brain, "confidence", 0.5) or 0.5) * 100
            who = f"{getattr(brain, 'direction', 'neutral')} bias from structure-first read"

        if candidate.story_forecast is not None:
            sf = candidate.story_forecast
            next_chapter = getattr(sf, "expected_next_move", next_chapter)
            opp = getattr(sf, "opportunity_type", None)
            if opp:
                objective = f"Exploit {opp} opportunity"
        if candidate.structure is not None:
            liquidity = (
                f"Structure {candidate.structure.trend} with "
                f"{len(candidate.structure.liquidity_zones)} liquidity zones mapped"
            )
        if candidate.range_intelligence is not None:
            rng = candidate.range_intelligence
            liquidity = (
                f"Range support {getattr(rng, 'support_level', 0):.5f}, "
                f"resistance {getattr(rng, 'resistance_level', 0):.5f}"
            )
        if "sweep" in narrative.lower() or "liquidity" in narrative.lower():
            trapped = "Late counter-trend participants may be trapped after the sweep"
            why = "Stop hunt and reclaim suggests institutional accumulation or distribution"

        if not narrative:
            narrative = (
                f"{what} {why} {who}. Liquidity: {liquidity}. "
                f"Next chapter: {next_chapter}."
            )

        return LiveMarketStory(
            symbol=symbol,
            what_is_happening=what,
            why_it_is_happening=why,
            who_is_in_control=who,
            who_is_trapped=trapped,
            liquidity_location=liquidity,
            market_objective=objective,
            next_likely_chapter=next_chapter,
            narrative=narrative[:800],
            confidence=confidence,
        )


class StrategyDepartment:
    """Strategy department — paints which professional playbook fits."""

    def analyze(self, candidate: TradeCandidate, rankings: tuple) -> DepartmentContribution:
        if not rankings:
            return DepartmentContribution(
                department="strategy",
                observation="No strategy ranked yet",
                confidence=30.0,
                uncertainty="Awaiting picture fusion",
            )
        top = rankings[0]
        second = rankings[1] if len(rankings) > 1 else None
        obs = f"{top.strategy_name}: {top.fit_score:.0f}% fit"
        implications = (top.rationale[:120],)
        if second:
            implications = (f"{top.strategy_name}: {top.fit_score:.0f}% fit", f"{second.strategy_name}: {second.fit_score:.0f}% fit")
        return DepartmentContribution(
            department="strategy",
            observation=obs,
            evidence=(top.rationale[:100],),
            confidence=min(95.0, top.fit_score),
            implications=implications,
        )


class ReviewDepartment:
    """Review department — paints historical expectancy for similar conditions."""

    def analyze(self, candidate: TradeCandidate) -> DepartmentContribution:
        archetype = candidate.archetype_check
        harvest = candidate.harvest_score
        evidence: list[str] = []
        confidence = 50.0
        if archetype is not None:
            allowed = getattr(archetype, "allowed", True)
            evidence.append(f"Archetype memory: allowed={allowed}")
            confidence = 65.0 if allowed else 35.0
        if harvest is not None:
            evidence.append(
                f"Harvest score {getattr(harvest, 'score', 0):.0f} ({getattr(harvest, 'band', '')})"
            )
            confidence = max(confidence, float(getattr(harvest, "score", 50) or 50))
        return DepartmentContribution(
            department="review",
            observation="Historical playbook memory informs current picture",
            evidence=tuple(evidence) or ("Insufficient closed-trade memory for this archetype",),
            confidence=confidence,
            implications=("Similar conditions should be compared post-trade",),
        )


class MarketStorytellerEngine:
    """
    Kraitos V4 — Market Storytelling AI.

    STORY → PICTURE → THESIS → STRATEGY → EXECUTION guidance → LEARNING hooks
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self._story_engine = LiveStoryEngine()
        self._cognitive = CognitiveBrain(project_root)
        self._fusion = PictureFusionEngine()
        self._narrator = NarratorEngine()
        self._strategy_selector = StrategySelectionEngine()
        self._strategy_dept = StrategyDepartment()
        self._review_dept = ReviewDepartment()
        self._cio = ChiefIntelligenceOfficer(self._cognitive.memory)
        self._latest: dict[str, StorytellerDecision] = {}

    def evaluate(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment=None,
        cognitive: CIODecision | None = None,
    ) -> StorytellerDecision:
        hour = evaluation_moment.hour if evaluation_moment is not None else 12
        session = infer_session(hour)
        context = MarketCognitiveContext.from_candidate(
            candidate,
            evaluation_moment=evaluation_moment,
            session_label=session,
        )

        live_story = self._story_engine.build(candidate)
        if cognitive is None:
            cognitive = self._cognitive.deliberate(candidate, evaluation_moment=evaluation_moment)

        departments = [
            PictureFusionEngine.contribution_from_council(obs)
            for obs in cognitive.council_observations
        ]
        preliminary_picture = self._fusion.fuse(
            symbol=candidate.symbol,
            departments=tuple(departments),
            regime_label=context.regime_label,
        )
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
        rejection = ""
        if hard_vetoes:
            rejection = hard_vetoes[0].reason
        elif not thesis_clear:
            if side not in {"buy", "sell"}:
                rejection = "No directional side resolved from market picture"
            else:
                rejection = picture.reason_not_clear or "Picture still forming — reduced participation"

        thesis = StoryTradeThesis(
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
            scaling_plan=scaling_plan,
            invalidation=narration.invalidation,
            confidence=confidence,
            risk_allocation=allocation,
            management_plan=cognitive.execution.timing_guidance,
            thesis_clear=thesis_clear,
            rejection_reason=rejection,
        )

        reason = cognitive.summary
        if not thesis_clear:
            reason = rejection or f"Picture {picture.clarity}: {participation}"

        decision = StorytellerDecision(
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
            hard_risk_blocked=bool(hard_vetoes),
        )
        self._latest[candidate.symbol] = decision
        return decision

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

    def latest(self, symbol: str) -> StorytellerDecision | None:
        return self._latest.get(symbol)
