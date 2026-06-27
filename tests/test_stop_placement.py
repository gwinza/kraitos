"""Tests for risk.stop_placement."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from risk.stop_placement import place_structural_stop
from strategies.models import MarketContext, SwingPoint


def _structure(trend: str = "bullish") -> MarketContext:
    return MarketContext(
        symbol="EURUSD",
        timeframe="M5",
        trend=trend,  # type: ignore[arg-type]
        higher_highs=trend == "bullish",
        higher_lows=trend == "bullish",
        lower_highs=trend == "bearish",
        lower_lows=trend == "bearish",
        swing_highs=(SwingPoint(15, None, 1.1080, "high"),),
        swing_lows=(SwingPoint(10, None, 1.1020, "low"),),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


def test_buy_stop_below_swing_low():
    stop = place_structural_stop(
        side="buy",
        entry_price=1.1050,
        structure=_structure(),
        symbol="EURUSD",
        atr=0.0010,
    )
    assert stop < 1.1050
    assert stop < 1.1020


def test_sell_stop_above_swing_high():
    stop = place_structural_stop(
        side="sell",
        entry_price=1.1050,
        structure=_structure("bearish"),
        symbol="EURUSD",
        atr=0.0010,
    )
    assert stop > 1.1050
    assert stop > 1.1080
