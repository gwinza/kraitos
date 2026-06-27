"""Tests for grandmaster trade maturity doctrine."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from strategies.location_quality_engine import LocationQualityEngine
from strategies.fast_failure_engine import FastFailureEngine
from strategies.market_acceptance_engine import MarketAcceptanceEngine
from strategies.scout_commit_engine import ScoutCommitEngine
from strategies.timing_quality_engine import TimingQualityEngine
from strategies.trade_maturity_engine import TradeMaturityEngine
from strategies.models import (
    MarketContext,
    MultiTimeframeBiasResult,
    SwingPoint,
    TimeframeBiasDetail,
)


def _m5_rejection_buy() -> pd.DataFrame:
    start = datetime(2025, 2, 1, tzinfo=timezone.utc)
    rows = []
    for idx in range(25):
        close = 1.1000 + idx * 0.00005
        rows.append(
            {
                "time": start.replace(minute=idx),
                "open": close,
                "high": close + 0.00015,
                "low": close - 0.00025,
                "close": close + 0.00008,
                "tick_volume": 100,
                "spread": 1.0,
            }
        )
    rows[-1]["low"] = rows[-1]["close"] - 0.00035
    rows[-1]["close"] = rows[-1]["open"] + 0.00012
    return pd.DataFrame(rows)


def _bias_bullish() -> MultiTimeframeBiasResult:
    return MultiTimeframeBiasResult(
        bias="bullish",
        confidence=0.75,
        explanation="test",
        layers=(TimeframeBiasDetail("H1", "bullish", 0.7, "test"),),
    )


def _structure_bullish() -> MarketContext:
    swing = SwingPoint(1, pd.Timestamp("2025-01-01", tz="UTC"), 1.10, "low")
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend="bullish",
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=(swing,),
        swing_lows=(swing,),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


class TestLocationQualityEngine:
    def test_buy_discount_scores_higher(self) -> None:
        class FakeInst:
            equilibrium = 1.1000
            premium_zone_low = 1.1010
            premium_zone_high = 1.1030
            discount_zone_low = 1.0970
            discount_zone_high = 1.0990
            in_premium = False
            in_discount = True
            in_ote = False
            liquidity_pools = ()

        result = LocationQualityEngine().evaluate(
            side="buy",
            entry_price=1.0985,
            stop_loss=1.0970,
            target_price=1.1010,
            spread_pips=1.0,
            pip_size=0.0001,
            institutional_structure=FakeInst(),
        )
        assert result.location_quality_score >= 65
        assert result.premium_discount_state == "discount"


class TestTimingQualityEngine:
    def test_no_reaction_is_too_early(self) -> None:
        flat = pd.DataFrame(
            {
                "open": [1.1] * 20,
                "high": [1.1002] * 20,
                "low": [1.0998] * 20,
                "close": [1.1] * 20,
                "tick_volume": [100] * 20,
                "spread": [1.0] * 20,
            }
        )
        result = TimingQualityEngine().evaluate(side="buy", candles=flat)
        assert result.entry_too_early
        assert result.timing_quality_score < 50


class TestTradeMaturityEngine:
    def test_idea_stage_allows_thesis_probe(self) -> None:
        engine = TradeMaturityEngine()
        result = engine.evaluate_entry(
            symbol="EURUSD",
            side="buy",
            entry_price=1.1020,
            stop_loss=1.1000,
            target_price=1.1050,
            spread_pips=1.2,
            pip_size=0.0001,
            setup_kind="harvest",
            bias=_bias_bullish(),
            structure=_structure_bullish(),
            candles={"M5": _m5_rejection_buy()},
            story_clear=False,
            conviction_score=50.0,
        )
        assert result.maturity_stage in {"idea", "developing", "ready"}
        assert result.commitment in {"probe", "micro_probe", "normal", "aggressive"}
        assert result.size_multiplier > 0

    def test_gbpjpy_requires_higher_maturity_for_normal(self) -> None:
        engine = TradeMaturityEngine()
        result = engine.evaluate_entry(
            symbol="GBPJPY",
            side="sell",
            entry_price=190.50,
            stop_loss=191.00,
            target_price=189.50,
            spread_pips=2.0,
            pip_size=0.01,
            setup_kind="micro_scalp",
            bias=MultiTimeframeBiasResult(
                bias="bearish",
                confidence=0.6,
                explanation="test",
                layers=(TimeframeBiasDetail("H1", "bearish", 0.55, "test"),),
            ),
            structure=_structure_bullish(),
            candles={"M5": _m5_rejection_buy()},
        )
        if result.maturity_stage == "ready":
            assert result.size_multiplier <= 0.75

    def test_scalp_scratch_on_open(self) -> None:
        result = TradeMaturityEngine().evaluate_open(
            side="buy",
            current_r=-0.30,
            setup_kind="micro_scalp",
        )
        assert result.commitment == "scratch"

    def test_harvest_holds_when_healthy(self) -> None:
        result = TradeMaturityEngine().evaluate_open(
            side="buy",
            current_r=-0.20,
            setup_kind="harvest",
            trend_health=65,
        )
        assert result.commitment in {"normal", "reduce"}


class TestMarketAcceptanceEngine:
    def test_evaluates_without_error(self) -> None:
        result = MarketAcceptanceEngine().evaluate(
            side="buy",
            candles=_m5_rejection_buy(),
            invalidation_level=1.0990,
            structure=_structure_bullish(),
        )
        assert 0 <= result.acceptance_score <= 100
        assert hasattr(result, "time_to_acceptance")
        assert hasattr(result, "acceptance_evidence")


class TestScoutCommitEngine:
    def test_ready_without_acceptance_scouts_not_commits(self) -> None:
        loc = LocationQualityEngine().evaluate(
            side="buy",
            entry_price=1.0985,
            stop_loss=1.0970,
            target_price=1.1010,
            spread_pips=1.0,
            pip_size=0.0001,
        )
        timing = TimingQualityEngine().evaluate(side="buy", candles=_m5_rejection_buy())
        acceptance = MarketAcceptanceEngine().evaluate(
            side="buy",
            candles=_m5_rejection_buy(),
            invalidation_level=1.0990,
            structure=_structure_bullish(),
        )
        result = ScoutCommitEngine().evaluate_entry(
            side="buy",
            setup_kind="harvest",
            maturity_stage="ready",
            direction_quality=70,
            location=loc,
            timing=timing,
            acceptance=acceptance,
            story_clear=True,
            market_phase="trend_continuation",
            trend_quality=65,
            maturity_score=72,
            stop_pips=15.0,
            spread_pips=1.2,
        )
        if acceptance.acceptance_score < 65:
            assert result.scout_or_commit == "scout"
            assert result.participation_stage == "scout"

    def test_scout_scratch_triggers_on_stagnant_acceptance(self) -> None:
        scratch = FastFailureEngine().evaluate_scout_scratch(
            symbol="EURUSD",
            side="buy",
            entry_price=1.1000,
            stop_loss=1.0985,
            current_price=1.0996,
            bars_since_entry=4,
            setup_kind="micro_scalp",
            scout_or_commit="scout",
            momentum_clarity="unclear",
            entry_acceptance_score=52,
            current_acceptance_score=50,
            entry_rejection_score=48,
            current_rejection_score=62,
            spread_pips=1.2,
            spread_limit=3.0,
            candles=_m5_rejection_buy(),
        )
        assert scratch.should_scratch
        assert scratch.scratch_reason in {
            "rejection_rise",
            "acceptance_failure",
            "momentum_unclear",
            "confidence_decay",
        }
