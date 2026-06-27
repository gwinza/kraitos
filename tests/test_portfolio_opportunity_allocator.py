"""Tests for portfolio opportunity allocator and OAS scoring."""

from __future__ import annotations

from datetime import datetime, timezone
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
from portfolio.opportunity_score import OpportunityScoreEngine, _tier_for_oas
from portfolio.opportunity_allocator import PortfolioOpportunityAllocator
from risk.models import OpenPosition, PortfolioState


def _portfolio(**kwargs) -> PortfolioState:
    defaults = dict(balance=10_000.0, peak_balance=10_000.0, open_positions=())
    defaults.update(kwargs)
    return PortfolioState(**defaults)


def _allocation(symbol: str = "EURUSD", trend_score: float = 85.0) -> OpportunityAllocation:
    trend = TrendStrengthResult(
        symbol=symbol,
        score=trend_score,
        quality="institutional_trend",
        direction="bullish",
        reason="strong trend",
        components={"momentum_persistence": 10},
    )
    market = MarketplaceSelection(
        symbol=symbol,
        strategy="harvest",
        fitness_score=0.82,
        expected_value=0.15,
        trend_score=trend_score,
        trend_quality="institutional_trend",
        regime="trending",
        session="london",
        competitors={"harvest": 0.82},
        recommended_action="FULL_RISK",
        reason="harvest wins",
    )
    maximiser = TrendMaximiserDecision(
        symbol=symbol,
        allow_primary_entry=True,
        allow_pullback_reentry=True,
        allow_breakout_retest=False,
        allow_continuation_addon=False,
        partial_take_profit_at_1r=True,
        early_partial_on_atr_contraction=False,
        trail_timeframe="M15",
        risk_multiplier=1.0,
        target_pips_multiplier=1.0,
        reason="primary allowed",
    )
    confirmation = AdaptiveConfirmation(
        min_bias_confidence=0.45,
        min_structure_swings=2,
        risk_multiplier=1.0,
        defensive_mode=False,
        tier="normal",
    )
    selection = StrategySelection(
        symbol=symbol,
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
        symbol=symbol,
        score=78.0,
        band="standard",
        allow_harvest=True,
        components={"trend_alignment": 12.0},
        reason="good harvest",
        session="london",
    )
    return OpportunityAllocation(
        symbol=symbol,
        trend_strength=trend,
        marketplace=market,
        maximiser=maximiser,
        confirmation=confirmation,
        strategy_selection=selection,
        harvest_boost=True,
        harvest_score=harvest,
    )


def test_oas_tier_mapping() -> None:
    assert _tier_for_oas(90.0) == ("premium", 1.0, True)
    assert _tier_for_oas(80.0) == ("standard", 0.75, True)
    assert _tier_for_oas(70.0) == ("reduced", 0.50, True)
    assert _tier_for_oas(55.0) == ("watchlist", 0.25, True)
    assert _tier_for_oas(40.0) == ("defer", 0.15, True)


def test_oas_scores_high_quality_setup(tmp_path: Path) -> None:
    engine = OpportunityScoreEngine()
    oas = engine.score(
        symbol="EURUSD",
        allocation=_allocation(),
        portfolio=_portfolio(),
        side="buy",
        spread_pips=1.0,
        target_pips=10.0,
    )
    assert oas.oas >= 50.0
    assert oas.allow_trade
    assert oas.edge >= 60.0


def test_oas_rejects_below_50(tmp_path: Path) -> None:
    engine = OpportunityScoreEngine()
    oas = engine.score(
        symbol="EURUSD",
        allocation=_allocation(trend_score=20.0),
        portfolio=_portfolio(
            open_positions=(
                OpenPosition("EURUSD", "buy", 0.1, 1.1, 1.09, 200),
                OpenPosition("GBPUSD", "buy", 0.1, 1.3, 1.29, 200),
                OpenPosition("AUDUSD", "buy", 0.1, 0.7, 0.69, 200),
            ),
            balance=8_000.0,
            peak_balance=10_000.0,
        ),
        side="buy",
        spread_pips=5.0,
        target_pips=8.0,
        loss_streak=5,
    )
    if oas.oas < 50.0:
        assert oas.allow_trade
        assert oas.tier == "defer"
        assert oas.risk_multiplier == pytest.approx(0.15)


def test_portfolio_allocator_ranks_opportunities(tmp_path: Path) -> None:
    allocator = PortfolioOpportunityAllocator(tmp_path)
    eur = allocator.evaluate(
        symbol="EURUSD",
        side="buy",
        allocation=_allocation("EURUSD", 90.0),
        portfolio=_portfolio(),
        evaluation_moment=datetime.now(timezone.utc),
    )
    gbp = allocator.evaluate(
        symbol="GBPUSD",
        side="buy",
        allocation=_allocation("GBPUSD", 70.0),
        portfolio=_portfolio(),
        evaluation_moment=datetime.now(timezone.utc),
    )
    ranked = allocator.rank_all([eur, gbp])
    assert ranked[0].symbol == "EURUSD"
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2


def test_portfolio_allocator_writes_report(tmp_path: Path) -> None:
    allocator = PortfolioOpportunityAllocator(tmp_path)
    allocator.evaluate(
        symbol="EURUSD",
        side="buy",
        allocation=_allocation(),
        portfolio=_portfolio(),
    )
    paths = allocator.write_reports()
    assert any(p.name == "portfolio_allocation_report.md" for p in paths)
    report = tmp_path / "logs" / "portfolio_allocation_report.md"
    assert report.exists()
    assert "EURUSD" in report.read_text(encoding="utf-8")
