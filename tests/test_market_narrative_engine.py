"""Tests for Market Narrative Engine."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from intelligence.market_narrative_engine import MarketNarrativeEngine, NARRATIVE_TIMEFRAMES
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult, SwingPoint


def _candles(closes: list[float], *, vol_scale: float = 1.0) -> pd.DataFrame:
    n = len(closes)
    times = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c + 0.001 for c in closes],
        "low": [c - 0.001 for c in closes],
        "close": closes,
        "tick_volume": [100 * vol_scale] * n,
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
        swing_highs=(SwingPoint(5, None, 1.10, "high"),),
        swing_lows=(SwingPoint(8, None, 1.09, "low"),),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


def test_narrative_covers_timeframes(tmp_path: Path):
    closes = [1.10 + i * 0.0003 for i in range(50)]
    candles = {tf: _candles(closes) for tf in NARRATIVE_TIMEFRAMES}
    engine = MarketNarrativeEngine(tmp_path)
    result = engine.build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.8, "test", ()),
        regime=RegimeResult("trending", 0.7, "test"),
    )
    tfs = {s.timeframe for s in result.slices}
    assert "H1" in tfs
    assert result.primary_story
    assert 0 <= result.overall_confidence <= 100
    for s in result.slices:
        assert s.what
        assert s.why
        assert s.likely_next


def test_compression_detection(tmp_path: Path):
    flat = [1.10 + (i % 2) * 0.00005 for i in range(40)]
    candles = {tf: _candles(flat, vol_scale=0.5) for tf in NARRATIVE_TIMEFRAMES}
    engine = MarketNarrativeEngine(tmp_path)
    result = engine.build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure("ranging"),
        bias=MultiTimeframeBiasResult("neutral", 0.5, "test", ()),
        regime=RegimeResult("ranging", 0.6, "test"),
    )
    phases = {s.what for s in result.slices}
    assert "compression" in phases or "ranging" in phases or result.compression_detected


def test_micro_narrative_class_detection(tmp_path: Path):
    flat = [1.10 + (i % 2) * 0.00005 for i in range(40)]
    candles = {tf: _candles(flat, vol_scale=0.5) for tf in NARRATIVE_TIMEFRAMES}
    engine = MarketNarrativeEngine(tmp_path)
    result = engine.build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure("ranging"),
        bias=MultiTimeframeBiasResult("bullish", 0.6, "test", ()),
        regime=RegimeResult("ranging", 0.6, "test"),
        evaluation_moment=datetime(2024, 6, 10, 9, 0, tzinfo=timezone.utc),
    )
    valid_classes = {
        "micro_pullback_continuation",
        "liquidity_sweep_snapback",
        "breakout_retest_harvest",
        "compression_pop",
        "session_open_push",
        "failed_breakout_return",
        "trend_pause_resume",
    }
    if result.micro_narrative_class is not None:
        assert result.micro_narrative_class in valid_classes


def test_narrative_report_written(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(30)]
    candles = {tf: _candles(closes) for tf in NARRATIVE_TIMEFRAMES}
    engine = MarketNarrativeEngine(tmp_path)
    engine.build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.7, "test", ()),
        regime=RegimeResult("trending", 0.7, "test"),
    )
    path = engine.write_report()
    assert path is not None
    assert "Market Narrative Report" in path.read_text(encoding="utf-8")
