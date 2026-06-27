"""Tests for trend maximiser opportunity rules."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from intelligence.trend_maximiser import TrendMaximiser
from intelligence.trend_strength_engine import TrendStrengthResult
from strategies.models import MarketContext, SwingPoint
from datetime import datetime, timezone


def _trend(quality: str, score: float = 85.0) -> TrendStrengthResult:
    return TrendStrengthResult(
        symbol="EURUSD",
        score=score,
        quality=quality,  # type: ignore[arg-type]
        direction="bullish",
        components={},
        reason="test",
    )


def _structure() -> MarketContext:
    swing = SwingPoint(
        bar_index=5,
        time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        price=1.10,
        kind="high",  # type: ignore[arg-type]
    )
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend="bullish",  # type: ignore[arg-type]
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=(swing, swing),
        swing_lows=(swing, swing),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


def test_institutional_trend_enables_maximisation() -> None:
    maximiser = TrendMaximiser()
    decision = maximiser.evaluate(
        trend=_trend("institutional_trend"),
        structure=_structure(),
        drawdown_pct=3.0,
        open_positions_on_symbol=0,
    )
    assert decision.allow_primary_entry
    assert decision.allow_pullback_reentry
    assert decision.allow_breakout_retest
    assert decision.allow_continuation_addon
    assert not decision.partial_take_profit_at_1r
    assert decision.trail_timeframe == "H1"


def test_elevated_drawdown_still_harvests() -> None:
    maximiser = TrendMaximiser()
    decision = maximiser.evaluate(
        trend=_trend("institutional_trend", score=85.0),
        structure=_structure(),
        drawdown_pct=16.0,
        open_positions_on_symbol=0,
    )
    assert decision.allow_primary_entry
    assert decision.allow_continuation_addon
    assert decision.trail_timeframe == "H1"


def test_drawdown_above_10_allows_addon() -> None:
    maximiser = TrendMaximiser()
    decision = maximiser.evaluate(
        trend=_trend("institutional_trend"),
        structure=_structure(),
        drawdown_pct=11.0,
        open_positions_on_symbol=0,
    )
    assert decision.allow_primary_entry
    assert decision.allow_continuation_addon
