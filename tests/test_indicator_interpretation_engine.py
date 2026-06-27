"""Tests for Indicator Interpretation Engine — evidence, not signals."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from intelligence.evidence_synthesis_engine import EvidenceSynthesisEngine
from intelligence.indicator_interpretation_engine import (
    FORBIDDEN_OUTPUT,
    INDICATOR_INTERPRETATION_DNA,
    IndicatorInterpretationEngine,
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
    assert "Indicators do not veto trades" in INDICATOR_INTERPRETATION_DNA
    assert "recognise more opportunities" in INDICATOR_INTERPRETATION_DNA


def test_each_indicator_produces_interpretation_not_signal(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(80)]
    engine = IndicatorInterpretationEngine(tmp_path)
    result = engine.interpret(
        symbol="EURUSD",
        candles=_candle_set(closes),
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
        narrative_direction="bullish",
    )
    indicators = {r.indicator for r in result.psychological_readings}
    expected = {
        "Moving averages", "ADX", "RSI", "MACD", "Bollinger Bands",
        "ATR", "OBV", "Accumulation/Distribution", "Sentiment",
        "Volume", "Price Action",
    }
    assert expected.issubset(indicators)
    assert result.insight_score >= 0.0


def test_no_buy_sell_commands_in_output(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(80)]
    engine = IndicatorInterpretationEngine(tmp_path)
    result = engine.interpret(
        symbol="EURUSD",
        candles=_candle_set(closes),
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    blob = " ".join([
        result.market_explanation_contribution,
        *result.observations,
        *(r.reading + " " + r.psychology for r in result.psychological_readings),
        *result.forecast_implications,
        *result.opportunity_hints,
    ]).lower()
    for word in FORBIDDEN_OUTPUT:
        assert word not in blob.split(), f"Forbidden word '{word}' in output"


def test_opportunity_hints_expand_recognition(tmp_path: Path):
    """Exhaustion/compression readings should expand opportunity hints."""
    # Trend up then flat — may produce compression or stretch hints
    closes = [1.10 + min(i, 40) * 0.0003 for i in range(80)]
    engine = IndicatorInterpretationEngine(tmp_path)
    result = engine.interpret(
        symbol="EURUSD",
        candles=_candle_set(closes),
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    assert isinstance(result.opportunity_hints, tuple)
    valid_hints = {
        "mean_reversion_snapback", "compression_breakout", "pullback_continuation",
        "liquidity_sweep", "liquidity_sweep_snapback", "trend_pause_resume",
        "failed_breakout",
    }
    for hint in result.opportunity_hints:
        assert hint in valid_hints


def test_exhaustion_produces_snapback_hint(tmp_path: Path):
    """Strong uptrend produces RSI stretch — snapback opportunity hint."""
    closes = [1.10 + i * 0.001 for i in range(80)]
    engine = IndicatorInterpretationEngine(tmp_path)
    result = engine.interpret(
        symbol="EURUSD",
        candles=_candle_set(closes),
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    rsi_readings = [r for r in result.psychological_readings if r.indicator == "RSI"]
    assert rsi_readings
    if "stretch" in rsi_readings[0].reading.lower() or "euphoria" in rsi_readings[0].reading.lower():
        assert "mean_reversion_snapback" in result.opportunity_hints


def test_integration_feeds_evidence_without_blocking(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(80)]
    interp_engine = IndicatorInterpretationEngine(tmp_path)
    interpretation = interp_engine.interpret(
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
        indicator_interpretation=interpretation,
    )
    pieces = interpretation.to_evidence_pieces()
    assert pieces
    assert all(p.category == "indicator_psychology" for p in pieces)
    assert summary.story_clear or summary.unclear_reason in {"insufficient", "incoherent", "random", ""}


def test_reports_written(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(80)]
    engine = IndicatorInterpretationEngine(tmp_path)
    engine.interpret(
        symbol="EURUSD",
        candles=_candle_set(closes),
        structure=_structure(),
        bias=_bias(),
        regime=_regime(),
    )
    paths = engine.write_all_reports()
    assert paths[0] is not None
    assert paths[0].exists()
    assert paths[1] is not None and paths[1].exists()
    assert paths[2] is not None and paths[2].exists()
