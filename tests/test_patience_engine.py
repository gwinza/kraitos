"""Tests for execution.patience_engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from brain.market_story_engine import LiquidityTarget, MarketStory
from execution.patience_engine import PatienceEngine
from strategies.models import MarketContext, StructureEvent, SwingPoint


def _story(
    direction: str = "bullish",
    confidence: float = 72.0,
    *,
    invalidation: float = 1.1000,
    objective: float = 1.1100,
) -> MarketStory:
    return MarketStory(
        symbol="EURUSD",
        timeframe="H4",
        direction=direction,  # type: ignore[arg-type]
        confidence=confidence,
        controlling_side="buyers" if direction == "bullish" else "sellers",
        structure_state="bullish moderate (HH/HL)",
        liquidity_targets=(
            LiquidityTarget("session high", objective, "buy_side"),
        ),
        trapped_traders=(),
        next_objective=objective,
        invalidation_level=invalidation,
        narrative="test story",
        trend_strength=65.0,
    )


def _structure(trend: str = "bullish", *, with_bos: bool = False) -> MarketContext:
    bos = None
    if with_bos:
        bos = StructureEvent(
            kind="bos_bullish",
            bar_index=20,
            time=None,
            price=1.1050,
            reference_price=1.1040,
            description="bullish BOS",
        )
    return MarketContext(
        symbol="EURUSD",
        timeframe="M5",
        trend=trend,  # type: ignore[arg-type]
        higher_highs=trend == "bullish",
        higher_lows=trend == "bullish",
        lower_highs=trend == "bearish",
        lower_lows=trend == "bearish",
        swing_highs=(SwingPoint(15, None, 1.1080, "high"), SwingPoint(25, None, 1.1090, "high")),
        swing_lows=(SwingPoint(10, None, 1.1020, "low"), SwingPoint(22, None, 1.1045, "low")),
        structure_events=(bos,) if bos else (),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=bos,
        last_choch=None,
    )


def _candles_from_closes(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    times = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c + 0.0004 for c in closes],
        "low": [c - 0.0004 for c in closes],
        "close": closes,
        "tick_volume": np.linspace(100, 180, n),
        "spread": [1.0] * n,
    })


def _pullback_candles() -> pd.DataFrame:
    """Impulse up then partial retrace into value with rejection wick."""
    base = [1.1020 + i * 0.00015 for i in range(20)]
    impulse = base + [base[-1] + 0.0005, base[-1] + 0.0010, base[-1] + 0.0014]
    retrace = impulse + [impulse[-1] - 0.0006, impulse[-1] - 0.00075]
    frame = _candles_from_closes(retrace)
    last_idx = frame.index[-1]
    frame.loc[last_idx, "low"] = float(frame.loc[last_idx, "close"]) - 0.0008
    frame.loc[last_idx, "open"] = float(frame.loc[last_idx, "close"]) - 0.0002
    return frame


def test_neutral_story_waits():
    decision = PatienceEngine().evaluate(
        story=_story("neutral", 80.0),
        candles=_pullback_candles(),
        structure=_structure(),
        bid=1.1030,
        ask=1.1032,
        symbol="EURUSD",
    )
    assert not decision.ready
    assert decision.opportunity is None


def test_low_confidence_story_waits():
    decision = PatienceEngine().evaluate(
        story=_story(confidence=25.0),
        candles=_pullback_candles(),
        structure=_structure(),
        bid=1.1030,
        ask=1.1032,
        symbol="EURUSD",
    )
    assert not decision.ready


def test_pullback_into_value_entry():
    decision = PatienceEngine().evaluate(
        story=_story(),
        candles=_pullback_candles(),
        structure=_structure(with_bos=True),
        bid=1.1033,
        ask=1.1035,
        symbol="EURUSD",
    )
    if decision.ready:
        assert decision.opportunity is not None
        assert decision.opportunity.entry_type in {
            "pullback_into_value",
            "retest_broken_structure",
            "liquidity_sweep_rejection",
            "compression_before_expansion",
        }
        assert decision.opportunity.stop_loss < decision.opportunity.entry_price
        assert decision.opportunity.confidence >= 60


def test_rejects_late_entry():
    story = _story(invalidation=1.1000, objective=1.1100)
    decision = PatienceEngine().evaluate(
        story=story,
        candles=_pullback_candles(),
        structure=_structure(),
        bid=1.1095,
        ask=1.1097,
        symbol="EURUSD",
    )
    assert not decision.ready
    assert "late entry" in decision.reason.lower()


def test_rejects_vertical_momentum():
    closes = [1.1000 + i * 0.0008 for i in range(28)]
    frame = _candles_from_closes(closes)
    frame.loc[frame.index[-1], "high"] = closes[-1] + 0.0020
    frame.loc[frame.index[-1], "low"] = closes[-1] - 0.0001
    frame.loc[frame.index[-1], "close"] = closes[-1] + 0.0018
    frame.loc[frame.index[-1], "open"] = closes[-1]

    decision = PatienceEngine().evaluate(
        story=_story(),
        candles=frame,
        structure=_structure(),
        bid=1.1220,
        ask=1.1222,
        symbol="EURUSD",
    )
    assert not decision.ready
    reason = decision.reason.lower()
    assert (
        "vertical momentum" in reason
        or "extended candle" in reason
        or "late entry" in reason
    )


def test_valid_story_without_setup_waits_not_chases():
    flat = [1.1030 + (i % 3) * 0.00005 for i in range(35)]
    decision = PatienceEngine().evaluate(
        story=_story(),
        candles=_candles_from_closes(flat),
        structure=_structure(),
        bid=1.1030,
        ask=1.1032,
        symbol="EURUSD",
    )
    assert not decision.ready
    reason = decision.reason.lower()
    assert "awaiting" in reason or "confirmation missing" in reason


def test_entry_opportunity_to_dict():
    from execution.patience_engine import EntryOpportunity

    opp = EntryOpportunity(
        entry_price=1.1035,
        entry_type="pullback_into_value",
        confidence=75.0,
        stop_loss=1.1020,
        explanation="test",
        side="buy",
    )
    payload = opp.to_dict()
    assert payload["entry_type"] == "pullback_into_value"
    assert payload["side"] == "buy"
