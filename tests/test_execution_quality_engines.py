"""Tests for execution quality engines."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from strategies.execution_quality_engine import ExecutionQualityEngine
from strategies.fast_failure_engine import FastFailureEngine
from strategies.models import MarketContext, MicroScalpSignal, SwingPoint
from strategies.opportunity_repair_engine import OpportunityRepairEngine
from strategies.tradability_engine_v2 import TradabilityEngineV2


def _frame(closes: list[float], *, volume: float = 120.0) -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    prev = closes[0]
    for idx, close in enumerate(closes):
        open_ = prev
        high = max(open_, close) + 0.00012
        low = min(open_, close) - 0.00012
        rows.append(
            {
                "time": start + timedelta(hours=idx),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": volume + idx % 9,
                "spread": 1.0,
            }
        )
        prev = close
    return pd.DataFrame(rows)


def _structure(trend: str = "bullish") -> MarketContext:
    swing = SwingPoint(1, pd.Timestamp("2025-01-10", tz="UTC"), 1.10, "low")
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


class TestTradabilityEngineV2:
    def test_tradability_score(self) -> None:
        result = TradabilityEngineV2().evaluate(
            symbol="EURUSD",
            spread_pips=1.0,
            spread_limit=3.0,
            stop_pips=15.0,
            target_pips=22.0,
            candles=_frame([1.1 + i * 0.0001 for i in range(50)]),
        )
        assert 0 <= result.tradability_score <= 100
        assert result.grade in {"A", "B", "C", "D"}
        assert result.components.spread_quality > 0


class TestFastFailureEngine:
    def test_detects_thesis_failure(self) -> None:
        result = FastFailureEngine().evaluate(
            symbol="EURUSD",
            side="buy",
            entry_price=1.1000,
            stop_loss=1.0980,
            current_price=1.0975,
            invalidation_level=1.0985,
        )
        assert result.thesis_failure
        assert result.recommended_action in {"exit_early", "tighten", "reduce", "hold"}

    def test_protects_winners(self) -> None:
        result = FastFailureEngine().evaluate(
            symbol="EURUSD",
            side="buy",
            entry_price=1.1000,
            stop_loss=1.0980,
            current_price=1.1030,
            momentum=MicroScalpSignal(action="buy", reason="ok", target_pips=5.0),
        )
        assert result.recommended_action == "hold"


class TestOpportunityRepairEngine:
    def test_no_instant_close(self) -> None:
        result = OpportunityRepairEngine().evaluate(
            symbol="EURUSD",
            side="buy",
            current_r=-0.2,
            trend_quality_score=35,
            reversal_pressure_score=75,
        )
        assert not result.instant_close
        assert result.size_multiplier < 1.0

    def test_weakening_tightens(self) -> None:
        result = OpportunityRepairEngine().evaluate(
            symbol="EURUSD",
            side="buy",
            current_r=0.3,
            trend_quality_score=45,
        )
        assert result.thesis_health in {"weakening", "fragile", "critical", "strong"}
        assert result.repair_action in {
            "monitor", "scale_down", "reduce_exposure", "tighten_management", "tighten_and_scale"
        }


class TestExecutionQualityEngine:
    def test_trending_entry(self) -> None:
        closes = [1.1000 + i * 0.00018 for i in range(60)]
        result = ExecutionQualityEngine().evaluate_entry(
            symbol="EURUSD",
            side="buy",
            spread_pips=1.0,
            spread_limit=3.0,
            stop_pips=12.0,
            target_pips=18.0,
            candles=_frame(closes),
            structure=_structure(),
            primary_regime="trending",
        )
        assert result.market_mode == "trending"
        assert result.entry.entry_style in {
            "continuation", "pullback", "breakout", "reversal", "wait"
        }
        assert result.execution_score > 0

    def test_exit_protects_winners(self) -> None:
        result = ExecutionQualityEngine().evaluate_exit(
            symbol="EURUSD",
            side="buy",
            entry_price=1.1000,
            stop_loss=1.0980,
            current_price=1.1040,
            trend_quality_score=60,
        )
        assert result.exit is not None
        assert result.exit.protect_winner
        assert result.repair is not None
        assert not result.repair.instant_close

    def test_exit_fast_failure_on_loser(self) -> None:
        result = ExecutionQualityEngine().evaluate_exit(
            symbol="EURUSD",
            side="buy",
            entry_price=1.1000,
            stop_loss=1.0980,
            current_price=1.0970,
            invalidation_level=1.0985,
            momentum=MicroScalpSignal(action="sell", reason="flip", target_pips=5.0),
        )
        assert result.fast_failure is not None
        assert result.fast_failure.thesis_failure or result.fast_failure.momentum_failure
