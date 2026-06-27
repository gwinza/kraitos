"""Tests for portfolio opportunity classifier."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.offline

from intelligence.dynamic_strategy_selector import StrategySelection
from intelligence.harvest_opportunity_score import HarvestOpportunityScore
from intelligence.opportunity_allocator import AdaptiveConfirmation, OpportunityAllocation
from intelligence.strategy_marketplace import MarketplaceSelection
from intelligence.trend_maximiser import TrendMaximiserDecision
from intelligence.trend_strength_engine import TrendStrengthResult
from portfolio.opportunity_classifier import OpportunityClassifier, RISK_RANGES


def _allocation(trend_score: float = 85.0) -> OpportunityAllocation:
    trend = TrendStrengthResult(
        symbol="EURUSD",
        score=trend_score,
        quality="institutional_trend",
        direction="bullish",
        reason="strong",
        components={"momentum_persistence": 10},
    )
    market = MarketplaceSelection(
        symbol="EURUSD",
        strategy="harvest",
        fitness_score=0.82,
        expected_value=0.15,
        trend_score=trend_score,
        trend_quality="institutional_trend",
        regime="trending",
        session="london",
        competitors={"harvest": 0.82},
        recommended_action="FULL_RISK",
        reason="harvest",
    )
    maximiser = TrendMaximiserDecision(
        symbol="EURUSD",
        allow_primary_entry=True,
        allow_pullback_reentry=True,
        allow_breakout_retest=False,
        allow_continuation_addon=False,
        partial_take_profit_at_1r=True,
        early_partial_on_atr_contraction=False,
        trail_timeframe="M15",
        risk_multiplier=1.0,
        target_pips_multiplier=1.0,
        reason="ok",
    )
    confirmation = AdaptiveConfirmation(
        min_bias_confidence=0.45,
        min_structure_swings=2,
        risk_multiplier=1.0,
        defensive_mode=False,
        tier="normal",
    )
    selection = StrategySelection(
        symbol="EURUSD",
        asset_state="strong_uptrend",
        selected_strategy="harvest",
        trade_mode="harvest",
        allow_harvest=True,
        allow_micro_scalp=False,
        risk_multiplier=1.0,
        require_heavy_confirmation=False,
        reason="test",
        switched=False,
        asset_status="FULL_RISK",
    )
    harvest = HarvestOpportunityScore(
        symbol="EURUSD",
        score=78.0,
        band="standard",
        allow_harvest=True,
        components={"trend_alignment": 12.0},
        reason="good",
        session="london",
    )
    return OpportunityAllocation(
        symbol="EURUSD",
        trend_strength=trend,
        marketplace=market,
        maximiser=maximiser,
        confirmation=confirmation,
        strategy_selection=selection,
        harvest_boost=True,
        harvest_score=harvest,
    )


def _market_story(opp_type: str, conf: float = 72.0):
    story = MagicMock()
    story.opportunity_type = opp_type
    story.overall_confidence = conf
    story.story_clear = True
    return story


def test_classifies_harvest_liquidity_sweep(tmp_path: Path) -> None:
    classifier = OpportunityClassifier(tmp_path)
    result = classifier.classify(
        symbol="EURUSD",
        allocation=_allocation(),
        market_story=_market_story("liquidity_sweep"),
        mode="harvest",
        valid_story=True,
        target_pips=3.0,
    )
    assert result.opportunity_class == "MICRO_HARVEST"
    assert RISK_RANGES["MICRO_HARVEST"][0] <= result.base_risk_pct <= RISK_RANGES["MICRO_HARVEST"][1]
    assert not result.no_trade


def test_classifies_proper_pullback(tmp_path: Path) -> None:
    classifier = OpportunityClassifier(tmp_path)
    result = classifier.classify(
        symbol="EURUSD",
        allocation=_allocation(),
        market_story=_market_story("pullback_continuation", 75.0),
        mode="harvest",
        valid_story=True,
        target_pips=8.0,
    )
    assert result.opportunity_class == "PROPER"
    assert RISK_RANGES["PROPER"][0] <= result.base_risk_pct <= RISK_RANGES["PROPER"][1]


def test_classifies_elite_high_confidence(tmp_path: Path) -> None:
    classifier = OpportunityClassifier(tmp_path)
    forecast = MagicMock()
    forecast.confidence = 88.0
    forecast.opportunity_type = "pullback_continuation"
    result = classifier.classify(
        symbol="EURUSD",
        allocation=_allocation(trend_score=90.0),
        market_story=_market_story("pullback_continuation", 85.0),
        story_forecast=forecast,
        mode="harvest",
        valid_story=True,
        target_pips=8.0,
    )
    assert result.opportunity_class == "ELITE"
    assert RISK_RANGES["ELITE"][0] <= result.base_risk_pct <= RISK_RANGES["ELITE"][1]


def test_no_trade_without_valid_story(tmp_path: Path) -> None:
    classifier = OpportunityClassifier(tmp_path)
    result = classifier.classify(
        symbol="EURUSD",
        valid_story=False,
    )
    assert result.opportunity_class == "NO_TRADE"
    assert result.no_trade


def test_no_trade_emergency_stop(tmp_path: Path) -> None:
    classifier = OpportunityClassifier(tmp_path)
    result = classifier.classify(
        symbol="EURUSD",
        valid_story=True,
        emergency_stop=True,
    )
    assert result.no_trade


def test_classification_report_written(tmp_path: Path) -> None:
    classifier = OpportunityClassifier(tmp_path)
    classifier.classify(
        symbol="EURUSD",
        allocation=_allocation(),
        market_story=_market_story("compression_breakout"),
        valid_story=True,
        target_pips=4.0,
    )
    path = classifier.write_classification_report()
    assert path is not None
    assert "Opportunity Classification Report" in path.read_text(encoding="utf-8")
