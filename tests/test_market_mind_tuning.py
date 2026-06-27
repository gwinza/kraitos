"""Tests for V5 Market Mind tuning parameters."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from intelligence.market_mind_tuning import (
    blended_confidence,
    participation_from_confidence,
    thesis_is_clear,
)
from intelligence.picture_models import DepartmentContribution, MarketPicture


def _picture(**kwargs) -> MarketPicture:
    defaults = {
        "symbol": "EURUSD",
        "clarity": "incomplete",
        "regime": "transitional",
        "dominant_side": "bullish",
        "coherent_story": True,
        "summary": "test",
        "supporting_evidence": (),
        "contradictions": (),
        "noise_evidence": (),
        "key_evidence": (),
        "departments": (),
        "confidence": 58.0,
        "professional_thesis_supported": False,
        "reason_not_clear": "forming",
    }
    defaults.update(kwargs)
    return MarketPicture(**defaults)  # type: ignore[arg-type]


def test_blended_confidence_boosts_with_strategy_fit():
    low = blended_confidence(
        picture_confidence=60,
        story_confidence=55,
        cio_confidence=58,
        strategy_fit=0,
    )
    high = blended_confidence(
        picture_confidence=60,
        story_confidence=55,
        cio_confidence=58,
        strategy_fit=82,
    )
    assert high > low


def test_participation_probes_on_moderate_confidence():
    picture = _picture(clarity="incomplete")
    mode, mult = participation_from_confidence(64, picture, hard_blocked=False)
    assert mode == "probe"
    assert mult >= 0.20


def test_participation_conflict_probes_when_side_resolved():
    picture = _picture(clarity="conflicted", confidence=55)
    mode, mult = participation_from_confidence(55, picture, hard_blocked=False)
    assert mode == "probe"
    assert mult == pytest.approx(0.18)


def test_thesis_clear_on_incomplete_with_strategy_fit():
    picture = _picture(
        clarity="incomplete",
        coherent_story=True,
        professional_thesis_supported=False,
        confidence=55,
    )
    assert thesis_is_clear(
        picture=picture,
        side="buy",
        participation="probe",
        allocation=0.22,
        strategy_fit=78,
        hard_blocked=False,
    )


def test_thesis_not_clear_when_stand_aside():
    picture = _picture(clarity="clear", professional_thesis_supported=True)
    assert not thesis_is_clear(
        picture=picture,
        side="buy",
        participation="stand_aside",
        allocation=0.0,
        strategy_fit=80,
        hard_blocked=False,
    )
