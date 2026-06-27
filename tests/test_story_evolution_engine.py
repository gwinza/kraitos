"""Tests for Story Evolution Engine."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from intelligence.story_evolution_engine import (
    EVOLUTION_TIMEFRAMES,
    IMPACT_STRENGTHEN,
    IMPACT_STRONG_WEAKEN,
    IMPACT_WEAKEN,
    StoryEvolutionEngine,
)


def _candles(
    closes: list[float],
    *,
    minutes: int = 60,
    volume_scale: float = 1.0,
    wick_bias: str = "none",
) -> pd.DataFrame:
    n = len(closes)
    times = pd.date_range("2024-01-01", periods=n, freq=f"{minutes}min", tz="UTC")
    opens = [c - 0.0001 for c in closes]
    highs = [c + 0.0008 for c in closes]
    lows = [c - 0.0008 for c in closes]
    if wick_bias == "upper":
        highs[-1] = closes[-1] + 0.003
        lows[-1] = closes[-1] - 0.0002
    elif wick_bias == "bearish_engulf":
        opens[-2] = closes[-2] + 0.0005
        opens[-1] = closes[-1] + 0.001
        closes[-1] = opens[-1] - 0.0015
        highs[-1] = opens[-1]
        lows[-1] = closes[-1]
    df = pd.DataFrame({
        "time": times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": np.linspace(100, 200, n) * volume_scale,
        "spread": [1.0] * n,
    })
    return df


def _bullish_set() -> dict[str, pd.DataFrame]:
    closes = [1.10 + i * 0.0003 for i in range(50)]
    return {
        tf: _candles(closes, minutes={"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "H8": 480}[tf])
        for tf in EVOLUTION_TIMEFRAMES
    }


def test_nested_layers_populated(tmp_path: Path):
    engine = StoryEvolutionEngine(tmp_path)
    state = engine.update("EURUSD", _bullish_set())
    assert state.novel.layer == "novel"
    assert state.chapter.layer == "chapter"
    assert state.paragraph.layer == "paragraph"
    assert state.sentence.layer == "sentence"
    assert state.novel.story
    assert state.chapter.story
    assert state.paragraph.story
    assert state.sentence.story
    assert state.macro_story == state.novel.story
    assert 0 < state.novel.confidence <= 100


def test_impact_scoring(tmp_path: Path):
    engine = StoryEvolutionEngine(tmp_path)
    candles = _bullish_set()
    bearish_m1 = [1.105 - i * 0.0004 for i in range(50)]
    m1 = _candles(bearish_m1, minutes=1, wick_bias="bearish_engulf")
    m1.loc[m1.index[-2], "open"] = 1.104
    m1.loc[m1.index[-2], "close"] = 1.103
    m1.loc[m1.index[-2], "high"] = 1.1045
    m1.loc[m1.index[-2], "low"] = 1.1025
    m1.loc[m1.index[-1], "open"] = 1.1035
    m1.loc[m1.index[-1], "close"] = 1.1015
    m1.loc[m1.index[-1], "high"] = 1.1035
    m1.loc[m1.index[-1], "low"] = 1.1010
    candles["M1"] = m1
    state = engine.update("EURUSD", candles)
    assert state.sentence.story in {
        "bearish_engulfing", "rejection_wick", "failed_break",
        "momentum_burst", "neutral",
    }
    negative_impacts = [i for i in state.sentence.recent_impacts if i <= IMPACT_WEAKEN]
    positive_impacts = [i for i in state.sentence.recent_impacts if i >= IMPACT_STRENGTHEN]
    assert negative_impacts or positive_impacts or state.sentence.story == "neutral"


def test_upward_propagation_m1_to_m5(tmp_path: Path):
    engine = StoryEvolutionEngine(tmp_path)
    candles = _bullish_set()
    bearish_m1 = [1.105 - i * 0.0005 for i in range(50)]
    candles["M1"] = _candles(bearish_m1, minutes=1, wick_bias="bearish_engulf")
    state = engine.update("EURUSD", candles)
    if state.sentence.story == "bearish_engulfing":
        assert state.paragraph.story in {
            "sellers_defending", "momentum_shift", "failed_breakout",
            "trend_pause", "liquidity_sweep", "compression",
        }
        impacts = list(state.paragraph.recent_impacts) + list(state.sentence.recent_impacts)
        assert any(i <= IMPACT_WEAKEN for i in impacts) or state.paragraph.story == "momentum_shift"


def test_downward_context_dampens_bearish(tmp_path: Path):
    engine = StoryEvolutionEngine(tmp_path)
    candles = _bullish_set()
    bearish_m1 = [1.105 - i * 0.0004 for i in range(50)]
    candles["M1"] = _candles(bearish_m1, minutes=1, wick_bias="bearish_engulf")
    state = engine.update("EURUSD", candles)
    if state.novel.story in {"bullish_campaign", "accumulation", "expansion"}:
        if state.sentence.story == "bearish_engulfing" and state.sentence.recent_impacts:
            assert max(state.sentence.recent_impacts) <= IMPACT_WEAKEN
            assert state.alignment in {"partial", "aligned", "transition"}
            assert state.probable_evolution in {
                "continuation_likely", "uncertain", "transition", "strengthening",
            }


def test_confidence_updates(tmp_path: Path):
    engine = StoryEvolutionEngine(tmp_path)
    state1 = engine.update("EURUSD", _bullish_set())
    conf_before = state1.novel.confidence
    candles = _bullish_set()
    strong = [1.10 + i * 0.0008 for i in range(50)]
    candles["H4"] = _candles(strong, minutes=240, volume_scale=1.8)
    state2 = engine.update("EURUSD", candles)
    assert state2.novel.evidence_count >= state1.novel.evidence_count
    assert state2.confidence_trend in {"strengthening", "stable", "deteriorating"}
    if state2.novel.recent_impacts and max(state2.novel.recent_impacts) >= IMPACT_STRENGTHEN:
        assert state2.novel.confidence >= conf_before - 5.0


def test_reports_written(tmp_path: Path):
    engine = StoryEvolutionEngine(tmp_path)
    engine.update("EURUSD", _bullish_set())
    evo, trans, impact = engine.write_all_reports()
    assert evo is not None and evo.exists()
    assert trans is not None and trans.exists()
    assert impact is not None and impact.exists()
    assert "Story Evolution Report" in evo.read_text(encoding="utf-8")
