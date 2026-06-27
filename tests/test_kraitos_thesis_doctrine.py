"""Tests for Kraitos Thesis Doctrine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.offline

from intelligence.kraitos_thesis_doctrine import (
    KraitosThesisEngine,
    ThesisExitManager,
    reset_thesis_tracker,
)
from strategies.trend_quality_engine import TradeStory, TrendQualityMetrics, TrendQualityResult
from strategies.models import (
    HarvestDecision,
    MarketContext,
    MultiTimeframeBiasResult,
    PriceZone,
    RegimeResult,
    SwingPoint,
    TimeframeBiasDetail,
)


def _swing(kind: str, price: float) -> SwingPoint:
    return SwingPoint(
        bar_index=10,
        time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        price=price,
        kind=kind,  # type: ignore[arg-type]
    )


def _bias(direction: str) -> MultiTimeframeBiasResult:
    layers = tuple(
        TimeframeBiasDetail(tf, direction, 0.75, role)  # type: ignore[arg-type]
        for tf, role in [("H1", "structure"), ("M5", "setup"), ("M1", "precision_entry")]
    )
    return MultiTimeframeBiasResult(
        bias=direction,  # type: ignore[arg-type]
        confidence=0.78,
        explanation="test",
        layers=layers,
    )


def _structure(
    trend: str = "bullish",
    *,
    resistance: float = 1.1050,
    support: float = 1.0950,
) -> MarketContext:
    bullish = trend == "bullish"
    res_zone = PriceZone("resistance", resistance - 0.0005, resistance + 0.0005, resistance, 2, ())
    sup_zone = PriceZone("support", support - 0.0005, support + 0.0005, support, 2, ())
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend=trend,  # type: ignore[arg-type]
        higher_highs=bullish,
        higher_lows=bullish,
        lower_highs=not bullish,
        lower_lows=not bullish,
        swing_highs=(_swing("high", 1.1040), _swing("high", 1.1030)),
        swing_lows=(_swing("low", 1.0980), _swing("low", 1.0970)),
        structure_events=(),
        support_zones=(sup_zone,),
        resistance_zones=(res_zone,),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


class _Story:
    story_clear = True
    current_explanation = "Bullish pullback into demand with continuation expected."
    primary_story = "Pullback continuation"
    opportunity_type = "pullback_continuation"
    overall_confidence = 82.0
    synthesis = None


def _trend_quality_metrics(**kwargs) -> TrendQualityMetrics:
    defaults = {
        "hh_hl_quality": 72,
        "ll_lh_quality": 68,
        "trend_acceleration": 0.55,
        "trend_exhaustion": 0.25,
        "trend_health": 0.72,
        "trend_participation": 0.65,
    }
    defaults.update(kwargs)
    return TrendQualityMetrics(**defaults)


def _trend_quality(
    *,
    phase: str = "healthy_pullback",
    quality: int = 72,
    continuation: float = 0.68,
    reversal: float = 0.22,
) -> TrendQualityResult:
    return TrendQualityResult(
        symbol="EURUSD",
        timeframe="H1",
        trend_direction="bullish",
        trend_quality_score=quality,
        trend_phase=phase,  # type: ignore[arg-type]
        continuation_probability=continuation,
        reversal_probability=reversal,
        regime="trending",
        explanation=f"H1 bullish trend quality {quality}/100: {phase}.",
        trade_story=TradeStory(
            previous_thesis="",
            current_thesis="healthy bullish continuation",
            what_changed="pullback held structure",
            trend_state="stable",
            action="continue",
            explanation="buyers remain in control",
        ),
        metrics=_trend_quality_metrics(),
    )


class _ScalpingIntel:
    suggested_action = "scalp"
    scalp_quality_score = 78
    scalp_expectancy_score = 66
    micro_reversion_state = "continuation_not_stretched"
    micro_breakout_state = "breakout_holding"
    micro_momentum_state = "accelerating"
    explanation = "Scalping intelligence scalp: quality 78/100."
    evidence = ("price accepted above VWAP", "breakout follow-through present")
    thesis_questions = {
        "why_move_immediately": "microstructure supports immediate movement",
        "where_is_liquidity": "bullish_control_above_vwap",
        "who_is_trapped": "late counter-trend participants",
        "what_invalidates": "loss of micro control",
    }

    def to_dict(self) -> dict:
        return {
            "suggested_action": self.suggested_action,
            "scalp_quality_score": self.scalp_quality_score,
            "scalp_expectancy_score": self.scalp_expectancy_score,
            "explanation": self.explanation,
        }


class _RegimeIntel:
    market_regime = "ranging_market"
    regime_confidence = 0.72
    range_quality_score = 68
    breakout_preparation_score = 54
    compression_probability = 0.41
    likely_next_regime = "breakout"
    strategy_bias = "range_logic"
    evidence = ("support respected", "resistance respected")


class _RangeIntel:
    range_status = "horizontal_range"
    support_level = 1.0950
    resistance_level = 1.1050
    range_width = 0.0100
    equilibrium_zone = 1.1000
    range_quality_score = 68
    breakout_risk_score = 54
    price_location = "near_support"
    likely_breakout_direction = "up"
    explanation = "clear range"
    evidence = ("support respected", "resistance respected")

    def to_dict(self) -> dict:
        return {
            "range_status": self.range_status,
            "support_level": self.support_level,
            "resistance_level": self.resistance_level,
            "range_quality_score": self.range_quality_score,
            "breakout_risk_score": self.breakout_risk_score,
        }


def test_valid_bullish_thesis() -> None:
    reset_thesis_tracker()
    engine = KraitosThesisEngine()
    thesis = engine.build_thesis(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        structure=_structure("bullish"),
        bias=_bias("bullish"),
        pip_size=0.0001,
        spread_pips=1.0,
        spread_limit=2.5,
        market_story=_Story(),  # type: ignore[arg-type]
        harvest=HarvestDecision(mode="conditional", allowed=True, target_pips=8.0, reason="ok"),
    )
    assert thesis.is_tradeable
    assert thesis.thesis_direction == "bullish"
    assert thesis.invalidation_level < 1.1000
    assert thesis.stop_loss < 1.1000
    assert thesis.take_profit_1 > 1.1000
    assert thesis.take_profit_2 >= thesis.take_profit_1
    assert thesis.reward_risk_ratio >= 0.8


def test_valid_bearish_thesis() -> None:
    reset_thesis_tracker()
    engine = KraitosThesisEngine()
    bearish = _structure("bearish", resistance=1.1020, support=1.0920)
    bearish = MarketContext(
        symbol=bearish.symbol,
        timeframe=bearish.timeframe,
        trend=bearish.trend,
        higher_highs=bearish.higher_highs,
        higher_lows=bearish.higher_lows,
        lower_highs=bearish.lower_highs,
        lower_lows=bearish.lower_lows,
        swing_highs=(_swing("high", 1.1015),),
        swing_lows=(_swing("low", 1.0900),),
        structure_events=bearish.structure_events,
        support_zones=bearish.support_zones,
        resistance_zones=bearish.resistance_zones,
        liquidity_zones=(),
        last_bos=bearish.last_bos,
        last_choch=bearish.last_choch,
    )
    thesis = engine.build_thesis(
        symbol="EURUSD",
        side="sell",
        entry_price=1.1000,
        structure=bearish,
        bias=_bias("bearish"),
        pip_size=0.0001,
        spread_pips=1.0,
        spread_limit=2.5,
        market_story=_Story(),  # type: ignore[arg-type]
        harvest=HarvestDecision(mode="conditional", allowed=True, target_pips=8.0, reason="ok"),
    )
    assert thesis.is_tradeable
    assert thesis.thesis_direction == "bearish"
    assert thesis.invalidation_level > 1.1000
    assert thesis.stop_loss > 1.1000
    assert thesis.take_profit_1 < 1.1000


def test_rejection_when_invalidation_missing() -> None:
    reset_thesis_tracker()
    engine = KraitosThesisEngine()
    broken = _structure("bullish")
    broken = MarketContext(
        symbol=broken.symbol,
        timeframe=broken.timeframe,
        trend=broken.trend,
        higher_highs=broken.higher_highs,
        higher_lows=broken.higher_lows,
        lower_highs=broken.lower_highs,
        lower_lows=broken.lower_lows,
        swing_highs=(_swing("high", 1.1020),),
        swing_lows=(_swing("low", 1.1010),),
        structure_events=broken.structure_events,
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=broken.last_bos,
        last_choch=broken.last_choch,
    )
    thesis = engine.build_thesis(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        structure=broken,
        bias=_bias("bullish"),
        pip_size=0.0001,
        spread_pips=1.0,
        spread_limit=2.5,
    )
    assert not thesis.is_tradeable
    assert "geometry" in thesis.rejection_reason.lower()


def test_rejection_when_target_liquidity_unclear() -> None:
    reset_thesis_tracker()
    engine = KraitosThesisEngine(min_reward_risk=2.0)
    flat = _structure("bullish")
    flat = MarketContext(
        symbol=flat.symbol,
        timeframe=flat.timeframe,
        trend="ranging",  # type: ignore[arg-type]
        higher_highs=False,
        higher_lows=False,
        lower_highs=False,
        lower_lows=False,
        swing_highs=(_swing("high", 1.1001),),
        swing_lows=(_swing("low", 1.0999),),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )

    class UnclearStory:
        story_clear = False
        current_explanation = ""
        primary_story = ""
        opportunity_type = None
        overall_confidence = 20.0
        synthesis = type("S", (), {"unclear_reason": "incoherent"})()

    thesis = engine.build_thesis(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        structure=flat,
        bias=_bias("neutral"),
        pip_size=0.0001,
        spread_pips=1.0,
        spread_limit=2.5,
        market_story=UnclearStory(),  # type: ignore[arg-type]
    )
    assert not thesis.is_tradeable


def test_momentum_imperfection_does_not_block_story_clear_thesis() -> None:
    reset_thesis_tracker()
    engine = KraitosThesisEngine()
    thesis = engine.build_thesis(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        structure=_structure("bullish"),
        bias=_bias("bullish"),
        pip_size=0.0001,
        spread_pips=1.5,
        spread_limit=2.5,
        market_story=_Story(),  # type: ignore[arg-type]
        harvest=HarvestDecision(mode="conditional", allowed=True, target_pips=8.0, reason="ok"),
        momentum_note="Momentum not confirmed: volatility chaotic on M1",
    )
    assert thesis.is_tradeable
    assert "Momentum note" in thesis.entry_reason


def test_lifecycle_intelligence_is_part_of_thesis_construction() -> None:
    reset_thesis_tracker()
    engine = KraitosThesisEngine()
    thesis = engine.build_thesis(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        structure=_structure("bullish"),
        bias=_bias("bullish"),
        pip_size=0.0001,
        spread_pips=1.0,
        spread_limit=2.5,
        market_story=_Story(),  # type: ignore[arg-type]
        harvest=HarvestDecision(mode="conditional", allowed=True, target_pips=8.0, reason="ok"),
        trend_quality=_trend_quality(),
    )
    assert thesis.market_context.market_phase == "healthy_pullback"
    assert thesis.market_context.dominant_side == "buyers"
    assert thesis.market_context.trend_quality_score == 72
    assert thesis.thesis_strength.lifecycle_alignment_score == pytest.approx(0.68)
    assert thesis.pullback_analysis.pullback_type == "healthy_retracement"
    assert thesis.control_analysis.who_is_in_control == "buyers"
    assert "Abandon if" in thesis.management_plan
    assert thesis.thesis_completion_report.entry_story
    serialized = thesis.to_dict()
    assert serialized["market_context"]["continuation_probability"] == pytest.approx(0.68)


def test_deteriorating_lifecycle_creates_thesis_challenges() -> None:
    reset_thesis_tracker()
    engine = KraitosThesisEngine()
    thesis = engine.build_thesis(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        structure=_structure("bullish"),
        bias=_bias("bullish"),
        pip_size=0.0001,
        spread_pips=1.0,
        spread_limit=2.5,
        market_story=_Story(),  # type: ignore[arg-type]
        harvest=HarvestDecision(mode="conditional", allowed=True, target_pips=8.0, reason="ok"),
        trend_quality=_trend_quality(
            phase="distribution",
            quality=38,
            continuation=0.32,
            reversal=0.61,
        ),
    )
    assert thesis.market_context.market_phase == "distribution"
    assert thesis.market_context.distribution_probability >= 0.61
    assert thesis.control_analysis.is_control_weakening
    assert thesis.thesis_evolution.management_bias == "reduce_risk_tighten_or_exit"
    assert thesis.thesis_challenges.evidence_distribution_not_continuation
    assert thesis.thesis_challenges.evidence_trend_quality_deteriorating


def test_scalping_intelligence_becomes_part_of_trade_thesis() -> None:
    reset_thesis_tracker()
    engine = KraitosThesisEngine()
    base = engine.build_thesis(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        structure=_structure("bullish"),
        bias=_bias("bullish"),
        pip_size=0.0001,
        spread_pips=1.0,
        spread_limit=2.5,
        market_story=_Story(),  # type: ignore[arg-type]
        harvest=HarvestDecision(mode="conditional", allowed=True, target_pips=8.0, reason="ok"),
        trend_quality=_trend_quality(),
    )
    with_scalp = engine.build_thesis(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        structure=_structure("bullish"),
        bias=_bias("bullish"),
        pip_size=0.0001,
        spread_pips=1.0,
        spread_limit=2.5,
        market_story=_Story(),  # type: ignore[arg-type]
        harvest=HarvestDecision(mode="conditional", allowed=True, target_pips=8.0, reason="ok"),
        trend_quality=_trend_quality(),
        scalping_intelligence=_ScalpingIntel(),
    )
    assert with_scalp.thesis_confidence > base.thesis_confidence
    assert "Scalping intelligence" in with_scalp.entry_reason
    assert with_scalp.scalping_intelligence["scalp_quality_score"] == 78
    assert "Scalping intelligence" in with_scalp.thesis_completion_report.entry_story


def test_market_regime_intelligence_becomes_part_of_trade_thesis() -> None:
    reset_thesis_tracker()
    engine = KraitosThesisEngine()
    thesis = engine.build_thesis(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        structure=_structure("bullish"),
        bias=_bias("bullish"),
        pip_size=0.0001,
        spread_pips=1.0,
        spread_limit=2.5,
        market_story=_Story(),  # type: ignore[arg-type]
        harvest=HarvestDecision(mode="conditional", allowed=True, target_pips=8.0, reason="ok"),
        trend_quality=_trend_quality(),
        market_regime=_RegimeIntel(),
        range_intelligence=_RangeIntel(),
    )

    assert thesis.market_regime.current_regime == "ranging_market"
    assert thesis.market_regime.range_quality_score == 68
    assert thesis.market_regime.compression_probability == pytest.approx(0.41)
    assert thesis.range_intelligence["range_status"] == "horizontal_range"
    assert "Regime:" in thesis.management_plan
    assert any(
        "Regime is ranging_market" in item
        for item in thesis.thesis_challenges.evidence_thesis_is_wrong
    )
    assert thesis.to_dict()["market_regime"]["strategy_bias"] == "range_logic"


def test_tp1_partial_exit_and_breakeven_runner() -> None:
    manager = ThesisExitManager(tp1_fraction=0.50, move_stop_to_breakeven=True)
    side = "buy"
    entry = 1.1000
    tp1 = 1.1025
    assert manager.tp1_hit(side, high=1.1030, low=1.0990, tp1=tp1)
    be = manager.breakeven_stop(side=side, entry_price=entry, pip_size=0.0001, spread_pips=1.0)
    assert be > entry
    closes = [1.099 + i * 0.0002 for i in range(25)]
    trail = manager.trail_runner_stop(
        side=side,
        candles_close=closes,
        current_stop=be,
        pip_size=0.0001,
    )
    assert trail is None or trail >= be
    assert manager.invalidation_hit(side, high=1.1010, low=1.0960, invalidation=1.0970)
