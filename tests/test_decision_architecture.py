"""Tests for next-generation decision architecture engines."""

from __future__ import annotations

import pandas as pd
import pytest

from strategies.adaptive_aggression_engine import AdaptiveAggressionEngine
from strategies.conviction_engine import ConvictionEngine
from strategies.decision_architecture import DecisionArchitecture
from strategies.models import (
    MarketContext,
    MicroScalpSignal,
    MultiTimeframeBiasResult,
    SwingPoint,
    TimeframeBiasDetail,
)
from strategies.opportunity_cost_engine import OpportunityCostEngine
from strategies.opportunity_engine import OpportunityEngine
from strategies.thesis_engine import ThesisEngine


def _bias(*, bullish_h4: bool = True, confidence: float = 0.6) -> MultiTimeframeBiasResult:
    layers = [
        TimeframeBiasDetail("H4", "bullish" if bullish_h4 else "bearish", 0.55, "macro"),
        TimeframeBiasDetail("H8", "bullish", 0.50, "macro"),
    ]
    return MultiTimeframeBiasResult(
        bias="bullish",
        confidence=confidence,
        explanation="test",
        layers=tuple(layers),
    )


def _structure(trend: str = "bullish") -> MarketContext:
    swing = SwingPoint(
        bar_index=1,
        time=pd.Timestamp("2025-01-10", tz="UTC"),
        price=1.10,
        kind="low",
    )
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend=trend,  # type: ignore[arg-type]
        higher_highs=trend == "bullish",
        higher_lows=trend == "bullish",
        lower_highs=trend == "bearish",
        lower_lows=trend == "bearish",
        swing_highs=(swing,),
        swing_lows=(swing,),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


def _m5_consolidation() -> pd.DataFrame:
    closes = [1.1000 + i * 0.0001 for i in range(20)]
    closes[-3:] = [1.1020, 1.10201, 1.10202]
    rows = []
    for i, close in enumerate(closes):
        rows.append(
            {
                "time": pd.Timestamp("2025-01-10", tz="UTC") + pd.Timedelta(minutes=5 * i),
                "open": close,
                "high": close + 0.00005,
                "low": close - 0.00005,
                "close": close,
                "tick_volume": 100,
                "spread": 1.0,
            }
        )
    return pd.DataFrame(rows)


class TestThesisEngine:
    def test_builds_complete_thesis(self) -> None:
        thesis = ThesisEngine().build(
            symbol="EURUSD",
            side="buy",
            entry_price=1.1000,
            structure=_structure(),
            bias=_bias(),
            market_story="Liquidity sweep reclaim",
            opportunity_type="liquidity_sweep",
            pip_size=0.0001,
        )
        assert thesis.is_tradeable
        assert thesis.direction == "buy"
        assert thesis.market_story
        assert thesis.entry_reason
        assert thesis.invalidation_reason
        assert thesis.expected_path
        assert thesis.risk > 0
        assert thesis.reward > 0
        assert thesis.confidence > 0

    def test_rejects_bad_geometry(self) -> None:
        thesis = ThesisEngine().build(
            symbol="EURUSD",
            side="invalid",
            entry_price=1.1000,
            structure=None,
            bias=None,
        )
        assert not thesis.is_tradeable


class TestOpportunityEngine:
    def test_finds_reasons_to_trade(self) -> None:
        opp = OpportunityEngine().evaluate(
            side="buy",
            bias=_bias(),
            structure=_structure(),
            story_clear=True,
            story_text="Pullback continuation",
            opportunity_type="pullback_continuation",
            momentum=MicroScalpSignal(action="buy", reason="M1 impulse", target_pips=5.0),
        )
        assert opp.opportunity_score >= 35
        assert opp.reasons_to_trade
        assert opp.expected_R > 0
        assert opp.participation_recommendation in {
            "aggressive", "normal", "probe", "watchlist", "monitor"
        }


class TestConvictionEngine:
    def test_aggressive_high_conviction(self) -> None:
        m5 = _m5_consolidation()
        assessment = ConvictionEngine().evaluate(
            side="buy",
            bias=_bias(),
            structure=_structure(),
            story="Liquidity sweep reclaim",
            story_clear=True,
            opportunity_type="liquidity_sweep",
            opportunity_score=0.85,
            candles={"M5": m5},
            momentum=MicroScalpSignal(action="buy", reason="M1 impulse", target_pips=5.0),
            invalidation_level=1.0980,
            expected_r=1.5,
            structure_quality=0.75,
        )
        assert assessment.conviction_score >= 61
        assert assessment.participation_mode in {"normal", "aggressive", "probe"}
        assert assessment.invalidators
        assert assessment.module_contributions

    def test_uncertain_becomes_probe_not_reject(self) -> None:
        assessment = ConvictionEngine().evaluate(
            side="buy",
            bias=_bias(bullish_h4=False, confidence=0.3),
            structure=_structure(trend="bearish"),
            story="Unclear chop",
            story_clear=False,
            expected_r=0.8,
            structure_quality=0.65,
        )
        assert assessment.participation_mode in {"probe", "watchlist", "avoid"}
        assert assessment.conviction_level != "no_trade" or assessment.anti_paralysis_override
        if assessment.anti_paralysis_override:
            assert assessment.participation_mode == "probe"

    def test_probe_timing_allows_reduced_entry(self) -> None:
        from strategies.conviction_engine import ConvictionAssessment

        m5 = _m5_consolidation()
        assessment = ConvictionAssessment(
            conviction_score=52.0,
            conviction_class="moderate",
            participation_mode="probe",
            story="Developing setup",
            invalidators=("H1 swing low breaks",),
            evidence=("Structure supports",),
            timing_mode="standard",
            size_multiplier=0.35,
        )
        allowed, detail = ConvictionEngine.entry_timing_allowed(
            assessment, side="buy", candles=m5
        )
        assert allowed
        assert "probe" in detail.lower() or "normal" in detail.lower()


class TestOpportunityCostEngine:
    def test_detects_over_filtering(self) -> None:
        engine = OpportunityCostEngine()
        for _ in range(6):
            engine.record_rejected_winner(
                symbol="EURUSD", side="buy", missed_r=1.5, missed_profit=150.0
            )
        for _ in range(3):
            engine.record_accepted_loser(symbol="EURUSD", side="buy", lost_r=0.5)
        snapshot = engine.assess()
        assert snapshot.over_filtering
        assert snapshot.filter_adjustment == "reduce_filtering"
        assert engine.filter_relaxation_multiplier() > 1.0


class TestAdaptiveAggressionEngine:
    def test_surge_on_strong_reading(self) -> None:
        engine = AdaptiveAggressionEngine()
        for _ in range(10):
            engine.record_outcome(
                symbol="EURUSD",
                side="buy",
                r_multiple=1.2,
                thesis_correct=True,
            )
        assessment = engine.assess()
        assert assessment.aggression_multiplier >= 1.0
        assert assessment.profit_factor > 1.0

    def test_defensive_on_weak_reading(self) -> None:
        engine = AdaptiveAggressionEngine()
        for _ in range(10):
            engine.record_outcome(
                symbol="EURUSD",
                side="buy",
                r_multiple=-0.8,
                thesis_correct=False,
            )
        assessment = engine.assess()
        assert assessment.aggression_multiplier < 1.0
        assert assessment.aggression_mode == "defensive"


class TestDecisionArchitecture:
    def test_end_to_end_participation(self) -> None:
        result = DecisionArchitecture().evaluate(
            symbol="EURUSD",
            side="buy",
            entry_price=1.1000,
            bias=_bias(),
            structure=_structure(),
            market_story="Pullback continuation after sweep",
            story_clear=True,
            opportunity_type="pullback_continuation",
            candles={"M5": _m5_consolidation()},
            momentum=MicroScalpSignal(action="buy", reason="M1", target_pips=5.0),
            pip_size=0.0001,
        )
        assert result.thesis.is_tradeable
        assert result.opportunity.opportunity_score > 0
        assert result.conviction.conviction_score > 0
        assert result.effective_size_multiplier > 0
