"""Shared pipeline data models (import-safe, no stage wiring)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from execution.models import EntryDecision
from risk.models import RiskDecision

if TYPE_CHECKING:
    from council.opportunity_hunter_council import CouncilConsensus
    from intelligence.asset_trend_analyzer import AssetTrendSnapshot
    from intelligence.dynamic_strategy_selector import StrategySelection
    from intelligence.dynamic_pip_targets import DynamicPipTargetDecision
    from intelligence.forecast_feedback import ForecastOutcome
    from intelligence.harvest_archetype_memory import ArchetypeCheckResult
    from intelligence.harvest_opportunity_score import HarvestOpportunityScore
    from intelligence.indicator_confirmation import IndicatorConfirmation
    from intelligence.market_narrative_engine import MarketNarrativeResult
    from intelligence.market_story_engine import MarketStoryResult
    from intelligence.narrative_forecast_engine import NarrativeForecastResult
    from intelligence.story_forecast_engine import StoryForecastResult
    from intelligence.opportunity_allocator import OpportunityAllocation
    from portfolio.portfolio_construction import PortfolioConstructionResult
    from strategies.market_regime_engine import MarketRegimeResult
    from strategies.range_intelligence_engine import RangeIntelligenceResult
    from strategies.scalping_intelligence_engine import ScalpingIntelligenceResult
    from strategies.trend_quality_engine import TrendQualityResult
    from strategies.models import (
        HarvestDecision,
        MarketContext,
        MicroScalpSignal,
        MultiTimeframeBiasResult,
        RegimeResult,
    )


@dataclass
class PipelineResult:
    """Accumulated outputs from all pipeline stages for one symbol."""

    symbol: str
    trace_id: str
    bid: float
    ask: float
    spread_pips: float
    spread_limit: float
    opportunity_key: str = ""
    setup_kind: str = "harvest"
    candles: dict[str, pd.DataFrame] = field(default_factory=dict)
    regime: RegimeResult | None = None
    bias: MultiTimeframeBiasResult | None = None
    structure: MarketContext | None = None
    harvest: HarvestDecision | None = None
    micro_scalp: MicroScalpSignal | None = None
    entry: EntryDecision | None = None
    risk: RiskDecision = field(
        default_factory=lambda: RiskDecision(False, "not evaluated", 0.0)
    )
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    pair_allowed: bool = True
    news_allowed: bool = True
    asset_trend: AssetTrendSnapshot | None = None
    strategy_selection: StrategySelection | None = None
    opportunity_allocation: OpportunityAllocation | None = None
    harvest_score: HarvestOpportunityScore | None = None
    archetype_check: ArchetypeCheckResult | None = None
    dynamic_pip_target: DynamicPipTargetDecision | None = None
    portfolio_construction: PortfolioConstructionResult | None = None
    market_story: MarketStoryResult | None = None
    story_forecast: StoryForecastResult | None = None
    market_narrative: MarketNarrativeResult | None = None
    narrative_forecast: NarrativeForecastResult | None = None
    council_consensus: CouncilConsensus | None = None
    indicator_confirmation: IndicatorConfirmation | None = None
    thesis: object | None = None
    individual_trade_plan: object | None = None
    conviction_assessment: object | None = None
    opportunity_assessment: object | None = None
    decision_result: object | None = None
    execution_quality: object | None = None
    institutional_structure: object | None = None
    liquidity_sweep: object | None = None
    false_breakout: object | None = None
    market_lifecycle: object | None = None
    reversal_pressure: object | None = None
    session_intelligence: object | None = None
    news_context: object | None = None
    trade_maturity: object | None = None
    location_quality: object | None = None
    timing_quality: object | None = None
    market_acceptance: object | None = None
    market_regime_intelligence: MarketRegimeResult | None = None
    range_intelligence: RangeIntelligenceResult | None = None
    trend_quality: TrendQualityResult | None = None
    scalping_intelligence: ScalpingIntelligenceResult | None = None
    forecast_outcome: ForecastOutcome | None = None
    brain_story: object | None = None
    patience_decision: object | None = None
    conviction_sizing: object | None = None
    cognitive_decision: object | None = None
    storyteller_decision: object | None = None
    market_picture: object | None = None
    market_mind_decision: object | None = None
    reality_decision: object | None = None
