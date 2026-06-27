"""Tests for Evidence Synthesis Engine."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from intelligence.evidence_synthesis_engine import (
    EVIDENCE_TIMEFRAMES,
    EvidenceSynthesisEngine,
)
from intelligence.market_story_engine import MarketStoryEngine, STORY_TIMEFRAMES
from intelligence.story_evolution_engine import StoryEvolutionEngine
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult, SwingPoint


def _candles(
    closes: list[float],
    *,
    minutes: int = 60,
    volume_scale: float = 1.0,
) -> pd.DataFrame:
    n = len(closes)
    times = pd.date_range("2024-01-01", periods=n, freq=f"{minutes}min", tz="UTC")
    return pd.DataFrame({
        "time": times,
        "open": [c - 0.0001 for c in closes],
        "high": [c + 0.0008 for c in closes],
        "low": [c - 0.0008 for c in closes],
        "close": closes,
        "tick_volume": np.linspace(100, 220, n) * volume_scale,
        "spread": [1.0] * n,
    })


def _candle_set(closes: list[float]) -> dict[str, pd.DataFrame]:
    return {
        tf: _candles(closes, minutes={"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "H8": 480}[tf])
        for tf in EVIDENCE_TIMEFRAMES
    }


def _structure(trend: str = "bullish") -> MarketContext:
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend=trend,  # type: ignore[arg-type]
        higher_highs=trend == "bullish",
        higher_lows=trend == "bullish",
        lower_highs=trend == "bearish",
        lower_lows=trend == "bearish",
        swing_highs=(SwingPoint(5, None, 1.105, "high"),),
        swing_lows=(SwingPoint(8, None, 1.102, "low"),),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


def _bias(direction: str = "bullish") -> MultiTimeframeBiasResult:
    return MultiTimeframeBiasResult(direction, 0.75, "test", ())


def _regime() -> RegimeResult:
    return RegimeResult("trending", 0.8, "test")


def test_evidence_collection_from_candles(tmp_path: Path):
    engine = EvidenceSynthesisEngine(tmp_path)
    candles = _candle_set([1.10 + i * 0.0003 for i in range(50)])
    summary = engine.synthesise(
        "EURUSD",
        candles,
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    assert len(summary.supporting_evidence) >= 3
    assert summary.current_explanation
    assert summary.confidence > 0


def test_synthesis_produces_single_explanation(tmp_path: Path):
    engine = EvidenceSynthesisEngine(tmp_path)
    candles = _candle_set([1.10 + i * 0.0002 for i in range(50)])
    summary = engine.synthesise(
        "EURUSD",
        candles,
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
        evaluation_moment=datetime(2024, 6, 10, 14, 0, tzinfo=timezone.utc),
    )
    assert summary.story_clear
    assert "trending" in summary.current_explanation.lower() or "bullish" in summary.current_explanation.lower()
    assert summary.probable_next_event
    assert summary.recommended_action


def test_conflicting_evidence_interpreted_not_unclear(tmp_path: Path):
    engine = EvidenceSynthesisEngine(tmp_path)
    candles = _candle_set([1.10 + i * 0.0003 for i in range(50)])
    evolution = StoryEvolutionEngine(tmp_path)
    evo_state = evolution.update("EURUSD", candles)
    summary = engine.synthesise(
        "EURUSD",
        candles,
        structure=_structure("bullish"),
        bias=_bias("bullish"),
        regime=_regime(),
        story_evolution_state=evo_state,
    )
    if summary.contradicting_evidence:
        assert summary.story_clear
        assert summary.unclear_reason == ""
        assert "conflict" in summary.current_explanation.lower() or "pressure" in summary.current_explanation.lower()


def test_insufficient_evidence_is_unclear(tmp_path: Path):
    engine = EvidenceSynthesisEngine(tmp_path)
    sparse = {"M1": _candles([1.10, 1.1001], minutes=1)}
    summary = engine.synthesise("EURUSD", sparse)
    assert not summary.story_clear
    assert summary.unclear_reason == "insufficient"


def test_four_questions_answered(tmp_path: Path):
    engine = EvidenceSynthesisEngine(tmp_path)
    candles = _candle_set([1.10 + i * 0.00025 for i in range(50)])
    summary = engine.synthesise(
        "EURUSD",
        candles,
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    assert summary.current_explanation  # WHAT + WHY
    assert summary.probable_next_event  # WHAT likely next
    assert summary.recommended_action  # WHAT should Kraitos do
    assert summary.risk_level in {"low", "medium", "high"}


def test_allocation_bias_mapping(tmp_path: Path):
    engine = EvidenceSynthesisEngine(tmp_path)
    candles = _candle_set([1.10 + i * 0.0004 for i in range(50)])
    summary = engine.synthesise(
        "EURUSD",
        candles,
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    assert summary.allocation_bias in {"harvest", "proper", "elite", "scout", "micro"}


def test_market_story_engine_delegates_to_synthesis(tmp_path: Path):
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
    assert result.synthesis is not None
    assert result.primary_story == result.synthesis.current_explanation or "[interpreted conflict]" in result.primary_story


def test_synthesis_reports_written(tmp_path: Path):
    engine = EvidenceSynthesisEngine(tmp_path)
    candles = _candle_set([1.10 + i * 0.0002 for i in range(50)])
    engine.synthesise("EURUSD", candles, structure=_structure(), bias=_bias(), regime=_regime())
    paths = engine.write_all_reports()
    assert all(p is not None and p.exists() for p in paths)
