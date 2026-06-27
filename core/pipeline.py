"""Integrated analysis pipeline for Kraitos.

Expectancy doctrine pipeline (TraderBrain):
  1. Market Story Engine — narrative from structure and liquidity
  2. Patience Engine — wait for professional entry locations
  3. Conviction Position Sizing — risk scales with evidence quality
  4. Trade Execution — entry engine and risk approval
  5. Adaptive Exit Engine — manage_exits step
  6. Pair Personality Memory — updated on trade close
  7. Trade Review Brain — mentor review on trade close

Kraitos optimises for expected value, profit factor, average R, equity growth,
and drawdown control — not win rate, trade count, or indicator agreement.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd

from config.settings import KraitosConfig
from core.pipeline_models import PipelineResult
from core.risk_controller import RiskController
from execution.entry_engine import EntryEngine
from strategies.harvest_engine import HarvestEngine
from strategies.market_structure import MarketStructureAnalyzer
from strategies.micro_scalper import MicroScalper
from strategies.multitimeframe_bias import MultiTimeframeBiasAnalyzer
from strategies.news_filter import NewsFilter
from strategies.regime_detector import RegimeDetector

from council.opportunity_acceptance_log import AcceptedOpportunity, OpportunityAcceptanceLog
from council.opportunity_hunter_council import CouncilExpansionConfig, OpportunityHunterCouncil
from intelligence.forecast_feedback import ForecastFeedbackStore
from intelligence.market_story_engine import MarketStoryEngine
from intelligence.story_evolution_engine import StoryEvolutionEngine
from intelligence.story_forecast_engine import StoryForecastEngine
from brains.models import TraderContext
from brains.trader_brain import TraderBrain

if TYPE_CHECKING:
    from analytics.pair_specialisation import PairSpecialisationAnalyzer
    from intelligence.opportunity_allocator import OpportunityAllocator
    from portfolio.portfolio_construction import PortfolioConstructionEngine
    from pathlib import Path


class TradingPipeline:
    """Run the full Kraitos analysis chain for a single symbol.

    Opportunity discovery is delegated to TraderBrain.
    Conservative execution and validation gates are auditor-only.
    """

    def __init__(
        self,
        *,
        config: KraitosConfig,
        regime_detector: RegimeDetector,
        bias_analyzer: MultiTimeframeBiasAnalyzer,
        structure_analyzer: MarketStructureAnalyzer,
        harvest_engine: HarvestEngine,
        micro_scalper: MicroScalper,
        entry_engine: EntryEngine,
        risk_controller: RiskController,
        news_filter: NewsFilter,
        pair_analyzer: PairSpecialisationAnalyzer,
        project_root: Path,
        strategy_quality_gate: object | None = None,
        opportunity_allocator: OpportunityAllocator | None = None,
        portfolio_engine: PortfolioConstructionEngine | None = None,
        story_engine: MarketStoryEngine | None = None,
        evolution_engine: StoryEvolutionEngine | None = None,
        forecast_engine: StoryForecastEngine | None = None,
        council: OpportunityHunterCouncil | None = None,
        forecast_feedback: ForecastFeedbackStore | None = None,
        trader_brain: TraderBrain | None = None,
    ) -> None:
        self._config = config
        self._project_root = project_root
        self._acceptance_log = (
            OpportunityAcceptanceLog(project_root) if project_root else None
        )
        self._forecast_feedback = forecast_feedback or (
            ForecastFeedbackStore(project_root) if project_root else None
        )
        self._trader_brain = trader_brain or TraderBrain(
            config=config,
            regime_detector=regime_detector,
            bias_analyzer=bias_analyzer,
            structure_analyzer=structure_analyzer,
            harvest_engine=harvest_engine,
            micro_scalper=micro_scalper,
            entry_engine=entry_engine,
            risk_controller=risk_controller,
            news_filter=news_filter,
            pair_analyzer=pair_analyzer,
            project_root=project_root,
            opportunity_allocator=opportunity_allocator,
            portfolio_engine=portfolio_engine,
            story_engine=story_engine,
            evolution_engine=evolution_engine,
            forecast_engine=forecast_engine,
            council=council,
            forecast_feedback=self._forecast_feedback,
        )
        self._allocator = opportunity_allocator
        self._story_engine = story_engine or (
            MarketStoryEngine(project_root) if project_root else None
        )
        self._evolution_engine = evolution_engine or (
            StoryEvolutionEngine(project_root) if project_root else None
        )
        self._forecast_engine = forecast_engine or (
            StoryForecastEngine(project_root) if project_root else None
        )
        expansion = CouncilExpansionConfig(
            enabled=config.pipeline.council_expansion_mode,
        )
        self._council = council or (
            OpportunityHunterCouncil(project_root, expansion_config=expansion)
            if project_root
            else None
        )

    @property
    def trader_brain(self) -> TraderBrain:
        return self._trader_brain

    def run(
        self,
        *,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        bid: float,
        ask: float,
        spread_pips: float,
        trace_id: str,
        evaluation_moment: datetime | None = None,
    ) -> list[PipelineResult]:
        """Execute every pipeline stage and return all valid trade candidates."""
        from core.helpers import resolve_spread_limit

        context = TraderContext(
            symbol=symbol,
            candles=candles,
            bid=bid,
            ask=ask,
            spread_pips=spread_pips,
            spread_limit=resolve_spread_limit(self._config, symbol),
            trace_id=trace_id,
            evaluation_moment=evaluation_moment,
        )
        from portfolio.unlimited_opportunity_tracker import get_unlimited_opportunity_tracker

        candidates = self._trader_brain.evaluate_all(context)
        results = [self._candidate_to_result(candidate) for candidate in candidates]
        moment_key = (
            evaluation_moment.isoformat() if evaluation_moment else trace_id
        )
        get_unlimited_opportunity_tracker().record_candidates(
            moment_key=moment_key,
            candidates=candidates,
        )

        for candidate, result in zip(candidates, results):
            if candidate.trade_intent:
                self._register_forecast(result, trace_id=result.trace_id)
                self._log_accepted_opportunity(
                    result,
                    trace_id=result.trace_id,
                    evaluation_moment=evaluation_moment,
                )
                self._register_trader_memory(result, trace_id=result.trace_id)
        return results

    @staticmethod
    def _candidate_to_result(candidate: object) -> PipelineResult:
        from brains.models import TradeCandidate

        assert isinstance(candidate, TradeCandidate)
        return PipelineResult(
            symbol=candidate.symbol,
            trace_id=candidate.trace_id,
            opportunity_key=candidate.opportunity_key,
            setup_kind=candidate.setup_kind,
            bid=candidate.bid,
            ask=candidate.ask,
            spread_pips=candidate.spread_pips,
            spread_limit=candidate.spread_limit,
            candles=candidate.candles,
            regime=candidate.regime,
            bias=candidate.bias,
            structure=candidate.structure,
            harvest=candidate.harvest,
            micro_scalp=candidate.micro_scalp,
            entry=candidate.entry,
            risk=candidate.risk,
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            take_profit=candidate.take_profit,
            pair_allowed=candidate.pair_allowed,
            news_allowed=candidate.news_allowed,
            asset_trend=candidate.asset_trend,
            strategy_selection=candidate.strategy_selection,
            opportunity_allocation=candidate.opportunity_allocation,
            harvest_score=candidate.harvest_score,
            archetype_check=candidate.archetype_check,
            dynamic_pip_target=candidate.dynamic_pip_target,
            portfolio_construction=candidate.portfolio_construction,
            market_story=candidate.market_story,
            story_forecast=candidate.story_forecast,
            market_narrative=candidate.market_narrative,
            narrative_forecast=candidate.narrative_forecast,
            council_consensus=candidate.council_consensus,
            indicator_confirmation=candidate.indicator_confirmation,
            thesis=candidate.thesis,
            individual_trade_plan=candidate.individual_trade_plan,
            conviction_assessment=candidate.conviction_assessment,
            opportunity_assessment=candidate.opportunity_assessment,
            decision_result=candidate.decision_result,
            execution_quality=candidate.execution_quality,
            institutional_structure=candidate.institutional_structure,
            liquidity_sweep=candidate.liquidity_sweep,
            false_breakout=candidate.false_breakout,
            market_lifecycle=candidate.market_lifecycle,
            reversal_pressure=candidate.reversal_pressure,
            session_intelligence=candidate.session_intelligence,
            news_context=candidate.news_context,
            trade_maturity=candidate.trade_maturity,
            location_quality=candidate.location_quality,
            timing_quality=candidate.timing_quality,
            market_acceptance=candidate.market_acceptance,
            market_regime_intelligence=candidate.market_regime_intelligence,
            range_intelligence=candidate.range_intelligence,
            trend_quality=candidate.trend_quality,
            scalping_intelligence=candidate.scalping_intelligence,
            brain_story=candidate.brain_story,
            patience_decision=candidate.patience_decision,
            conviction_sizing=candidate.conviction_sizing,
            cognitive_decision=candidate.cognitive_decision,
            storyteller_decision=candidate.storyteller_decision,
            market_picture=candidate.market_picture,
            market_mind_decision=candidate.market_mind_decision,
            reality_decision=candidate.reality_decision,
        )

    def _register_forecast(self, result: PipelineResult, *, trace_id: str) -> None:
        if self._forecast_feedback is None:
            return
        if result.narrative_forecast is None:
            return
        forecast = result.narrative_forecast
        council = result.council_consensus
        members = ()
        if council is not None:
            members = tuple(
                op.member_name.lower().replace(" ", "_").replace("_professor", "")
                for op in council.member_opinions
            )
        regime = result.regime.regime if result.regime else "unknown"
        self._forecast_feedback.register_trade_forecast(
            trace_id=trace_id,
            symbol=result.symbol,
            forecast_story=forecast.current_story,  # type: ignore[union-attr]
            expected_move=forecast.expected_next_move,  # type: ignore[union-attr]
            confidence=forecast.confidence,  # type: ignore[union-attr]
            strategy=forecast.recommended_strategy,  # type: ignore[union-attr]
            council_edge=council.opportunity_edge if council else "",
            regime=regime,
            council_members=members,
        )

    def _log_accepted_opportunity(
        self,
        result: PipelineResult,
        *,
        trace_id: str,
        evaluation_moment: datetime | None,
    ) -> None:
        if self._acceptance_log is None:
            return
        council = result.council_consensus
        forecast = result.narrative_forecast
        narrative = result.market_narrative
        story = result.market_story
        if council is None and story is None:
            return
        expected_pips = 0.0
        if result.dynamic_pip_target is not None:
            expected_pips = result.dynamic_pip_target.target_pips
        elif result.story_forecast is not None:
            expected_pips = result.story_forecast.expected_pip_range
        elif forecast is not None:
            expected_pips = forecast.expected_pip_range  # type: ignore[union-attr]
        strategy = "unknown"
        if result.strategy_selection is not None:
            strategy = result.strategy_selection.selected_strategy
        ts = (
            evaluation_moment.isoformat()
            if evaluation_moment
            else datetime.now().isoformat()
        )
        self._acceptance_log.record(
            AcceptedOpportunity(
                symbol=result.symbol,
                trace_id=trace_id,
                timestamp=ts,
                narrative=(
                    story.primary_story
                    if story
                    else (narrative.primary_story if narrative else council.consensus_narrative)
                ),
                micro_class=council.micro_narrative_class,
                council_votes_for=council.votes_for,
                council_votes_against=council.votes_against,
                council_vote_breakdown=council.vote_breakdown,
                price_action_reason=council.price_action_reason,
                volume_reason=council.volume_reason,
                expected_pips=expected_pips,
                strategy_selected=strategy,
                expansion_mode=council.expansion_mode,
                micro_harvest=council.micro_harvest,
            )
        )

    def _register_trader_memory(self, result: PipelineResult, *, trace_id: str) -> None:
        """Record pending trade memory — outcomes updated from journal on close."""
        memory = getattr(self._trader_brain, "_memory_engine", None)
        if memory is None:
            return
        if result.entry is None or result.entry.action not in {"enter_buy", "enter_sell"}:
            return
        psychology = None
        psych_engine = getattr(self._trader_brain, "_psychology_engine", None)
        if psych_engine is not None and result.market_story is not None:
            try:
                psychology = psych_engine.infer(
                    symbol=result.symbol,
                    market_story=result.market_story,
                    story_evolution=result.story_evolution,
                    indicator_interpretation=result.indicator_interpretation,
                )
            except Exception:
                psychology = None
        try:
            memory.record_from_context(
                trade_id=trace_id,
                symbol=result.symbol,
                outcome="pending",
                market_story=result.market_story,
                market_psychology=psychology,
                story_evolution=result.story_evolution,
                story_forecast=result.story_forecast,
            )
        except Exception:
            pass
