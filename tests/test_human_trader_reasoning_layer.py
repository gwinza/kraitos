"""Tests for Human Trader Reasoning Layer — explain like an experienced trader."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from intelligence.human_trader_reasoning_layer import (
    HUMAN_TRADER_REASONING_DNA,
    REASONING_QUESTIONS,
    HumanTraderReasoningLayer,
    TradeReasoning,
)
from intelligence.indicator_interpretation_engine import FORBIDDEN_OUTPUT
from intelligence.market_psychology_engine import MarketPsychologyEngine
from intelligence.market_story_engine import MarketStoryEngine, STORY_TIMEFRAMES
from intelligence.story_forecast_engine import StoryForecastEngine
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
        for tf in STORY_TIMEFRAMES
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


def _full_context(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(80)]
    candles = _candle_set(closes)
    structure = _structure()
    bias = _bias()
    regime = _regime()
    story = MarketStoryEngine(tmp_path).build(
        symbol="EURUSD",
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
        evaluation_moment=datetime(2024, 6, 10, 14, 0, tzinfo=timezone.utc),
    )
    from intelligence.indicator_interpretation_engine import IndicatorInterpretationEngine

    interpretation = IndicatorInterpretationEngine(tmp_path).interpret(
        symbol="EURUSD",
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
    )
    psychology = MarketPsychologyEngine(tmp_path).infer(
        symbol="EURUSD",
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
        indicator_interpretation=interpretation,
    )
    forecast = StoryForecastEngine(tmp_path).forecast(
        symbol="EURUSD",
        market_story=story,
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
        evidence_synthesis=story.synthesis,
        market_psychology=psychology,
    )
    return candles, story, interpretation, psychology, forecast


def test_dna_exported():
    assert "experienced trader" in HUMAN_TRADER_REASONING_DNA.lower()
    assert "never filters" in HUMAN_TRADER_REASONING_DNA.lower()


def test_explain_produces_all_seven_questions(tmp_path: Path):
    _, story, interpretation, psychology, forecast = _full_context(tmp_path)
    layer = HumanTraderReasoningLayer(tmp_path)
    reasoning = layer.explain(
        symbol="EURUSD",
        setup_kind="harvest",
        market_story=story,
        story_forecast=forecast,
        indicator_interpretation=interpretation,
        market_psychology=psychology,
    )
    assert isinstance(reasoning, TradeReasoning)
    for field in REASONING_QUESTIONS:
        assert getattr(reasoning, field if field != "contradicting_evidence" else field) is not None
    assert reasoning.what_is_happening
    assert reasoning.why_is_it_happening
    assert reasoning.what_participants_feel
    assert reasoning.what_is_likely_next
    assert reasoning.what_opportunity_exists
    assert reasoning.why_opportunity_attractive
    assert isinstance(reasoning.contradicting_evidence, tuple)


def test_trade_thesis_reads_like_human_trader(tmp_path: Path):
    _, story, interpretation, psychology, forecast = _full_context(tmp_path)
    reasoning = HumanTraderReasoningLayer(tmp_path).explain(
        symbol="EURUSD",
        market_story=story,
        story_forecast=forecast,
        indicator_interpretation=interpretation,
        market_psychology=psychology,
    )
    assert reasoning.trade_thesis
    assert len(reasoning.trade_thesis.split()) >= 12
    assert reasoning.trade_thesis[0].isupper()


def test_no_forbidden_filter_language(tmp_path: Path):
    _, story, interpretation, psychology, forecast = _full_context(tmp_path)
    reasoning = HumanTraderReasoningLayer(tmp_path).explain(
        symbol="EURUSD",
        market_story=story,
        story_forecast=forecast,
        indicator_interpretation=interpretation,
        market_psychology=psychology,
    )
    blob = " ".join([
        reasoning.trade_thesis,
        reasoning.what_is_happening,
        reasoning.what_opportunity_exists,
        reasoning.why_opportunity_attractive,
        *reasoning.contradicting_evidence,
    ]).lower()
    for word in FORBIDDEN_OUTPUT:
        assert word not in blob.split(), f"Forbidden word '{word}' in reasoning"


def test_evidence_pieces_enrich_not_block(tmp_path: Path):
    _, story, interpretation, psychology, forecast = _full_context(tmp_path)
    reasoning = HumanTraderReasoningLayer(tmp_path).explain(
        symbol="EURUSD",
        market_story=story,
        story_forecast=forecast,
        indicator_interpretation=interpretation,
        market_psychology=psychology,
    )
    pieces = reasoning.to_evidence_pieces()
    assert pieces
    assert all(p.category == "human_trader_reasoning" for p in pieces)


def test_report_written(tmp_path: Path):
    _, story, interpretation, psychology, forecast = _full_context(tmp_path)
    layer = HumanTraderReasoningLayer(tmp_path)
    layer.explain(
        symbol="EURUSD",
        market_story=story,
        story_forecast=forecast,
        indicator_interpretation=interpretation,
        market_psychology=psychology,
    )
    path = layer.write_human_trader_reasoning_report()
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "Human Trader Reasoning Report" in text
    assert "trade_thesis" in text.lower() or "Thesis" in text
    assert "What is happening?" in text
