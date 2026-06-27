"""Tests for Market Story Engine."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from intelligence.market_story_engine import MarketStoryEngine, STORY_TIMEFRAMES
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult, SwingPoint


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


def _structure(trend: str = "bullish") -> MarketContext:
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend=trend,  # type: ignore[arg-type]
        higher_highs=trend == "bullish",
        higher_lows=trend == "bullish",
        lower_highs=trend == "bearish",
        lower_lows=trend == "bearish",
        swing_highs=(SwingPoint(5, None, 1.105, "high"), SwingPoint(15, None, 1.108, "high")),
        swing_lows=(SwingPoint(8, None, 1.102, "low"), SwingPoint(18, None, 1.104, "low")),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


def _bias() -> MultiTimeframeBiasResult:
    return MultiTimeframeBiasResult("bullish", 0.75, "test", ())


def _regime() -> RegimeResult:
    return RegimeResult("trending", 0.8, "test")


def test_story_covers_timeframes(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(50)]
    candles = {
        tf: _candles(closes, minutes={"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "H8": 480}[tf])
        for tf in STORY_TIMEFRAMES
    }
    engine = MarketStoryEngine(tmp_path)
    result = engine.build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    assert result.macro_story
    assert result.h1_integrity in {"confirmed", "weakening", "changing"}
    assert result.primary_story
    assert 0 <= result.overall_confidence <= 100
    assert len(result.macro_slices) >= 1


def test_story_report_written(tmp_path: Path):
    closes = [1.10 + i * 0.0001 for i in range(40)]
    candles = {tf: _candles(closes) for tf in STORY_TIMEFRAMES}
    engine = MarketStoryEngine(tmp_path)
    engine.build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    path = engine.write_report()
    assert path is not None
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Market Story Report" in content
    assert "EURUSD" in content


def test_narrative_bridge(tmp_path: Path):
    closes = [1.10 + i * 0.0003 for i in range(45)]
    candles = {tf: _candles(closes) for tf in STORY_TIMEFRAMES}
    engine = MarketStoryEngine(tmp_path)
    story = engine.build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
        evaluation_moment=datetime(2024, 6, 10, 14, 0, tzinfo=timezone.utc),
    )
    narrative = story.to_narrative_result()
    assert narrative.symbol == "EURUSD"
    assert narrative.primary_story == story.primary_story
    assert len(narrative.slices) >= 1


def test_compression_story_detected(tmp_path: Path):
    flat = [1.10 + (i % 2) * 0.00003 for i in range(40)]
    candles = {
        tf: _candles(flat, minutes={"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "H8": 480}[tf])
        for tf in STORY_TIMEFRAMES
    }
    for tf in candles:
        candles[tf]["tick_volume"] = 50.0
    engine = MarketStoryEngine(tmp_path)
    result = engine.build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure("ranging"),
        bias=MultiTimeframeBiasResult("neutral", 0.4, "flat", ()),
        regime=RegimeResult("ranging", 0.6, "range"),
    )
    assert result.macro_story in {"compression", "ranging", "accumulation", "distribution"}
    assert result.volume_signal
