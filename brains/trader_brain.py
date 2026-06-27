"""Trader Brain — orchestrates ALL opportunity discovery.

Must NOT import conservative execution, validation gates, or auditor pessimism.
The Trader hunts opportunities; the Auditor verifies outcomes separately.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd

from config.settings import KraitosConfig
from core.helpers import (
    compute_stop_loss,
    compute_take_profit,
    is_in_trading_session,
    pip_size_for_symbol,
    resolve_spread_limit,
)
from core.pair_gating import pair_trading_allowed
from core.risk_controller import RiskController
from execution.entry_engine import EntryEngine
from execution.models import EntryContext, EntryDecision
from risk.models import RiskDecision
from strategies.harvest_engine import HarvestEngine
from intelligence.story_aware_harvest_engine import StoryAwareHarvestEngine
from intelligence.participation_tracker import get_participation_tracker
from strategies.market_structure import MarketStructureAnalyzer
from strategies.micro_scalper import MicroScalper
from strategies.models import (
    HarvestContext,
    HarvestDecision,
    MarketContext,
    MicroScalpSignal,
    MultiTimeframeBiasResult,
    RegimeResult,
)
from strategies.multitimeframe_bias import (
    MultiTimeframeBiasAnalyzer,
    REQUIRED_TIMEFRAMES as BIAS_TIMEFRAMES,
)
from strategies.news_filter import NewsFilter
from strategies.regime_detector import RegimeDetector

from council.cognitive_brain import CognitiveBrain
from council.opportunity_hunter_council import CouncilExpansionConfig, OpportunityHunterCouncil
from council.rejection_tracker import get_rejection_tracker
from intelligence.forecast_feedback import ForecastFeedbackStore
from intelligence.market_story_engine import MarketStoryEngine
from intelligence.story_evolution_engine import StoryEvolutionEngine
from intelligence.story_forecast_engine import StoryForecastEngine

from brains.models import TradeCandidate, TraderBrainStats, TraderContext

if TYPE_CHECKING:
    from analytics.pair_specialisation import PairSpecialisationAnalyzer
    from intelligence.opportunity_allocator import OpportunityAllocator
    from portfolio.portfolio_construction import PortfolioConstructionEngine
    from pathlib import Path


class TraderBrain:
    """Elite discretionary thinking and machine execution — hunts opportunities."""

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
        opportunity_allocator: OpportunityAllocator | None = None,
        portfolio_engine: PortfolioConstructionEngine | None = None,
        story_engine: MarketStoryEngine | None = None,
        evolution_engine: StoryEvolutionEngine | None = None,
        forecast_engine: StoryForecastEngine | None = None,
        council: OpportunityHunterCouncil | None = None,
        forecast_feedback: ForecastFeedbackStore | None = None,
    ) -> None:
        self._config = config
        self._regime_detector = regime_detector
        self._bias_analyzer = bias_analyzer
        self._structure_analyzer = structure_analyzer
        if isinstance(harvest_engine, StoryAwareHarvestEngine):
            self._harvest_engine = harvest_engine
        else:
            self._harvest_engine = StoryAwareHarvestEngine(harvest_engine)
        self._micro_scalper = micro_scalper
        self._entry_engine = entry_engine
        self._risk_controller = risk_controller
        self._news_filter = news_filter
        self._pair_analyzer = pair_analyzer
        self._project_root = project_root
        self._structure_tf = config.pipeline.structure_timeframe
        self._allocator = opportunity_allocator
        self._portfolio_engine = portfolio_engine
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
        self._cognitive_brain = (
            CognitiveBrain(
                project_root,
                deliberation_rounds=(
                    1
                    if config.pipeline.reality_engine_mode
                    else 2
                ),
            )
            if project_root and config.pipeline.cognitive_council_mode
            else None
        )
        from intelligence.market_mind_engine import MarketMindEngine
        from intelligence.market_mind_reports import MarketMindReportWriter
        from intelligence.market_storyteller_engine import MarketStorytellerEngine
        from intelligence.picture_reports import PictureTheoryReportWriter
        from reality.reality_engine import RealityEngine
        from reality.reality_reports import RealityReportWriter

        self._reality_engine = (
            RealityEngine(project_root, cognitive=self._cognitive_brain)
            if project_root
            and config.pipeline.reality_engine_mode
            and self._cognitive_brain is not None
            else None
        )
        self._reality_reports = (
            RealityReportWriter(project_root)
            if project_root and config.pipeline.reality_engine_mode
            else None
        )
        self._market_mind = (
            MarketMindEngine(project_root, cognitive=self._cognitive_brain)
            if project_root
            and config.pipeline.market_mind_mode
            and not config.pipeline.reality_engine_mode
            and self._cognitive_brain is not None
            else None
        )
        self._mind_reports = (
            MarketMindReportWriter(project_root)
            if project_root
            and config.pipeline.market_mind_mode
            and not config.pipeline.reality_engine_mode
            else None
        )
        self._storyteller = (
            MarketStorytellerEngine(project_root)
            if project_root
            and config.pipeline.picture_theory_mode
            and not config.pipeline.market_mind_mode
            and not config.pipeline.reality_engine_mode
            else None
        )
        self._picture_reports = (
            PictureTheoryReportWriter(project_root)
            if project_root
            and config.pipeline.picture_theory_mode
            and not config.pipeline.market_mind_mode
            and not config.pipeline.reality_engine_mode
            else None
        )
        self._forecast_feedback = forecast_feedback or (
            ForecastFeedbackStore(project_root) if project_root else None
        )
        from intelligence.indicator_interpretation_engine import IndicatorInterpretationEngine
        from intelligence.market_psychology_engine import MarketPsychologyEngine
        from intelligence.trader_memory_engine import TraderMemoryEngine

        self._interpretation_engine = (
            IndicatorInterpretationEngine(project_root) if project_root else None
        )
        self._psychology_engine = (
            MarketPsychologyEngine(project_root) if project_root else None
        )
        self._memory_engine = (
            TraderMemoryEngine(project_root) if project_root else None
        )
        from intelligence.human_trader_reasoning_layer import HumanTraderReasoningLayer

        self._reasoning_layer = (
            HumanTraderReasoningLayer(project_root) if project_root else None
        )
        from intelligence.kraitos_thesis_doctrine import KraitosThesisEngine
        from intelligence.individual_trade_doctrine import IndividualTradeDoctrineEngine
        from strategies.market_regime_engine import MarketRegimeEngine
        from strategies.range_intelligence_engine import RangeIntelligenceEngine
        from strategies.scalping_intelligence_engine import ScalpingIntelligenceEngine
        from strategies.trend_quality_engine import TrendQualityEngine

        self._thesis_engine = KraitosThesisEngine(timeframe=self._structure_tf)
        self._individual_trade_engine = IndividualTradeDoctrineEngine()
        self._market_regime_engine = MarketRegimeEngine()
        self._range_intelligence_engine = RangeIntelligenceEngine()
        self._trend_quality_engine = TrendQualityEngine()
        self._scalping_intelligence_engine = ScalpingIntelligenceEngine()
        from brains.intelligence_integration import IntelligenceIntegrator

        self._intelligence = IntelligenceIntegrator(structure_timeframe=self._structure_tf)
        from intelligence.thesis_projection_learning_engine import (
            get_thesis_projection_learning_engine,
        )

        self._projection_learning = (
            get_thesis_projection_learning_engine(project_root) if project_root else None
        )
        from core.expectancy_doctrine import build_expectancy_doctrine

        self._expectancy = build_expectancy_doctrine(
            project_root=project_root,
            config=config,
            risk_controller=risk_controller,
        )
        self._stats = TraderBrainStats()

    @property
    def stats(self) -> TraderBrainStats:
        return self._stats

    def evaluate(self, context: TraderContext) -> TradeCandidate:
        """Run opportunity discovery — returns primary candidate (first valid path)."""
        return self.evaluate_all(context)[0]

    def evaluate_all(self, context: TraderContext) -> list[TradeCandidate]:
        """Return every valid story-based opportunity for one symbol (harvest + scalp paths)."""
        self._stats.symbols_scanned += 1
        self._stats.last_scan_at = datetime.now().isoformat()

        base = self._build_base_candidate(context)
        base.trade_reasoning = self._run_trade_reasoning(base)
        candidates = self._split_opportunity_candidates(
            base, evaluation_moment=context.evaluation_moment
        )

        tracker = get_rejection_tracker()
        tracker.record_evaluation()
        for candidate in candidates:
            if candidate.harvest is not None and candidate.harvest.allowed:
                self._stats.harvest_allowed += 1
                self._stats.opportunities_found += 1
            if candidate.micro_scalp is not None and candidate.micro_scalp.action in {"buy", "sell"}:
                self._stats.micro_scalp_signals += 1
            if candidate.trade_reasoning is None:
                candidate.trade_reasoning = self._run_trade_reasoning(candidate)
            if candidate.entry is not None and candidate.entry.action == "reject":
                tracker.record_stage("thesis", candidate.entry.explanation)
            if candidate.thesis is not None and not candidate.thesis.is_tradeable:
                tracker.record_stage("thesis", candidate.thesis.rejection_reason)
            if candidate.trade_intent:
                self._stats.trade_candidates += 1
                tracker.record_trade()
            if candidate.entry is not None and candidate.entry.action == "reject":
                tracker.record_stage("entry", candidate.entry.explanation)
            elif candidate.harvest is not None and not candidate.harvest.allowed:
                tracker.record_stage("harvest_engine", candidate.harvest.reason)
        return candidates

    def _build_base_candidate(self, context: TraderContext) -> TradeCandidate:
        candidate = TradeCandidate(
            symbol=context.symbol,
            trace_id=context.trace_id,
            bid=context.bid,
            ask=context.ask,
            spread_pips=context.spread_pips,
            spread_limit=context.spread_limit,
            candles=context.candles,
            opportunity_key=context.symbol,
        )
        candidate.regime = self._run_regime(candidate)
        candidate.range_intelligence = self._run_range_intelligence(candidate)
        candidate.market_regime_intelligence = self._run_market_regime_intelligence(candidate)
        candidate.bias = self._run_bias(candidate)
        candidate.structure = self._run_structure(candidate)
        candidate.trend_quality = self._run_trend_quality(candidate)
        candidate.scalping_intelligence = self._run_scalping_intelligence(candidate)
        candidate.indicator_interpretation = self._run_indicator_interpretation(candidate)
        candidate.story_evolution = self._run_story_evolution(candidate)
        candidate.brain_story = self._expectancy.read_market_story(
            symbol=candidate.symbol,
            candles=candidate.candles,
            indicator_interpretation=candidate.indicator_interpretation,
        )
        candidate.market_story = self._run_market_story(
            candidate,
            evaluation_moment=context.evaluation_moment,
            story_evolution=candidate.story_evolution,
            indicator_interpretation=candidate.indicator_interpretation,
        )
        if candidate.market_story is not None:
            candidate.market_narrative = candidate.market_story.to_narrative_result()
        candidate.story_forecast = self._run_story_forecast(candidate)
        if candidate.story_forecast is not None:
            candidate.narrative_forecast = candidate.story_forecast.to_narrative_forecast()
        candidate.council_consensus = self._run_council_observers(
            candidate, evaluation_moment=context.evaluation_moment
        )
        candidate.indicator_confirmation = self._run_indicator_confirmation(candidate)
        candidate.asset_trend, candidate.strategy_selection, candidate.opportunity_allocation = (
            self._run_opportunity_allocation(
                candidate, evaluation_moment=context.evaluation_moment
            )
        )
        allocation = candidate.opportunity_allocation
        if allocation is not None:
            candidate.harvest_score = allocation.harvest_score
            candidate.archetype_check = allocation.archetype_check
            candidate.dynamic_pip_target = allocation.dynamic_pip_target
        candidate.harvest = self._run_setup_quality(
            candidate, evaluation_moment=context.evaluation_moment
        )
        candidate.micro_scalp = self._run_precision_entry_scan(candidate)
        self._intelligence.enrich_market_reading(
            candidate,
            evaluation_moment=context.evaluation_moment,
        )
        if self._reality_engine is not None:
            candidate.reality_decision = self._run_reality_engine(
                candidate,
                evaluation_moment=context.evaluation_moment,
            )
            if candidate.reality_decision is not None:
                cognitive = candidate.reality_decision.cognitive_snapshot
                if cognitive and cognitive.get("thesis"):
                    from council.cognitive_models import CIODecision

                    candidate.cognitive_decision = self._cognitive_brain.latest(
                        candidate.symbol
                    ) if self._cognitive_brain else None
        elif self._market_mind is not None:
            candidate.market_mind_decision = self._run_market_mind(
                candidate,
                evaluation_moment=context.evaluation_moment,
            )
            if candidate.market_mind_decision is not None:
                mind = candidate.market_mind_decision
                candidate.cognitive_decision = mind.cognitive
                candidate.storyteller_decision = mind.as_storyteller()
                candidate.market_picture = mind.picture
        else:
            candidate.cognitive_decision = self._run_cognitive_council(
                candidate,
                evaluation_moment=context.evaluation_moment,
            )
            candidate.storyteller_decision = self._run_market_storyteller(
                candidate,
                evaluation_moment=context.evaluation_moment,
            )
            if candidate.storyteller_decision is not None:
                candidate.market_picture = candidate.storyteller_decision.picture
        return candidate

    def _clone_candidate(self, base: TradeCandidate, **overrides: object) -> TradeCandidate:
        clone = TradeCandidate(
            symbol=base.symbol,
            trace_id=overrides.get("trace_id", base.trace_id) or base.trace_id,
            bid=base.bid,
            ask=base.ask,
            spread_pips=base.spread_pips,
            spread_limit=base.spread_limit,
            candles=base.candles,
            opportunity_key=str(overrides.get("opportunity_key", base.opportunity_key)),
            setup_kind=str(overrides.get("setup_kind", base.setup_kind)),
        )
        for field_name in (
            "regime", "bias", "structure", "harvest", "micro_scalp", "entry", "risk",
            "entry_price", "stop_loss", "take_profit", "pair_allowed", "news_allowed",
            "asset_trend", "strategy_selection", "opportunity_allocation", "harvest_score",
            "archetype_check", "dynamic_pip_target", "portfolio_construction",
            "market_story", "story_evolution", "story_forecast", "market_narrative",
            "narrative_forecast", "council_consensus", "indicator_confirmation",
            "indicator_interpretation", "trade_reasoning", "thesis", "individual_trade_plan",
            "conviction_assessment", "opportunity_assessment", "decision_result",
            "execution_quality", "institutional_structure", "liquidity_sweep",
            "false_breakout", "market_lifecycle", "reversal_pressure",
            "session_intelligence", "news_context",
            "trade_maturity", "location_quality", "timing_quality", "market_acceptance",
            "market_regime_intelligence", "range_intelligence",
            "trend_quality", "scalping_intelligence",
            "brain_story", "patience_decision", "conviction_sizing", "cognitive_decision",
            "storyteller_decision", "market_picture", "market_mind_decision", "reality_decision",
        ):
            setattr(clone, field_name, getattr(base, field_name))
        for key, value in overrides.items():
            if key not in {"trace_id", "opportunity_key", "setup_kind"}:
                setattr(clone, key, value)
        return clone

    def _split_opportunity_candidates(
        self,
        base: TradeCandidate,
        *,
        evaluation_moment: datetime | None,
    ) -> list[TradeCandidate]:
        """Emit separate candidates per opportunity class — never rank-and-drop."""
        story = base.market_story
        story_unlock = self._expectancy.harvest_unlock(
            harvest_allowed=base.harvest is not None and base.harvest.allowed,
            brain_story=base.brain_story,  # type: ignore[arg-type]
            legacy_story=story,
            harvest_score_band=(
                base.harvest_score.band if base.harvest_score is not None else None
            ),
        )
        selection = base.strategy_selection
        harvest_ok = base.harvest is not None and base.harvest.allowed
        scalp_ok = (
            base.micro_scalp is not None
            and base.micro_scalp.action in {"buy", "sell"}
            and selection is not None
            and selection.allow_micro_scalp
        )
        paths: list[tuple[str, str]] = []
        if harvest_ok or story_unlock:
            paths.append(("harvest", f"{base.symbol}:harvest"))
        # One entry per story — skip scalp when harvest/story path already active.
        if scalp_ok and not story_unlock:
            paths.append(("micro_scalp", f"{base.symbol}:scalp"))
        if not paths:
            reject = self._clone_candidate(base, setup_kind="none")
            reject.entry, reject.risk = self._run_entry_and_risk(
                reject,
                evaluation_moment=evaluation_moment,
                setup_kind="harvest",
            )
            return [reject]

        candidates: list[TradeCandidate] = []
        for setup_kind, key in paths:
            trace_suffix = "harvest" if setup_kind == "harvest" else "scalp"
            candidate = self._clone_candidate(
                base,
                trace_id=f"{base.trace_id}-{trace_suffix}",
                opportunity_key=key,
                setup_kind=setup_kind,
            )
            candidate.entry, candidate.risk = self._run_entry_and_risk(
                candidate,
                evaluation_moment=evaluation_moment,
                setup_kind=setup_kind,
            )
            candidates.append(candidate)
        return candidates

    def _run_story_evolution(self, candidate: TradeCandidate) -> object | None:
        if self._evolution_engine is None:
            return None
        return self._evolution_engine.update(
            candidate.symbol,
            candidate.candles,
        )

    def _run_indicator_interpretation(self, candidate: TradeCandidate) -> object | None:
        if self._interpretation_engine is None:
            return None
        if candidate.bias is None or candidate.structure is None or candidate.regime is None:
            return None
        direction = "neutral"
        if candidate.bias.bias != "neutral":
            direction = candidate.bias.bias
        return self._interpretation_engine.interpret(
            symbol=candidate.symbol,
            candles=candidate.candles,
            structure=candidate.structure,
            bias=candidate.bias,
            regime=candidate.regime,
            narrative_direction=direction,
            spread_pips=candidate.spread_pips,
            spread_limit=candidate.spread_limit,
        )

    def _run_market_story(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment: datetime | None = None,
        story_evolution: object | None = None,
        indicator_interpretation: object | None = None,
    ) -> object | None:
        if self._story_engine is None:
            return None
        assert candidate.bias is not None
        assert candidate.structure is not None
        assert candidate.regime is not None
        return self._story_engine.build(
            symbol=candidate.symbol,
            candles=candidate.candles,
            structure=candidate.structure,
            bias=candidate.bias,
            regime=candidate.regime,
            evaluation_moment=evaluation_moment,
            story_evolution_state=story_evolution,
            indicator_interpretation=indicator_interpretation,
        )

    def _run_story_forecast(self, candidate: TradeCandidate) -> object | None:
        if self._forecast_engine is None or candidate.market_story is None:
            return None
        assert candidate.bias is not None
        assert candidate.structure is not None
        assert candidate.regime is not None
        atr_ratio = None
        if candidate.asset_trend is not None:
            atr_ratio = candidate.asset_trend.features.atr_ratio  # type: ignore[union-attr]
        indicator_boost = (
            candidate.indicator_interpretation.insight_score
            if candidate.indicator_interpretation is not None
            else (
                candidate.indicator_confirmation.boost
                if candidate.indicator_confirmation is not None
                else 0.0
            )
        )
        if candidate.story_evolution is not None and self._evolution_engine is not None:
            self._evolution_engine.record_opportunity_informed()

        market_psychology, trader_memory_recall = self._gather_market_enrichment(candidate)
        synthesis = (
            candidate.market_story.synthesis if candidate.market_story is not None else None
        )
        return self._forecast_engine.forecast(
            symbol=candidate.symbol,
            market_story=candidate.market_story,
            candles=candidate.candles,
            structure=candidate.structure,
            bias=candidate.bias,
            regime=candidate.regime,
            indicator_atr_ratio=atr_ratio,
            indicator_confirmation_boost=indicator_boost,
            evolution_state=candidate.story_evolution,
            evolution_engine=self._evolution_engine,
            evidence_synthesis=synthesis,
            market_psychology=market_psychology,
            trader_memory_recall=trader_memory_recall,
        )

    def _run_trade_reasoning(self, candidate: TradeCandidate) -> object | None:
        if self._reasoning_layer is None:
            return None
        market_psychology, trader_memory_recall = self._gather_market_enrichment(candidate)
        return self._reasoning_layer.explain(
            symbol=candidate.symbol,
            setup_kind=candidate.setup_kind,
            market_story=candidate.market_story,
            story_forecast=candidate.story_forecast,
            indicator_interpretation=candidate.indicator_interpretation,
            story_evolution=candidate.story_evolution,
            market_psychology=market_psychology,
            trader_memory_recall=trader_memory_recall,
            harvest=candidate.harvest,
            micro_scalp=candidate.micro_scalp,
        )

    def _gather_market_enrichment(
        self,
        candidate: TradeCandidate,
    ) -> tuple[object | None, object | None]:
        market_psychology = None
        if (
            self._psychology_engine is not None
            and candidate.indicator_interpretation is not None
            and candidate.bias is not None
            and candidate.structure is not None
            and candidate.regime is not None
        ):
            direction = candidate.bias.bias if candidate.bias.bias != "neutral" else "neutral"
            market_psychology = self._psychology_engine.infer(
                symbol=candidate.symbol,
                candles=candidate.candles,
                structure=candidate.structure,
                bias=candidate.bias,
                regime=candidate.regime,
                indicator_interpretation=candidate.indicator_interpretation,
                narrative_direction=direction,
            )

        trader_memory_recall = None
        if self._memory_engine is not None and candidate.market_story is not None:
            synthesis = candidate.market_story.synthesis
            story_text = (
                synthesis.current_explanation
                if synthesis is not None
                else candidate.market_story.primary_story
            )
            psych_state = (
                market_psychology.psychology_state.to_dict()
                if market_psychology is not None
                else {}
            )
            trader_memory_recall = self._memory_engine.recall(
                symbol=candidate.symbol,
                story_explanation=story_text,
                psychological_state=psych_state,
                evolution_path=_evolution_path(candidate.story_evolution),
                macro_story=(
                    candidate.story_evolution.macro_story
                    if candidate.story_evolution is not None
                    else candidate.market_story.macro_story
                ),
            )
        return market_psychology, trader_memory_recall

    def _run_indicator_confirmation(self, candidate: TradeCandidate) -> object | None:
        from intelligence.indicator_confirmation import IndicatorConfirmationEngine

        if candidate.bias is None or candidate.structure is None:
            return None
        direction = "neutral"
        if candidate.story_forecast is not None:
            direction = candidate.story_forecast.direction
        elif candidate.narrative_forecast is not None:
            direction = candidate.narrative_forecast.direction  # type: ignore[union-attr]
        elif candidate.bias.bias != "neutral":
            direction = candidate.bias.bias
        features = None
        if candidate.asset_trend is not None:
            features = candidate.asset_trend.features  # type: ignore[union-attr]
        return IndicatorConfirmationEngine().confirm(
            features=features,
            structure=candidate.structure,
            bias=candidate.bias,
            narrative_direction=direction,
            candles=candidate.candles,
            symbol=candidate.symbol,
            regime=candidate.regime,
            spread_pips=candidate.spread_pips,
            spread_limit=candidate.spread_limit,
        )

    def _run_council_observers(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment: datetime | None = None,
    ) -> object | None:
        if self._council is None:
            return None
        if candidate.market_story is None or candidate.story_forecast is None:
            return None
        assert candidate.bias is not None
        assert candidate.structure is not None
        assert candidate.regime is not None
        indicator_boost = (
            candidate.indicator_interpretation.insight_score
            if candidate.indicator_interpretation is not None
            else (
                candidate.indicator_confirmation.boost
                if candidate.indicator_confirmation is not None
                else 0.0
            )
        )
        consensus = self._council.observe(
            symbol=candidate.symbol,
            market_story=candidate.market_story,
            story_forecast=candidate.story_forecast,
            structure=candidate.structure,
            bias=candidate.bias,
            regime=candidate.regime,
            evaluation_moment=evaluation_moment,
            indicator_confirmation_boost=indicator_boost,
            spread_pips=candidate.spread_pips,
        )
        tracker = get_rejection_tracker()
        tracker.record_council(
            allowed=consensus.allow_opportunity,
            micro_harvest=consensus.micro_harvest,
        )
        symbols = self._config.trading.symbols
        if (
            len(self._council._latest) >= len(symbols)
            and candidate.symbol == symbols[-1]
        ):
            self._council.maybe_write_reports()
            if self._story_engine is not None:
                self._story_engine.write_report()
                self._story_engine.synthesis_engine.write_all_reports()
            if candidate.indicator_interpretation is not None and self._interpretation_engine is not None:
                self._interpretation_engine.write_all_reports()
            if self._evolution_engine is not None:
                self._evolution_engine.write_all_reports()
            if self._forecast_engine is not None:
                self._forecast_engine.write_report()
        return consensus

    def _run_cognitive_council(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment: datetime | None = None,
    ) -> object | None:
        if self._cognitive_brain is None:
            return None
        if candidate.structure is None or candidate.regime is None:
            return None
        from loguru import logger

        decision = self._cognitive_brain.deliberate(
            candidate,
            evaluation_moment=evaluation_moment,
        )
        logger.debug(f"Cognitive council {candidate.symbol}: {decision.summary}")
        symbols = self._config.trading.symbols
        if (
            self._cognitive_brain.reports is not None
            and len(self._cognitive_brain._latest) >= len(symbols)
            and candidate.symbol == symbols[-1]
        ):
            self._cognitive_brain.maybe_write_reports()
        return decision

    def _run_reality_engine(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment: datetime | None = None,
    ) -> object | None:
        if self._reality_engine is None:
            return None
        if candidate.structure is None or candidate.regime is None:
            return None
        from loguru import logger

        decision = self._reality_engine.evaluate(
            candidate,
            evaluation_moment=evaluation_moment,
        )
        logger.debug(
            f"Reality {candidate.symbol}: {decision.convergence.dominant_model_name} "
            f"{decision.convergence.convergence_score:.0f}% — {decision.reason[:120]}"
        )
        if self._reality_reports is not None:
            self._reality_reports.record(candidate.symbol, decision)
            self._reality_reports.write_cycle_jsonl(decision)
            symbols = self._config.trading.symbols
            if (
                len(self._reality_engine._latest) >= len(symbols)
                and candidate.symbol == symbols[-1]
            ):
                self._reality_reports.write_report()
                self._reality_engine.flush_state()
        return decision

    def _run_market_mind(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment: datetime | None = None,
    ) -> object | None:
        if self._market_mind is None:
            return None
        if candidate.structure is None or candidate.regime is None:
            return None
        from loguru import logger

        decision = self._market_mind.evaluate(
            candidate,
            evaluation_moment=evaluation_moment,
        )
        logger.debug(
            f"Market Mind {candidate.symbol}: {decision.mind_state} "
            f"{decision.participation} — {decision.reason[:120]}"
        )
        if self._mind_reports is not None:
            self._mind_reports.record(candidate.symbol, decision)
            self._mind_reports.write_cycle_jsonl(decision)
            symbols = self._config.trading.symbols
            if (
                len(self._market_mind._latest) >= len(symbols)
                and candidate.symbol == symbols[-1]
            ):
                self._mind_reports.write_report()
        return decision

    def _run_market_storyteller(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment: datetime | None = None,
    ) -> object | None:
        if self._storyteller is None:
            return None
        if candidate.structure is None or candidate.regime is None:
            return None
        from loguru import logger

        decision = self._storyteller.evaluate(
            candidate,
            evaluation_moment=evaluation_moment,
            cognitive=candidate.cognitive_decision,
        )
        logger.debug(f"Storyteller {candidate.symbol}: {decision.participation} — {decision.reason[:120]}")
        if self._picture_reports is not None:
            self._picture_reports.record(candidate.symbol, decision)
            self._picture_reports.write_cycle_jsonl(decision)
            symbols = self._config.trading.symbols
            if (
                len(self._storyteller._latest) >= len(symbols)
                and candidate.symbol == symbols[-1]
            ):
                self._picture_reports.write_report()
        return decision

    def _run_regime(self, candidate: TradeCandidate) -> RegimeResult:
        h1 = candidate.candles["H1"]
        return self._regime_detector.detect(
            h1,
            spread_limit=candidate.spread_limit,
        )

    def _run_range_intelligence(self, candidate: TradeCandidate) -> object | None:
        frame = candidate.candles.get(self._structure_tf)
        if frame is None or frame.empty:
            frame = candidate.candles.get("H1")
        if frame is None or frame.empty:
            return None
        try:
            return self._range_intelligence_engine.analyze(frame, symbol=candidate.symbol)
        except Exception as exc:
            from loguru import logger

            logger.debug(f"Range intelligence unavailable for {candidate.symbol}: {exc}")
            return None

    def _run_market_regime_intelligence(self, candidate: TradeCandidate) -> object | None:
        frame = candidate.candles.get(self._structure_tf)
        if frame is None or frame.empty:
            frame = candidate.candles.get("H1")
        if frame is None or frame.empty:
            return None
        try:
            return self._market_regime_engine.analyze(
                frame,
                symbol=candidate.symbol,
                range_intelligence=candidate.range_intelligence,
            )
        except Exception as exc:
            from loguru import logger

            logger.debug(f"Market regime intelligence unavailable for {candidate.symbol}: {exc}")
            return None

    def _run_bias(self, candidate: TradeCandidate) -> MultiTimeframeBiasResult:
        return self._bias_analyzer.evaluate(
            {tf: candidate.candles[tf] for tf in BIAS_TIMEFRAMES},
        )

    def _run_opportunity_allocation(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment: datetime | None = None,
    ) -> tuple[object | None, object | None, object | None]:
        if self._allocator is None:
            return None, None, None
        assert candidate.bias is not None
        assert candidate.structure is not None
        assert candidate.regime is not None

        portfolio = self._risk_controller.portfolio_snapshot()
        drawdown_pct = portfolio.drawdown_pct
        open_count = sum(
            1 for position in portfolio.open_positions if position.symbol == candidate.symbol
        )

        indicator_boost = (
            candidate.indicator_interpretation.insight_score
            if candidate.indicator_interpretation is not None
            else (
                candidate.indicator_confirmation.boost
                if candidate.indicator_confirmation is not None
                else 0.0
            )
        )
        allocation = self._allocator.allocate(
            symbol=candidate.symbol,
            candles=candidate.candles,
            bias=candidate.bias,
            structure=candidate.structure,
            regime=candidate.regime,
            spread_pips=candidate.spread_pips,
            spread_limit=candidate.spread_limit,
            drawdown_pct=drawdown_pct,
            open_positions_on_symbol=open_count,
            evaluation_moment=evaluation_moment,
            base_min_bias=self._entry_engine.config.min_bias_confidence,
            base_min_swings=self._entry_engine.config.min_structure_swings,
            market_story=candidate.market_story,
            narrative=candidate.market_narrative,
            story_forecast=candidate.story_forecast,
            story_evolution=candidate.story_evolution,
            forecast=candidate.narrative_forecast,
            council=candidate.council_consensus,
            indicator_insight=indicator_boost,
        )
        symbols = self._config.trading.symbols
        if (
            len(self._allocator._allocations) >= len(symbols)
            and candidate.symbol == symbols[-1]
        ):
            self._allocator.maybe_write_reports()

        snapshot = self._allocator._trend_snapshots.get(candidate.symbol)
        return snapshot, allocation.strategy_selection, allocation

    def _run_structure(self, candidate: TradeCandidate) -> MarketContext:
        frame = candidate.candles[self._structure_tf]
        return self._structure_analyzer.analyze(
            frame,
            symbol=candidate.symbol,
            timeframe=self._structure_tf,
        )

    def _run_trend_quality(self, candidate: TradeCandidate) -> object | None:
        frame = candidate.candles.get(self._structure_tf)
        if frame is None or frame.empty:
            return None
        try:
            return self._trend_quality_engine.analyze(
                frame,
                symbol=candidate.symbol,
                timeframe=self._structure_tf,
            )
        except Exception as exc:
            from loguru import logger

            logger.debug(f"Trend quality unavailable for {candidate.symbol}: {exc}")
            return None

    def _run_scalping_intelligence(self, candidate: TradeCandidate) -> object | None:
        timeframe = "M1"
        frame = candidate.candles.get("M1")
        if frame is None or frame.empty:
            timeframe = "M5"
            frame = candidate.candles.get("M5")
        if frame is None or frame.empty:
            return None
        market_phase = "unknown"
        reversal_pressure = 0.0
        if candidate.trend_quality is not None:
            market_phase = str(getattr(candidate.trend_quality, "trend_phase", "unknown"))
            reversal_pressure = float(
                getattr(candidate.trend_quality, "reversal_probability", 0.0) or 0.0
            )
        try:
            return self._scalping_intelligence_engine.analyze(
                frame,
                symbol=candidate.symbol,
                timeframe=timeframe,
                spread_pips=candidate.spread_pips,
                spread_limit=candidate.spread_limit,
                market_phase=market_phase,
                reversal_pressure=reversal_pressure,
            )
        except Exception as exc:
            from loguru import logger

            logger.debug(f"Scalping intelligence unavailable for {candidate.symbol}: {exc}")
            return None

    def _run_setup_quality(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment: datetime | None = None,
    ) -> HarvestDecision:
        assert candidate.regime is not None
        assert candidate.bias is not None
        assert candidate.structure is not None

        pair_allowed, pair_reason = pair_trading_allowed(
            candidate.symbol,
            analyzer=self._pair_analyzer,
            output_path=self._project_root / "logs" / "pair_specialisation.json",
        )
        candidate.pair_allowed = pair_allowed

        news_allowed = True
        if self._config.trading.news_filter_enabled:
            news_result = self._news_filter.check_symbol(candidate.symbol)
            news_allowed = news_result.allowed
        candidate.news_allowed = news_allowed

        if not pair_allowed:
            return HarvestDecision(
                mode="none",
                allowed=False,
                target_pips=0.0,
                reason=f"Pair blocked: {pair_reason}",
            )

        if not news_allowed:
            return HarvestDecision(
                mode="none",
                allowed=False,
                target_pips=0.0,
                reason="News filter blocked trading",
            )

        story = candidate.market_story
        tracker = get_rejection_tracker()
        synthesis = getattr(story, "synthesis", None) if story is not None else None
        story_actionable = self._expectancy.story_actionable(
            candidate.brain_story,  # type: ignore[arg-type]
            story,
        )
        if story is not None and not story.story_clear and not story_actionable:
            tracker.record_stage(
                "market_story",
                "Story low confidence — harvest proceeds on expectancy metrics only",
            )
        elif story is not None and not story.story_clear and story_actionable:
            tracker.record_stage(
                "market_story",
                "Brain story actionable despite legacy synthesis unclear",
            )
        if (
            synthesis is not None
            and synthesis.story_clear
            and synthesis.contradicting_evidence
            and self._story_engine is not None
        ):
            self._story_engine.synthesis_engine.record_opportunity_recovered()

        harvest_score = candidate.harvest_score
        if harvest_score is not None and harvest_score.band == "no_harvest":
            if story is None or not story.opportunity_type:
                tracker.record_stage("harvest_score", harvest_score.reason)

        pip_target = candidate.dynamic_pip_target
        if pip_target is not None and pip_target.skip_trade:
            if not story_actionable:
                tracker.record_stage("dynamic_pip", pip_target.reason)
                return HarvestDecision(
                    mode="none",
                    allowed=False,
                    target_pips=0.0,
                    reason=pip_target.reason,
                )

        narrative_dir = "neutral"
        if candidate.story_forecast is not None:
            narrative_dir = candidate.story_forecast.direction
        elif candidate.narrative_forecast is not None:
            narrative_dir = candidate.narrative_forecast.direction  # type: ignore[union-attr]
        volume_strong = False
        structure_supports = False
        if candidate.indicator_interpretation is not None:
            for reading in candidate.indicator_interpretation.psychological_readings:
                if reading.indicator == "OBV" and "supports" in reading.reading:
                    volume_strong = True
                if reading.indicator == "Moving averages" and "control" in reading.reading:
                    if "Neither" not in reading.reading:
                        structure_supports = True
        elif candidate.indicator_confirmation is not None:
            volume_strong = candidate.indicator_confirmation.momentum_confirms
            structure_supports = (
                candidate.indicator_confirmation.ma_confirms
                or candidate.structure.trend == candidate.bias.bias
            )
        council = candidate.council_consensus
        context = HarvestContext(
            symbol=candidate.symbol,
            bias=candidate.bias,
            structure=candidate.structure,
            regime=candidate.regime,
            current_spread=candidate.spread_pips,
            spread_limit=candidate.spread_limit,
            in_active_session=is_in_trading_session(self._config, evaluation_moment),
            news_risk_active=not news_allowed,
            council_micro_harvest=council.micro_harvest if council else False,
            narrative_direction=narrative_dir,
            volume_momentum_strong=volume_strong,
            story_clear=story_actionable,
            opportunity_type=story.opportunity_type if story else None,
            price_action_valid=story.strike.strike != "none" if story else False,
            structure_supports=structure_supports,
        )
        decision = self._harvest_engine.evaluate(
            context,
            story_forecast=candidate.story_forecast,
        )
        tracker_pt = get_participation_tracker()
        if candidate.market_story is not None:
            tracker_pt.record_story()
        if candidate.indicator_interpretation is not None:
            tracker_pt.record_interpretation()
        if decision.allowed:
            tracker_pt.record_opportunity_seen()
        elif not story_actionable:
            tracker_pt.record_opportunity_missed(decision.reason)
        allocation = candidate.opportunity_allocation
        if allocation is not None and allocation.harvest_boost:
            decision = self._maybe_boost_harvest(decision)
        if decision.allowed and pip_target is not None and pip_target.target_pips > 0:
            mode = decision.mode
            if harvest_score is not None and harvest_score.band == "aggressive":
                mode = "full"
            elif harvest_score is not None and harvest_score.band == "conditional":
                mode = "conditional"
            decision = HarvestDecision(
                mode=mode,
                allowed=True,
                target_pips=pip_target.target_pips,
                reason=f"{decision.reason}; {pip_target.reason}",
            )
        return decision

    @staticmethod
    def _maybe_boost_harvest(decision: HarvestDecision) -> HarvestDecision:
        if decision.allowed:
            return decision
        if "Mandatory conditions failed" in decision.reason:
            return decision
        lowered = decision.reason.lower()
        if "insufficient secondary" not in lowered and "secondary support" not in lowered:
            return decision
        return HarvestDecision(
            mode="conditional",
            allowed=True,
            target_pips=5.0,
            reason=f"Institutional trend harvest boost: {decision.reason}",
        )

    def _run_precision_entry_scan(self, candidate: TradeCandidate) -> MicroScalpSignal:
        selection = candidate.strategy_selection
        if selection is not None and not selection.allow_micro_scalp:
            if not selection.allow_harvest:
                return MicroScalpSignal(
                    action="no_trade",
                    reason=f"Dynamic strategy: {selection.reason}",
                )
        return self._micro_scalper.scan(
            candidate.candles["M1"],
            candidate.candles["M5"],
            spread_limit=candidate.spread_limit,
            current_spread=candidate.spread_pips,
        )

    def _run_entry_and_risk(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment: datetime | None = None,
        setup_kind: str = "harvest",
    ) -> tuple[EntryDecision | None, RiskDecision]:
        assert candidate.bias is not None
        assert candidate.structure is not None
        assert candidate.regime is not None
        assert candidate.harvest is not None
        assert candidate.micro_scalp is not None

        allocation = candidate.opportunity_allocation
        selection = candidate.strategy_selection
        scalp_entry = setup_kind == "micro_scalp"
        harvest_path = setup_kind == "harvest"
        story_unlock = self._expectancy.harvest_unlock(
            harvest_allowed=candidate.harvest.allowed,
            brain_story=candidate.brain_story,  # type: ignore[arg-type]
            legacy_story=candidate.market_story,
            harvest_score_band=(
                candidate.harvest_score.band if candidate.harvest_score is not None else None
            ),
        )
        picture_unlock = False
        cognitive_unlock = False
        cio_mult = 1.0
        mind = candidate.market_mind_decision
        reality = candidate.reality_decision
        cognitive = candidate.cognitive_decision
        storyteller = candidate.storyteller_decision

        if reality is not None:
            from reality.reality_adapter import reality_as_entry_proxy

            mind = reality_as_entry_proxy(reality)

        # V5/V8: unified mind/reality decision when available
        if mind is not None:
            if mind.hard_risk_blocked:
                reason = mind.thesis.rejection_reason or mind.reason
                return (
                    EntryDecision(action="reject", explanation=reason, lot_size=0.0),
                    RiskDecision(approved=False, reason=reason, lot_size=0.0),
                )
            if (
                mind.participation in {"stand_aside", "wait"}
                and mind.allocation_multiplier <= 0
            ):
                reason = f"Mind {mind.mind_state}: {mind.reason}"
                return (
                    EntryDecision(action="wait", explanation=reason, lot_size=0.0),
                    RiskDecision(approved=False, reason=reason, lot_size=0.0),
                )
            if mind.thesis.thesis_clear and mind.thesis.side in {"buy", "sell"}:
                picture_unlock = True
            cio_mult = float(mind.allocation_multiplier)
            cognitive_unlock = mind.thesis.thesis_clear and cio_mult > 0
        elif storyteller is not None:
            if storyteller.hard_risk_blocked:
                reason = storyteller.thesis.rejection_reason or storyteller.reason
                return (
                    EntryDecision(action="reject", explanation=reason, lot_size=0.0),
                    RiskDecision(approved=False, reason=reason, lot_size=0.0),
                )
            if (
                storyteller.participation in {"stand_aside", "wait"}
                and storyteller.allocation_multiplier <= 0
            ):
                reason = f"Picture {storyteller.picture.clarity}: {storyteller.reason}"
                return (
                    EntryDecision(action="wait", explanation=reason, lot_size=0.0),
                    RiskDecision(approved=False, reason=reason, lot_size=0.0),
                )
            if storyteller.thesis.thesis_clear and storyteller.thesis.side in {"buy", "sell"}:
                picture_unlock = True
        if mind is None and cognitive is not None:
            if cognitive.hard_vetoes:
                reason = cognitive.hard_vetoes[0].reason
                return (
                    EntryDecision(action="reject", explanation=reason, lot_size=0.0),
                    RiskDecision(approved=False, reason=reason, lot_size=0.0),
                )
            cio_mult = float(cognitive.execution.allocation_multiplier)
            cognitive_unlock = cognitive.can_trade and cio_mult > 0
            if cognitive.observe_only and cio_mult <= 0:
                reason = f"CIO observe: {cognitive.execution.timing_guidance}"
                return (
                    EntryDecision(action="wait", explanation=reason, lot_size=0.0),
                    RiskDecision(approved=False, reason=reason, lot_size=0.0),
                )

        if harvest_path and not candidate.harvest.allowed and not story_unlock and not cognitive_unlock and not picture_unlock:
            return (
                EntryDecision(
                    action="reject",
                    explanation=candidate.harvest.reason,
                    lot_size=0.0,
                ),
                RiskDecision(approved=False, reason=candidate.harvest.reason, lot_size=0.0),
            )
        if scalp_entry and candidate.micro_scalp.action not in {"buy", "sell"}:
            reason = candidate.micro_scalp.reason or "No micro scalp signal"
            return (
                EntryDecision(action="reject", explanation=reason, lot_size=0.0),
                RiskDecision(approved=False, reason=reason, lot_size=0.0),
            )
        if not harvest_path and not scalp_entry:
            return (
                EntryDecision(
                    action="reject",
                    explanation=candidate.harvest.reason,
                    lot_size=0.0,
                ),
                RiskDecision(approved=False, reason=candidate.harvest.reason, lot_size=0.0),
            )

        defensive_scale = 1.0
        if allocation is not None and allocation.confirmation.defensive_mode:
            defensive_scale = min(defensive_scale, allocation.confirmation.risk_multiplier)

        if scalp_entry:
            side = candidate.micro_scalp.action  # type: ignore[assignment]
        else:
            trade_direction = candidate.bias.bias
            if trade_direction == "neutral" and candidate.story_forecast is not None:
                trade_direction = candidate.story_forecast.direction
            elif trade_direction == "neutral" and candidate.narrative_forecast is not None:
                trade_direction = candidate.narrative_forecast.direction  # type: ignore[union-attr]
            if trade_direction == "neutral" and candidate.market_story is not None:
                if candidate.structure.trend in {"bullish", "bearish"}:
                    trade_direction = candidate.structure.trend
            if trade_direction == "neutral" and reality is not None:
                rt_side = reality.thesis.side
                if rt_side == "buy":
                    trade_direction = "bullish"
                elif rt_side == "sell":
                    trade_direction = "bearish"
            if trade_direction == "neutral" and mind is not None and hasattr(mind, "thesis"):
                mind_side = mind.thesis.side
                if mind_side == "buy":
                    trade_direction = "bullish"
                elif mind_side == "sell":
                    trade_direction = "bearish"
            if trade_direction == "neutral" and storyteller is not None:
                st_side = storyteller.thesis.side
                if st_side == "buy":
                    trade_direction = "bullish"
                elif st_side == "sell":
                    trade_direction = "bearish"
            if trade_direction == "neutral" and cognitive is not None:
                cio_side = cognitive.thesis.side
                if cio_side == "buy":
                    trade_direction = "bullish"
                elif cio_side == "sell":
                    trade_direction = "bearish"
            if trade_direction == "neutral":
                reason = "Multi-timeframe bias is neutral"
                return (
                    EntryDecision(action="reject", explanation=reason, lot_size=0.0),
                    RiskDecision(approved=False, reason=reason, lot_size=0.0),
                )
            side = "buy" if trade_direction == "bullish" else "sell"
        entry_price = candidate.ask if side == "buy" else candidate.bid
        pip_size = pip_size_for_symbol(candidate.symbol)

        momentum_note = ""
        if candidate.micro_scalp is not None and candidate.micro_scalp.action == "no_trade":
            momentum_note = candidate.micro_scalp.reason or "momentum not confirmed"

        thesis = self._thesis_engine.build_thesis(
            symbol=candidate.symbol,
            side=side,
            entry_price=entry_price,
            structure=candidate.structure,
            bias=candidate.bias,
            pip_size=pip_size,
            spread_pips=candidate.spread_pips,
            spread_limit=candidate.spread_limit,
            risk_percent=float(self._config.risk.per_trade_pct),
            market_story=candidate.market_story,
            story_forecast=candidate.story_forecast,
            harvest=candidate.harvest,
            trade_reasoning=candidate.trade_reasoning,
            trend_quality=candidate.trend_quality,
            market_regime=candidate.market_regime_intelligence,
            range_intelligence=candidate.range_intelligence,
            scalping_intelligence=candidate.scalping_intelligence,
            setup_kind=setup_kind,
            momentum_note=momentum_note,
        )

        regime_label = candidate.regime.regime if candidate.regime else "unknown"
        story = candidate.market_story
        opp_type = story.opportunity_type if story else None
        story_clear = self._expectancy.story_actionable(
            candidate.brain_story,  # type: ignore[arg-type]
            story,
        )
        story_text = story.primary_story if story else ""
        bias_label = candidate.bias.bias if candidate.bias else "neutral"
        struct_trend = candidate.structure.trend if candidate.structure else "neutral"

        participation = self._intelligence.evaluate_participation(
            symbol=candidate.symbol,
            side=side,
            candidate=candidate,
            market_story=story_text,
            story_clear=story_clear,
            opportunity_type=str(opp_type) if opp_type else None,
            reward_risk=thesis.reward_risk_ratio,
            invalidation_level=thesis.invalidation_level,
            is_tradeable=thesis.is_tradeable,
        )
        conviction = participation.conviction
        opportunity = participation.opportunity

        individual_plan = self._individual_trade_engine.build_plan(
            symbol=candidate.symbol,
            side=side,
            entry_price=entry_price,
            stop_loss=thesis.stop_loss,
            target_liquidity=thesis.target_liquidity,
            opportunity_type=opp_type,
            regime_label=regime_label,
            story_clear=story_clear,
            structure_trend=struct_trend,
            bias_label=bias_label,
            spread_pips=candidate.spread_pips,
            spread_limit=candidate.spread_limit,
            candles=candidate.candles,
            sweep_level=thesis.invalidation_level,
            thesis_confidence=thesis.thesis_confidence,
            thesis_reward_risk=thesis.reward_risk_ratio,
            in_active_session=is_in_trading_session(
                self._config, evaluation_moment
            ),
            projection_learning=self._projection_learning,
            conviction_assessment=conviction,
        )
        candidate.individual_trade_plan = individual_plan

        if harvest_path and not individual_plan.entry_allowed and not story_clear:
            reason = f"Thesis projection: skip — {individual_plan.summary}"
            return (
                EntryDecision(action="reject", explanation=reason, lot_size=0.0),
                RiskDecision(approved=False, reason=reason, lot_size=0.0),
            )

        if individual_plan.entry_allowed:
            from dataclasses import replace

            thesis = replace(
                thesis,
                take_profit_1=individual_plan.take_profit_1,
                take_profit_2=individual_plan.take_profit_2,
                tp1_r_multiple=individual_plan.tp1_r,
                management_plan=(
                    f"{thesis.management_plan} | Individual v1.1: {individual_plan.summary}"
                ),
            )

        candidate.thesis = thesis

        if not thesis.is_tradeable:
            reason = f"Thesis rejected: {thesis.rejection_reason}"
            return (
                EntryDecision(action="reject", explanation=reason, lot_size=0.0),
                RiskDecision(approved=False, reason=reason, lot_size=0.0),
            )

        stop_loss = thesis.stop_loss
        take_profit = (
            individual_plan.take_profit_2
            if individual_plan.entry_allowed and individual_plan.runner_allowed
            else (
                individual_plan.take_profit_1
                if individual_plan.entry_allowed
                else thesis.take_profit_2
            )
        )
        candidate.entry_price = entry_price
        candidate.stop_loss = stop_loss
        candidate.take_profit = take_profit

        patience_decision = None
        patience_ready = False
        patience_explanation = ""
        if harvest_path and candidate.brain_story is not None:
            from brain.market_story_engine import MarketStory

            brain_story: MarketStory = candidate.brain_story  # type: ignore[assignment]
            if brain_story.direction != "neutral":
                patience_decision = self._expectancy.evaluate_patience(
                    story=brain_story,
                    structure=candidate.structure,
                    candles=candidate.candles.get("M5"),
                    bid=candidate.bid,
                    ask=candidate.ask,
                    symbol=candidate.symbol,
                )
                candidate.patience_decision = patience_decision
                if not patience_decision.ready:
                    reason = f"Patience: {patience_decision.reason}"
                    return (
                        EntryDecision(
                            action="wait",
                            explanation=reason,
                            lot_size=0.0,
                        ),
                        RiskDecision(approved=False, reason=reason, lot_size=0.0),
                    )
                if patience_decision.opportunity is not None:
                    opp = patience_decision.opportunity
                    entry_price = opp.entry_price
                    stop_loss = opp.stop_loss
                    side = opp.side
                    candidate.entry_price = entry_price
                    candidate.stop_loss = stop_loss
                    patience_ready = True
                    patience_explanation = opp.explanation

        conviction_sizing = None
        if harvest_path:
            setup_key = ""
            if patience_decision and patience_decision.opportunity is not None:
                setup_key = patience_decision.opportunity.entry_type
            conviction_sizing = self._expectancy.size_by_conviction(
                symbol=candidate.symbol,
                side=side,  # type: ignore[arg-type]
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                story=candidate.brain_story,  # type: ignore[arg-type]
                structure=candidate.structure,
                entry_opportunity=(
                    patience_decision.opportunity
                    if patience_decision is not None
                    else None
                ),
                setup_key=setup_key,
                evaluation_moment=evaluation_moment,
            )
            candidate.conviction_sizing = conviction_sizing

        open_on_symbol = sum(
            1 for p in self._risk_controller.portfolio_snapshot().open_positions
            if p.symbol == candidate.symbol
        )
        trend_score = None
        trend_quality = None
        if allocation is not None:
            trend_score = allocation.trend_strength.score
            trend_quality = allocation.trend_strength.quality
        trade_mode = "scalp" if scalp_entry else (
            candidate.harvest.mode if candidate.harvest.allowed else "harvest"
        )

        harvest_band = candidate.harvest_score.band if candidate.harvest_score else None
        archetype_mult = (
            candidate.archetype_check.risk_multiplier if candidate.archetype_check else None
        )

        target_pips = abs(thesis.take_profit_2 - entry_price) / pip_size if pip_size > 0 else 10.0
        stop_pips = abs(entry_price - stop_loss) / pip_size
        construction_expected_r = None
        if stop_pips > 0:
            construction_expected_r = max(0.0, target_pips - candidate.spread_pips) / stop_pips

        exec_quality = self._intelligence.evaluate_entry_execution(
            symbol=candidate.symbol,
            side=side,
            spread_pips=candidate.spread_pips,
            spread_limit=candidate.spread_limit,
            stop_pips=stop_pips,
            target_pips=target_pips,
            candidate=candidate,
        )

        maturity = self._intelligence.evaluate_trade_maturity(
            symbol=candidate.symbol,
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=take_profit,
            setup_kind=setup_kind,
            candidate=candidate,
            story_clear=story_clear,
            invalidation_level=thesis.invalidation_level,
            conviction_score=conviction.conviction_score,
            execution_score=exec_quality.execution_score,
        )
        scout_commit = maturity.scout_commit
        if scout_commit is not None:
            if scout_commit.participation_stage == "exit" or scout_commit.size_multiplier <= 0:
                reject_reason = f"Thesis rejected at entry — {scout_commit.explanation}"
                return (
                    EntryDecision(action="reject", explanation=reject_reason, lot_size=0.0),
                    RiskDecision(approved=False, reason=reject_reason, lot_size=0.0),
                )
            if (
                scout_commit.effective_setup_kind == "micro_scalp"
                and setup_kind == "harvest"
            ):
                setup_kind = "micro_scalp"
                scalp_entry = True
                harvest_path = False
                trade_mode = "scalp"

        portfolio_construction = None
        if self._portfolio_engine is not None and allocation is not None:
            target_pips_val = max(target_pips, 1.0)
            loss_streak = 0
            dd_risk = self._risk_controller.drawdown_risk
            key = (candidate.symbol.strip().upper(), trade_mode.strip().lower())
            streak_state = dd_risk._loss_streaks.get(key)
            if streak_state is not None:
                loss_streak = streak_state.consecutive_losses
            valid_story = self._expectancy.story_actionable(
                candidate.brain_story,  # type: ignore[arg-type]
                candidate.market_story,
            ) or candidate.harvest.allowed
            portfolio_construction = self._portfolio_engine.construct(
                symbol=candidate.symbol,
                side=side,  # type: ignore[arg-type]
                allocation=allocation,
                portfolio=self._risk_controller.portfolio_snapshot(),
                spread_pips=candidate.spread_pips,
                target_pips=target_pips_val,
                mode=trade_mode,
                loss_streak=loss_streak,
                trace_id=candidate.trace_id,
                evaluation_moment=evaluation_moment,
                base_risk_pct=float(self._config.risk.per_trade_pct),
                market_story=candidate.market_story,
                story_forecast=candidate.story_forecast,
                valid_story=valid_story,
                setup_kind=setup_kind,
                candles=candidate.candles,
                pair_conviction=conviction.conviction_score,
                expected_r=construction_expected_r,
            )
            candidate.portfolio_construction = portfolio_construction

        forecast_conf = (
            candidate.story_forecast.confidence
            if candidate.story_forecast
            else (candidate.narrative_forecast.confidence if candidate.narrative_forecast else 0.0)
        )
        effective_target = target_pips
        expected_r = None
        if stop_pips > 0:
            expected_r = max(0.0, effective_target - candidate.spread_pips) / stop_pips

        harvest_score_val = (
            candidate.harvest_score.score if candidate.harvest_score is not None else None
        )
        risk_eval = self._risk_controller.evaluate(
            symbol=candidate.symbol,
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            trace_id=candidate.trace_id,
            mode=trade_mode,
            trend_score=trend_score,
            trend_quality=trend_quality,
            harvest_score_band=harvest_band,
            harvest_score=harvest_score_val,
            archetype_risk_multiplier=archetype_mult,
            is_addon=open_on_symbol > 0,
            evaluation_moment=evaluation_moment,
            portfolio_construction=portfolio_construction,
            spread_pips=candidate.spread_pips,
            target_pips=effective_target,
            forecast_confidence=forecast_conf,
            expected_r=expected_r,
        )

        min_bias: float | None = None
        min_swings: int | None = None
        dynamic_mult = 1.0
        if allocation is not None:
            min_bias = allocation.confirmation.min_bias_confidence
            min_swings = allocation.confirmation.min_structure_swings
            dynamic_mult = allocation.maximiser.risk_multiplier
            if selection is not None:
                dynamic_mult = min(dynamic_mult, selection.risk_multiplier)
            if candidate.archetype_check is not None:
                dynamic_mult = min(dynamic_mult, candidate.archetype_check.risk_multiplier)
            if candidate.dynamic_pip_target is not None:
                dynamic_mult = min(dynamic_mult, candidate.dynamic_pip_target.risk_multiplier)
        elif selection is not None:
            dynamic_mult = selection.risk_multiplier
            if selection.require_heavy_confirmation:
                min_bias = self._entry_engine.config.min_bias_confidence + 0.1
                min_swings = self._entry_engine.config.min_structure_swings + 1

        entry_context = EntryContext(
            symbol=candidate.symbol,
            bias=candidate.bias,
            structure=candidate.structure,
            regime=candidate.regime,
            momentum=candidate.micro_scalp,
            current_spread=candidate.spread_pips,
            spread_limit=candidate.spread_limit,
            entry_price=entry_price,
            stop_loss=stop_loss,
            portfolio=risk_eval.portfolio,
            risk_manager=self._risk_controller.risk_manager,
            trace_id=candidate.trace_id,
            min_bias_confidence=min_bias,
            min_structure_swings=min_swings,
            candles=candidate.candles.get("M5"),
            conviction=conviction,
            market_regime_intelligence=candidate.market_regime_intelligence,
            range_intelligence=candidate.range_intelligence,
            trend_quality=candidate.trend_quality,
            scalping_intelligence=candidate.scalping_intelligence,
            expected_target_pips=effective_target,
            execution_quality=exec_quality,
            patience_ready=patience_ready,
            patience_explanation=patience_explanation,
            resolved_side=side,  # type: ignore[arg-type]
            cognitive_decision=candidate.cognitive_decision,
        )
        entry = self._entry_engine.evaluate(entry_context)
        if entry.action in {"enter_buy", "enter_sell"} and thesis.is_tradeable:
            scout_label = ""
            if scout_commit is not None:
                scout_label = (
                    f" [{scout_commit.scout_or_commit}/{scout_commit.participation_stage}]"
                )
            entry_explanation = (
                f"{entry.explanation} Thesis: {thesis.entry_reason}.{scout_label} "
                f"Maturity {maturity.maturity_score}/100 ({maturity.maturity_stage}, "
                f"{maturity.commitment}). {maturity.explanation}. "
                f"{thesis.management_plan}"
            )
            entry = EntryDecision(
                action=entry.action,
                explanation=entry_explanation,
                lot_size=entry.lot_size,
                confirmations=entry.confirmations,
            )
        risk = risk_eval.decision
        lot_size = entry.lot_size if entry.lot_size > 0 else risk.lot_size
        if conviction_sizing is not None and conviction_sizing.position_size > 0:
            lot_size = conviction_sizing.position_size
        if defensive_scale < 0.999:
            dynamic_mult = min(dynamic_mult, defensive_scale)
        if individual_plan.entry_allowed and individual_plan.size_multiplier < 0.999:
            dynamic_mult = min(dynamic_mult, individual_plan.size_multiplier)
        if conviction.conviction_level != "no_trade" and conviction.size_multiplier < 0.999:
            dynamic_mult = min(dynamic_mult, conviction.size_multiplier)
        if conviction.staged_entry and conviction.initial_size_fraction < 0.999:
            dynamic_mult = min(dynamic_mult, conviction.initial_size_fraction)
        dynamic_mult = min(
            dynamic_mult,
            participation.effective_size_multiplier,
            exec_quality.entry.size_multiplier,
            self._intelligence.session_size_multiplier(candidate),
            self._intelligence.news_size_multiplier(candidate),
        )
        if maturity.size_multiplier > 0:
            dynamic_mult = min(dynamic_mult, maturity.size_multiplier)
        if maturity.commitment == "aggressive" and maturity.maturity_stage == "ready":
            dynamic_mult = min(1.0, max(dynamic_mult, 0.92))
        elif maturity.commitment in {"probe", "micro_probe"}:
            dynamic_mult = min(dynamic_mult, maturity.size_multiplier)
        storyteller_mult = 1.0
        if candidate.market_mind_decision is not None:
            storyteller_mult = float(candidate.market_mind_decision.allocation_multiplier)
        elif candidate.storyteller_decision is not None:
            storyteller_mult = float(candidate.storyteller_decision.allocation_multiplier)
        if cio_mult < 0.999:
            dynamic_mult = min(dynamic_mult, cio_mult)
        if storyteller_mult < 0.999:
            dynamic_mult = min(dynamic_mult, storyteller_mult)
        if candidate.symbol.strip().upper() == "GBPJPY" and maturity.maturity_stage == "ready":
            dynamic_mult = min(dynamic_mult, maturity.size_multiplier)
        if candidate.scalping_intelligence is not None:
            scalp_quality = float(
                getattr(candidate.scalping_intelligence, "scalp_quality_score", 50) or 50
            )
            scalp_expectancy = float(
                getattr(candidate.scalping_intelligence, "scalp_expectancy_score", 50) or 50
            )
            if scalp_quality < 45 or scalp_expectancy < 40:
                dynamic_mult = min(dynamic_mult, 0.75)
            elif setup_kind == "micro_scalp" and scalp_quality >= 70 and scalp_expectancy >= 60:
                dynamic_mult = min(1.0, max(dynamic_mult, 0.90))
        if candidate.market_regime_intelligence is not None:
            strategy_bias = str(
                getattr(candidate.market_regime_intelligence, "strategy_bias", "") or ""
            )
            current_regime = str(
                getattr(candidate.market_regime_intelligence, "market_regime", "") or ""
            )
            if strategy_bias == "range_logic" and setup_kind == "harvest":
                dynamic_mult = min(dynamic_mult, 0.70)
            if strategy_bias == "prepare_breakout" and current_regime != "breakout_in_progress":
                dynamic_mult = min(dynamic_mult, 0.75)
            if strategy_bias == "reduced_risk_trend":
                dynamic_mult = min(dynamic_mult, 0.65)
            if current_regime == "distribution" and side == "buy":
                dynamic_mult = min(dynamic_mult, 0.55)
            if current_regime == "accumulation" and side == "sell":
                dynamic_mult = min(dynamic_mult, 0.55)
        if candidate.range_intelligence is not None:
            location = str(getattr(candidate.range_intelligence, "price_location", "") or "")
            range_status = str(getattr(candidate.range_intelligence, "range_status", "") or "")
            if range_status in {"horizontal_range", "diagonal_range", "triangular_range"}:
                if side == "buy" and location not in {"near_support", "lower_half"}:
                    dynamic_mult = min(dynamic_mult, 0.75)
                if side == "sell" and location not in {"near_resistance", "upper_half"}:
                    dynamic_mult = min(dynamic_mult, 0.75)
        if dynamic_mult < 0.999 and lot_size > 0:
            lot_size = round(max(0.01, lot_size * max(dynamic_mult, 0.15)), 2)
        if entry.lot_size > 0 or risk.approved:
            risk = RiskDecision(
                approved=risk.approved and lot_size > 0,
                reason=(
                    f"{risk.reason} (dynamic risk {dynamic_mult:.0%})"
                    if dynamic_mult < 0.999
                    else risk.reason
                ),
                lot_size=lot_size,
            )
        if (
            self._projection_learning is not None
            and individual_plan.entry_allowed
            and harvest_path
            and entry.action in {"enter_buy", "enter_sell"}
        ):
            self._projection_learning.record_pending_entry(
                trade_id=candidate.trace_id,
                personality=individual_plan.personality.kind,
                side=side,
                in_active_session=is_in_trading_session(
                    self._config, evaluation_moment
                ),
                thesis_confidence=thesis.thesis_confidence,
                projected_reward_r=individual_plan.readiness.projected_reward_r,
                lifecycle_pattern=(
                    f"{thesis.market_context.market_phase}|"
                    f"{thesis.market_context.trend_direction}|"
                    f"{thesis.thesis_direction}"
                ),
                retracement_pattern=thesis.pullback_analysis.pullback_type,
                reversal_pattern=(
                    f"reversal_pressure_{thesis.market_context.reversal_pressure_score:.2f}"
                ),
                distribution_pattern=(
                    f"distribution_{thesis.market_context.distribution_probability:.2f}"
                ),
            )
        if (
            harvest_path
            and entry.action in {"enter_buy", "enter_sell"}
            and patience_decision is not None
            and patience_decision.opportunity is not None
        ):
            self._expectancy.record_pending_entry(
                trade_id=candidate.trace_id,
                symbol=candidate.symbol,
                entry_type=patience_decision.opportunity.entry_type,
                evaluation_moment=evaluation_moment,
            )
        return entry, risk


def _primary_regime_label(candidate: TradeCandidate) -> str:
    if candidate.market_regime_intelligence is not None:
        primary = getattr(candidate.market_regime_intelligence, "primary_regime", None)
        if primary:
            return str(primary)
        regime = getattr(candidate.market_regime_intelligence, "market_regime", None)
        if regime:
            return str(regime)
    if candidate.regime is not None:
        return str(candidate.regime.regime)
    return "unknown"


def _evolution_path(evolution_state: object | None) -> tuple[str, ...]:
    if evolution_state is None:
        return ()
    return (
        f"novel:{getattr(evolution_state, 'macro_story', '')}",
        f"chapter:{getattr(evolution_state, 'chapter_story', '')}",
        f"paragraph:{getattr(evolution_state, 'paragraph_story', '')}",
        f"evolution:{getattr(evolution_state, 'probable_evolution', '')}",
    )
