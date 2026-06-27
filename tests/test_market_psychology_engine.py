"""Tests for Market Psychology Engine — understanding, not filters."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from intelligence.evidence_synthesis_engine import EvidenceSynthesisEngine
from intelligence.indicator_interpretation_engine import FORBIDDEN_OUTPUT
from intelligence.market_psychology_engine import (
    INFERRED_EMOTIONS,
    MARKET_PSYCHOLOGY_DNA,
    MarketPsychologyEngine,
)
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult, SwingPoint


def _candles(closes: list[float], minutes: int = 60) -> pd.DataFrame:
    n = len(closes)
    times = pd.date_range("2024-01-01", periods=n, freq=f"{minutes}min", tz="UTC")
    return pd.DataFrame({
        "time": times,
        "open": [c - 0.0001 for c in closes],
        "high": [c + 0.0008 for c in closes],
        "low": [c - 0.0008 for c in closes],
        "close": closes,
        "tick_volume": np.linspace(100, 300, n),
        "spread": [1.0] * n,
    })


def _candle_set(closes: list[float]) -> dict[str, pd.DataFrame]:
    return {
        tf: _candles(closes, minutes={"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "H8": 480}[tf])
        for tf in ("M1", "M5", "M15", "H1", "H4", "H8")
    }


def _structure(trend: str = "bullish") -> MarketContext:
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend=trend,
        higher_highs=trend == "bullish",
        higher_lows=trend == "bullish",
        lower_highs=trend == "bearish",
        lower_lows=trend == "bearish",
        swing_highs=(SwingPoint(10, None, 1.105, "high"),),
        swing_lows=(SwingPoint(5, None, 1.100, "low"),),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=("1.1000",),
        last_bos=None,
        last_choch=None,
    )


def _bias(direction: str = "bullish") -> MultiTimeframeBiasResult:
    return MultiTimeframeBiasResult(
        bias=direction,
        confidence=0.72,
        explanation="test",
        layers=(),
    )


def _regime() -> RegimeResult:
    return RegimeResult("trending", 0.7, "trending")


def test_dna_exported():
    assert "Markets are driven by people" in MARKET_PSYCHOLOGY_DNA
    assert "Understanding expands opportunities" in MARKET_PSYCHOLOGY_DNA
    assert "never filters" in MARKET_PSYCHOLOGY_DNA


def test_infer_produces_psychology_state(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(80)]
    engine = MarketPsychologyEngine(tmp_path)
    result = engine.infer(
        symbol="EURUSD",
        candles=_candle_set(closes),
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    state = result.psychology_state
    assert state.dominant_emotion in INFERRED_EMOTIONS
    assert state.conviction_level in {"strong", "moderate", "weak", "contested"}
    assert state.participation_quality
    assert state.confidence_shift in {"strengthening", "stable", "weakening", "fading"}
    assert state.emotional_extremes
    assert result.insight_score >= 0.0


def test_all_emotions_scored(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(80)]
    engine = MarketPsychologyEngine(tmp_path)
    result = engine.infer(
        symbol="EURUSD",
        candles=_candle_set(closes),
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    for emotion in INFERRED_EMOTIONS:
        assert emotion in result.emotion_scores
        assert result.emotion_scores[emotion] >= 0.0


def test_no_forbidden_output(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(80)]
    engine = MarketPsychologyEngine(tmp_path)
    result = engine.infer(
        symbol="EURUSD",
        candles=_candle_set(closes),
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    blob = " ".join([
        result.narrative,
        *result.observations,
        result.psychology_state.dominant_emotion,
        *result.psychology_state.emotional_extremes,
        *result.opportunity_expansion,
    ]).lower()
    for word in FORBIDDEN_OUTPUT:
        assert word not in blob.split(), f"Forbidden word '{word}' in output"


def test_strong_uptrend_detects_greed_or_confidence(tmp_path: Path):
    closes = [1.10 + i * 0.001 for i in range(80)]
    engine = MarketPsychologyEngine(tmp_path)
    result = engine.infer(
        symbol="EURUSD",
        candles=_candle_set(closes),
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    dominant = result.psychology_state.dominant_emotion
    top_scores = sorted(result.emotion_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    top_emotions = {e for e, _ in top_scores}
    assert (
        dominant in {"greed", "euphoria", "confidence", "accumulation", "exhaustion"}
        or top_emotions & {"greed", "euphoria", "confidence", "accumulation"}
    )


def test_steep_decline_detects_fear_or_panic(tmp_path: Path):
    closes = [1.12 - i * 0.001 for i in range(80)]
    engine = MarketPsychologyEngine(tmp_path)
    result = engine.infer(
        symbol="EURUSD",
        candles=_candle_set(closes),
        structure=_structure(trend="bearish"),
        bias=_bias("bearish"),
        regime=_regime(),
    )
    top_scores = sorted(result.emotion_scores.items(), key=lambda x: x[1], reverse=True)[:4]
    top_emotions = {e for e, _ in top_scores}
    assert top_emotions & {"fear", "panic", "distribution", "hesitation", "uncertainty"}


def test_opportunity_expansion_hints_valid(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(80)]
    engine = MarketPsychologyEngine(tmp_path)
    result = engine.infer(
        symbol="EURUSD",
        candles=_candle_set(closes),
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    valid = {
        "contrarian_snapback", "momentum_continuation", "compression_release",
        "accumulation_breakout", "exhaustion_pause", "panic_capitulation_bounce",
        "distribution_fade", "hesitation_break",
    }
    for hint in result.opportunity_expansion:
        assert hint in valid


def test_integration_feeds_evidence_without_blocking(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(80)]
    psych_engine = MarketPsychologyEngine(tmp_path)
    psychology = psych_engine.infer(
        symbol="EURUSD",
        candles=_candle_set(closes),
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    synth_engine = EvidenceSynthesisEngine(tmp_path)
    summary = synth_engine.synthesise(
        "EURUSD",
        _candle_set(closes),
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
        market_psychology=psychology,
    )
    pieces = psychology.to_evidence_pieces()
    assert pieces
    assert all(p.category == "market_psychology" for p in pieces)
    assert summary.story_clear or summary.unclear_reason in {"insufficient", "incoherent", "random", ""}


def test_reports_written(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(80)]
    engine = MarketPsychologyEngine(tmp_path)
    engine.infer(
        symbol="EURUSD",
        candles=_candle_set(closes),
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    paths = engine.write_all_reports()
    assert paths[0] is not None and paths[0].exists()
    assert paths[1] is not None and paths[1].exists()
