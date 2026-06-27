"""Tests for brain.market_story_engine."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from brain.market_story_engine import MarketStory, MarketStoryEngine, STORY_TIMEFRAMES


def _candles(closes: list[float], minutes: int = 60) -> pd.DataFrame:
    n = len(closes)
    times = pd.date_range("2024-01-01", periods=n, freq=f"{minutes}min", tz="UTC")
    return pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c + 0.0008 for c in closes],
        "low": [c - 0.0008 for c in closes],
        "close": closes,
        "tick_volume": np.linspace(100, 220, n),
        "spread": [1.0] * n,
    })


def test_read_bullish_story_fields():
    closes = [1.10 + i * 0.0002 for i in range(60)]
    frame = _candles(closes)
    story = MarketStoryEngine().read(symbol="EURUSD", timeframe="H4", candles=frame)

    assert isinstance(story, MarketStory)
    assert story.direction in {"bullish", "bearish", "neutral"}
    assert story.controlling_side in {"buyers", "sellers", "neutral"}
    assert 0 <= story.confidence <= 100
    assert story.structure_state
    assert story.narrative
    assert story.next_objective > 0
    assert story.invalidation_level > 0
    assert story.trend_strength >= 0


def test_read_all_timeframes():
    closes = [1.10 + i * 0.00015 for i in range(60)]
    candles = {
        tf: _candles(closes, minutes={"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "H8": 480}[tf])
        for tf in STORY_TIMEFRAMES
    }
    stories = MarketStoryEngine().read_all(symbol="EURUSD", candles=candles)
    assert len(stories) == len(STORY_TIMEFRAMES)
    for tf, story in stories.items():
        assert story.timeframe == tf
        assert story.symbol == "EURUSD"
        assert len(story.narrative) > 20


def test_narrative_reads_like_trader(tmp_path: Path):
    # Uptrend with dip then reclaim — sweep-like behaviour
    base = [1.10 + i * 0.0003 for i in range(50)]
    dip = base[:-5] + [base[-6] - 0.0015] + [base[-1] + 0.0005]
    frame = _candles(dip, minutes=240)
    story = MarketStoryEngine().read(symbol="EURUSD", timeframe="H4", candles=frame)

    lower = story.narrative.lower()
    assert "h4" in lower
    assert "invalidat" in lower
    assert "target" in lower or "liquidity" in lower


def test_indicators_support_never_veto_direction():
    closes = [1.10 + i * 0.00025 for i in range(60)]
    frame = _candles(closes)

    class _BearIndicators:
        market_explanation_contribution = "bearish distribution pressure building"
        insight_score = 80.0

    engine = MarketStoryEngine()
    without = engine.read(symbol="EURUSD", timeframe="H1", candles=frame)
    with_ind = engine.read(
        symbol="EURUSD",
        timeframe="H1",
        candles=frame,
        indicator_interpretation=_BearIndicators(),
    )
    assert with_ind.direction == without.direction
    assert with_ind.confidence <= without.confidence + 1


def test_to_dict_serialises():
    closes = [1.10 + i * 0.0001 for i in range(55)]
    story = MarketStoryEngine().read(symbol="EURUSD", timeframe="H1", candles=_candles(closes))
    payload = story.to_dict()
    assert payload["symbol"] == "EURUSD"
    assert "liquidity_targets" in payload
    assert "trapped_traders" in payload
    assert payload["narrative"]
