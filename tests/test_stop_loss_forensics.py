"""Tests for management.stop_loss_forensics."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from brain.market_story_engine import MarketStory
from management.stop_loss_forensics import StopForensicsInput, StopLossForensics


def _story(direction: str = "bullish") -> MarketStory:
    return MarketStory(
        symbol="EURUSD",
        timeframe="M5",
        direction=direction,  # type: ignore[arg-type]
        confidence=70.0,
        controlling_side="buyers",
        structure_state="bullish",
        liquidity_targets=(),
        trapped_traders=(),
        next_objective=1.1100,
        invalidation_level=1.1000,
        narrative="test",
        trend_strength=60.0,
    )


def test_classifies_too_tight_stop():
    result = StopLossForensics().classify(
        StopForensicsInput(
            symbol="EURUSD",
            side="buy",
            entry_price=1.1050,
            stop_loss=1.1046,
            exit_price=1.1046,
            exit_action="stop_loss",
            r_multiple=-0.8,
            atr=0.0010,
            story=_story(),
        )
    )
    assert result is not None
    assert result.classification in {"too_tight", "inside_volatility", "inside_sweep_zone"}


def test_classifies_correct_stop_on_thesis_failure():
    result = StopLossForensics().classify(
        StopForensicsInput(
            symbol="EURUSD",
            side="buy",
            entry_price=1.1050,
            stop_loss=1.0990,
            exit_price=1.0990,
            exit_action="stop_loss",
            r_multiple=-1.2,
            atr=0.0010,
            story=_story(),
        )
    )
    assert result is not None
    assert result.classification == "correct_stop"
