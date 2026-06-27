"""Tests for risk.conviction_position_sizing."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from brain.market_story_engine import LiquidityTarget, MarketStory, TrappedTraderZone
from execution.patience_engine import EntryOpportunity
from risk.conviction_position_sizing import (
    ConvictionPositionSizer,
    RISK_BY_SCORE,
    SetupExpectancy,
)
from risk.models import RiskLimits
from strategies.models import MarketContext, StructureEvent, SwingPoint


def _story(confidence: float = 78.0, *, strength: float = 70.0) -> MarketStory:
    return MarketStory(
        symbol="EURUSD",
        timeframe="H4",
        direction="bullish",
        confidence=confidence,
        controlling_side="buyers",
        structure_state="bullish moderate; sell-side sweep reclaimed",
        liquidity_targets=(LiquidityTarget("session high", 1.1100, "buy_side"),),
        trapped_traders=(
            TrappedTraderZone("shorts trapped below sweep", 1.1010, 1.1025, "shorts"),
        ),
        next_objective=1.1100,
        invalidation_level=1.1000,
        narrative="test",
        trend_strength=strength,
    )


def _structure() -> MarketContext:
    bos = StructureEvent(
        kind="bos_bullish",
        bar_index=10,
        time=None,
        price=1.1050,
        reference_price=1.1040,
        description="bullish BOS",
    )
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend="bullish",
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=(SwingPoint(5, None, 1.1080, "high"),),
        swing_lows=(SwingPoint(8, None, 1.1020, "low"),),
        structure_events=(bos,),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=bos,
        last_choch=None,
    )


def _entry(entry_type: str = "liquidity_sweep_rejection", confidence: float = 82.0) -> EntryOpportunity:
    return EntryOpportunity(
        entry_price=1.1035,
        entry_type=entry_type,  # type: ignore[arg-type]
        confidence=confidence,
        stop_loss=1.1020,
        explanation="sweep reclaim",
        side="buy",
    )


class TestRiskTiers:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (55, 0.25),
            (65, 0.50),
            (80, 1.00),
            (92, 2.00),
            (45, 0.15),
        ],
    )
    def test_risk_percent_tiers(self, score: float, expected: float) -> None:
        assert ConvictionPositionSizer()._risk_percent_for_score(score) == expected


class TestConvictionSizing:
    def test_high_evidence_gets_full_risk_tier(self) -> None:
        result = ConvictionPositionSizer(limits=RiskLimits(per_trade_pct=2.0)).size(
            symbol="EURUSD",
            side="buy",
            balance=10_000.0,
            entry_price=1.1035,
            stop_loss=1.1020,
            take_profit=1.1100,
            story=_story(confidence=88.0, strength=82.0),
            structure=_structure(),
            entry_opportunity=_entry(),
            setup_expectancy=SetupExpectancy(
                average_r=0.65,
                win_rate=0.62,
                profit_factor=1.9,
                sample_size=12,
                setup_label="ny_liquidity_sweep",
            ),
        )
        assert result.score >= 75.0
        assert result.risk_percent >= 1.0
        assert result.position_size > 0
        assert "Conviction" in result.explanation

    def test_moderate_evidence_gets_half_percent(self) -> None:
        weak_structure = MarketContext(
            symbol="EURUSD",
            timeframe="H1",
            trend="ranging",
            higher_highs=False,
            higher_lows=True,
            lower_highs=False,
            lower_lows=False,
            swing_highs=(SwingPoint(5, None, 1.1080, "high"),),
            swing_lows=(SwingPoint(8, None, 1.1020, "low"),),
            structure_events=(),
            support_zones=(),
            resistance_zones=(),
            liquidity_zones=(),
            last_bos=None,
            last_choch=None,
        )
        result = ConvictionPositionSizer().size(
            symbol="EURUSD",
            side="buy",
            balance=10_000.0,
            entry_price=1.1035,
            stop_loss=1.1020,
            take_profit=1.1048,
            story=_story(confidence=64.0, strength=52.0),
            structure=weak_structure,
            entry_opportunity=_entry("pullback_into_value", 66.0),
        )
        assert 60.0 <= result.score < 75.0
        assert result.risk_percent == 0.50

    def test_emotional_pressure_caps_risk(self) -> None:
        sizer = ConvictionPositionSizer()
        baseline = sizer.size(
            symbol="EURUSD",
            side="buy",
            balance=10_000.0,
            entry_price=1.1035,
            stop_loss=1.1020,
            take_profit=1.1100,
            story=_story(confidence=90.0, strength=85.0),
            structure=_structure(),
            entry_opportunity=_entry(),
            setup_expectancy=SetupExpectancy(
                average_r=0.8,
                win_rate=0.65,
                profit_factor=2.1,
                sample_size=20,
            ),
        )
        pressured = sizer.size(
            symbol="EURUSD",
            side="buy",
            balance=10_000.0,
            entry_price=1.1035,
            stop_loss=1.1020,
            take_profit=1.1100,
            story=_story(confidence=90.0, strength=85.0),
            structure=_structure(),
            entry_opportunity=_entry(),
            setup_expectancy=SetupExpectancy(
                average_r=0.8,
                win_rate=0.65,
                profit_factor=2.1,
                sample_size=20,
            ),
            revenge_trading=True,
            recovery_mode=True,
            loss_streak=4,
        )
        assert baseline.risk_percent >= 1.0
        assert pressured.risk_percent <= 0.50
        assert pressured.risk_percent < baseline.risk_percent
        assert "capped" in pressured.explanation.lower() or "streak" in pressured.explanation.lower()

    def test_components_present(self) -> None:
        result = ConvictionPositionSizer().size(
            symbol="EURUSD",
            side="buy",
            balance=10_000.0,
            entry_price=1.1035,
            stop_loss=1.1020,
            story=_story(),
            structure=_structure(),
            entry_opportunity=_entry(),
        )
        assert set(result.components) == {
            "market_story",
            "structure",
            "liquidity",
            "entry_timing",
            "risk_reward",
            "historical_expectancy",
        }

    def test_risk_tiers_documented(self) -> None:
        assert RISK_BY_SCORE[0] == (90.0, 2.00)
        assert (60.0, 0.50) in RISK_BY_SCORE
