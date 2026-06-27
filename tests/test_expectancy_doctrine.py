"""Integration tests for expectancy doctrine orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from brain.market_story_engine import MarketStory
from core.expectancy_gates import MIN_STORY_CONFIDENCE, participation_unlock
from core.expectancy_doctrine import ExpectancyDoctrine
from core.expectancy_learning import map_adaptive_exit, _current_r
from execution.models import OpenTrade
from management.adaptive_exit_engine import ExitDecision as AdaptiveExitDecision

pytestmark = pytest.mark.offline


def _story(direction: str = "bullish", confidence: float = 55.0) -> MarketStory:
    return MarketStory(
        direction=direction,  # type: ignore[arg-type]
        confidence=confidence,
        controlling_side="buyers" if direction == "bullish" else "sellers",
        structure_state="trend_continuation",
        liquidity_targets=(),
        trapped_traders=(),
        next_objective=1.105,
        invalidation_level=1.098,
        narrative="Buyers control; pullback into value likely.",
        symbol="EURUSD",
        timeframe="M5",
        trend_strength=62.0,
    )


def test_story_actionable_prefers_brain_story_over_legacy_clear() -> None:
    doctrine = ExpectancyDoctrine(
        project_root=None,
        config=MagicMock(),
        risk_controller=MagicMock(),
    )
    legacy = MagicMock(story_clear=False)
    assert doctrine.story_actionable(_story(), legacy)
    assert not doctrine.story_actionable(
        _story(direction="neutral", confidence=20.0),
        legacy,
    )


def test_harvest_unlock_uses_expectancy_not_story_clear_alone() -> None:
    doctrine = ExpectancyDoctrine(
        project_root=None,
        config=MagicMock(),
        risk_controller=MagicMock(),
    )
    assert doctrine.harvest_unlock(
        harvest_allowed=False,
        brain_story=_story(confidence=MIN_STORY_CONFIDENCE + 5),
        legacy_story=None,
        harvest_score_band="conditional",
    )
    assert doctrine.harvest_unlock(
        harvest_allowed=False,
        brain_story=None,
        legacy_story=None,
        harvest_score_band="no_harvest",
        expected_r=0.12,
    )


def test_map_adaptive_exit_translates_trail_and_scale() -> None:
    trade = OpenTrade(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        volume=0.10,
    )
    trail = map_adaptive_exit(
        AdaptiveExitDecision(action="TRAIL", stop_level=1.1010, reasoning="Trail"),
        trade=trade,
        current_price=1.1020,
    )
    assert trail.action == "trail_stop"
    assert trail.new_stop_loss == 1.1010

    scale = map_adaptive_exit(
        AdaptiveExitDecision(
            action="SCALE_OUT",
            stop_level=None,
            reasoning="Liquidity",
            scale_fraction=0.5,
        ),
        trade=trade,
        current_price=1.1030,
    )
    assert scale.action == "scale_out"
    assert scale.scale_fraction == 0.5


def test_participation_unlock_module_helper() -> None:
    assert participation_unlock(
        harvest_allowed=False,
        brain_story=_story(),
        legacy_story=None,
        harvest_score_band="no_harvest",
    )
    assert not participation_unlock(
        harvest_allowed=False,
        brain_story=None,
        legacy_story=None,
        harvest_score_band="no_harvest",
        expected_r=0.01,
    )
    trade = OpenTrade(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        volume=0.1,
    )
    r_val = _current_r(trade, 1.1020)
    assert r_val == pytest.approx(1.0, rel=0.01)
