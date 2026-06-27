"""Tests for thesis-based trade management."""

from __future__ import annotations

import pandas as pd

from intelligence.thesis_trade_management import (
    check_thesis_invalidation,
    resolve_exit_phase,
    reset_adaptive_trackers,
)
from strategies.models import MarketContext, SwingPoint


def _structure_bearish() -> MarketContext:
    swing = SwingPoint(
        bar_index=1,
        time=pd.Timestamp("2025-01-10", tz="UTC"),
        price=1.10,
        kind="high",
    )
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend="bearish",
        higher_highs=False,
        higher_lows=False,
        lower_highs=True,
        lower_lows=True,
        swing_highs=(swing,),
        swing_lows=(swing,),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


def test_exit_phases() -> None:
    assert resolve_exit_phase(partial_taken=False, tp2_taken=False) == "thesis_protection"
    assert resolve_exit_phase(partial_taken=True, tp2_taken=False) == "profit_protection"
    assert resolve_exit_phase(partial_taken=True, tp2_taken=True) == "harvest"


def test_invalidation_on_level_breach() -> None:
    invalidated, reason = check_thesis_invalidation(
        side="buy",
        current_price=1.0970,
        invalidation_level=1.0980,
    )
    assert invalidated
    assert "breached" in reason


def test_invalidation_on_structure_flip() -> None:
    invalidated, reason = check_thesis_invalidation(
        side="buy",
        current_price=1.1005,
        invalidation_level=1.0980,
        structure=_structure_bearish(),
    )
    assert invalidated
    assert "bearish" in reason


def test_opportunity_cost_tracker() -> None:
    reset_adaptive_trackers()
    from intelligence.thesis_trade_management import get_opportunity_cost_tracker

    tracker = get_opportunity_cost_tracker()
    tracker.record_avoided_loser(r_avoided=1.0)
    tracker.record_missed_winner(r_potential=0.5)
    assert tracker.confirmation_expectancy == 0.5
