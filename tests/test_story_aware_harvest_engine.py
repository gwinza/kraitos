"""Tests for story-aware harvest engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.offline

from intelligence.story_aware_harvest_engine import StoryAwareHarvestEngine
from strategies.models import (
    HarvestContext,
    MarketContext,
    MultiTimeframeBiasResult,
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
        TimeframeBiasDetail(tf, direction, 0.7, role)  # type: ignore[arg-type]
        for tf, role in [("H1", "structure"), ("M5", "setup"), ("M1", "precision_entry")]
    )
    return MultiTimeframeBiasResult(
        bias=direction,  # type: ignore[arg-type]
        confidence=0.75,
        explanation="test",
        layers=layers,
    )


def _structure(trend: str = "bullish") -> MarketContext:
    bullish = trend == "bullish"
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend=trend,  # type: ignore[arg-type]
        higher_highs=bullish,
        higher_lows=bullish,
        lower_highs=not bullish,
        lower_lows=not bullish,
        swing_highs=(_swing("high", 1.12), _swing("high", 1.13)),
        swing_lows=(_swing("low", 1.10), _swing("low", 1.11)),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


def _context(**kwargs) -> HarvestContext:
    defaults = {
        "symbol": "EURUSD",
        "bias": _bias("bullish"),
        "structure": _structure("bullish"),
        "regime": RegimeResult(regime="trending", confidence=0.7, reason="ok"),  # type: ignore[arg-type]
        "current_spread": 1.5,
        "spread_limit": 2.0,
        "in_active_session": True,
        "news_risk_active": False,
        "story_clear": True,
        "opportunity_type": "liquidity_sweep",
        "price_action_valid": True,
        "structure_supports": True,
        "volume_momentum_strong": True,
        "narrative_direction": "bullish",
    }
    defaults.update(kwargs)
    return HarvestContext(**defaults)


def test_probe_detects_micro_harvest_window():
    engine = StoryAwareHarvestEngine()
    window = engine.probe_micro_harvest(_context())
    assert window is not None
    assert window.pattern_key == "liquidity_sweep"
    assert 1.0 <= window.target_pips <= 5.0


def test_story_participation_override_when_base_blocks():
    engine = StoryAwareHarvestEngine()
    context = _context(
        bias=_bias("neutral"),
        story_clear=True,
        opportunity_type="pullback_continuation",
        price_action_valid=True,
        structure_supports=True,
        volume_momentum_strong=True,
    )
    decision = engine.evaluate(context)
    assert decision.allowed
    assert decision.target_pips <= 5.0
    assert "Story" in decision.reason
