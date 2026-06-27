"""Tests for Story Forecast Engine."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from intelligence.indicator_interpretation_engine import FORBIDDEN_OUTPUT
from intelligence.market_psychology_engine import MarketPsychologyEngine
from intelligence.market_story_engine import MarketStoryEngine, STORY_TIMEFRAMES
from intelligence.story_forecast_engine import (
    FORECAST_DNA,
    SCENARIO_NAMES,
    StoryForecastEngine,
)
from intelligence.trader_memory_engine import TraderMemoryEngine
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult, StructureEvent, SwingPoint


def _candles(closes: list[float], minutes: int = 60) -> pd.DataFrame:
    n = len(closes)
    times = pd.date_range("2024-01-01", periods=n, freq=f"{minutes}min", tz="UTC")
    return pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c + 0.0008 for c in closes],
        "low": [c - 0.0008 for c in closes],
        "close": closes,
        "tick_volume": np.linspace(100, 200, n),
        "spread": [1.0] * n,
    })


def _structure() -> MarketContext:
    bos = StructureEvent(
        kind="bos_bullish",
        bar_index=18,
        time=None,
        price=1.108,
        reference_price=1.105,
        description="Bullish BOS",
    )
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend="bullish",
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=(SwingPoint(5, None, 1.105, "high"),),
        swing_lows=(SwingPoint(8, None, 1.102, "low"),),
        structure_events=(bos,),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=bos,
        last_choch=None,
    )


def test_forecast_output_fields(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(45)]
    candles = {
        tf: _candles(closes, minutes={"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "H8": 480}[tf])
        for tf in STORY_TIMEFRAMES
    }
    story = MarketStoryEngine(tmp_path).build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.8, "test", ()),
        regime=RegimeResult("trending", 0.75, "test"),
        evaluation_moment=datetime(2024, 6, 10, 14, 0, tzinfo=timezone.utc),
    )
    forecast = StoryForecastEngine(tmp_path).forecast(
        symbol="EURUSD",
        market_story=story,
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.8, "test", ()),
        regime=RegimeResult("trending", 0.75, "test"),
        indicator_confirmation_boost=4.0,
    )
    assert forecast.story
    assert forecast.expected_next_move
    assert forecast.expected_pip_range > 0
    assert 0 <= forecast.confidence <= 100
    assert forecast.invalidation
    assert forecast.recommended_strategy
    assert forecast.direction in {"bullish", "bearish", "neutral"}
    assert forecast.most_likely_next in SCENARIO_NAMES
    probs = forecast.scenario_probabilities
    total = sum(probs.as_tuple())
    assert 99.0 <= total <= 101.0
    assert forecast.probability_rationale


def test_scenario_probabilities_answer_what_is_next(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(45)]
    candles = {
        tf: _candles(closes, minutes={"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "H8": 480}[tf])
        for tf in STORY_TIMEFRAMES
    }
    story = MarketStoryEngine(tmp_path).build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.8, "test", ()),
        regime=RegimeResult("trending", 0.75, "test"),
    )
    forecast = StoryForecastEngine(tmp_path).forecast(
        symbol="EURUSD",
        market_story=story,
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.8, "test", ()),
        regime=RegimeResult("trending", 0.75, "test"),
    )
    assert "Most likely:" in forecast.expected_next_move
    name, pct = forecast.scenario_probabilities.most_likely()
    assert forecast.most_likely_next == name
    assert pct >= max(
        forecast.scenario_probabilities.pullback,
        forecast.scenario_probabilities.reversal,
    )


def test_psychology_and_memory_influence_probabilities(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(50)]
    candles = {
        tf: _candles(closes, minutes={"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "H8": 480}[tf])
        for tf in STORY_TIMEFRAMES
    }
    structure = _structure()
    bias = MultiTimeframeBiasResult("bullish", 0.8, "test", ())
    regime = RegimeResult("trending", 0.75, "test")
    story = MarketStoryEngine(tmp_path).build(
        symbol="EURUSD",
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
    )
    engine = StoryForecastEngine(tmp_path)
    base = engine.forecast(
        symbol="EURUSD",
        market_story=story,
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
    )

    psych_engine = MarketPsychologyEngine(tmp_path)
    psychology = psych_engine.infer(
        symbol="EURUSD",
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
    )
    memory_engine = TraderMemoryEngine(tmp_path)
    memory_engine.record_trade(
        trade_id="mem-1",
        symbol="EURUSD",
        evidence_summary="Trend continuation evidence",
        psychological_state=psychology.psychology_state.to_dict(),
        story_explanation=story.primary_story,
        forecast="Continuation",
        outcome="win",
        evolution_path=("novel:bullish_campaign", "chapter:continuation"),
        r_multiple=1.0,
    )
    recall = memory_engine.recall(
        symbol="EURUSD",
        story_explanation=story.primary_story,
        psychological_state=psychology.psychology_state.to_dict(),
    )
    enriched = engine.forecast(
        symbol="EURUSD",
        market_story=story,
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
        evidence_synthesis=story.synthesis,
        market_psychology=psychology,
        trader_memory_recall=recall,
    )
    assert enriched.scenario_probabilities != base.scenario_probabilities or enriched.probability_rationale
    assert any("Psychology" in r or "Memory" in r or "synthesis" in r.lower() for r in enriched.probability_rationale)


def test_probabilities_not_used_as_filters(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(40)]
    candles = {tf: _candles(closes) for tf in STORY_TIMEFRAMES}
    story = MarketStoryEngine(tmp_path).build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.75, "test", ()),
        regime=RegimeResult("trending", 0.7, "test"),
    )
    forecast = StoryForecastEngine(tmp_path).forecast(
        symbol="EURUSD",
        market_story=story,
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.75, "test", ()),
        regime=RegimeResult("trending", 0.7, "test"),
    )
    blob = " ".join([
        forecast.expected_next_move,
        *forecast.probability_rationale,
        forecast.most_likely_next,
    ]).lower()
    for word in FORBIDDEN_OUTPUT:
        assert word not in blob.split()


def test_forecast_dna_exported():
    assert "most likely next" in FORECAST_DNA.lower()
    assert "never filter" in FORECAST_DNA.lower()


def test_forecast_quality_report_written(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(40)]
    candles = {tf: _candles(closes) for tf in STORY_TIMEFRAMES}
    engine = StoryForecastEngine(tmp_path)
    story = MarketStoryEngine(tmp_path).build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.75, "test", ()),
        regime=RegimeResult("trending", 0.7, "test"),
    )
    engine.forecast(
        symbol="EURUSD",
        market_story=story,
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.75, "test", ()),
        regime=RegimeResult("trending", 0.7, "test"),
    )
    path = engine.write_forecast_quality_report()
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "Forecast Quality Report" in text
    assert "Continuation:" in text
    assert "inform action" in text.lower()


def test_forecast_report_written(tmp_path: Path):
    closes = [1.10 + i * 0.0001 for i in range(40)]
    candles = {tf: _candles(closes) for tf in STORY_TIMEFRAMES}
    story_engine = MarketStoryEngine(tmp_path)
    forecast_engine = StoryForecastEngine(tmp_path)
    story = story_engine.build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.7, "test", ()),
        regime=RegimeResult("trending", 0.7, "test"),
    )
    forecast_engine.forecast(
        symbol="EURUSD",
        market_story=story,
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.7, "test", ()),
        regime=RegimeResult("trending", 0.7, "test"),
    )
    path = forecast_engine.write_report()
    assert path is not None
    assert "Story Forecast Report" in path.read_text(encoding="utf-8")


def test_indicator_boost_refines_confidence(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(40)]
    candles = {tf: _candles(closes) for tf in STORY_TIMEFRAMES}
    story = MarketStoryEngine(tmp_path).build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.75, "test", ()),
        regime=RegimeResult("trending", 0.7, "test"),
    )
    engine = StoryForecastEngine(tmp_path)
    base = engine.forecast(
        symbol="EURUSD",
        market_story=story,
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.75, "test", ()),
        regime=RegimeResult("trending", 0.7, "test"),
        indicator_confirmation_boost=0.0,
    )
    boosted = engine.forecast(
        symbol="EURUSD",
        market_story=story,
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.75, "test", ()),
        regime=RegimeResult("trending", 0.7, "test"),
        indicator_confirmation_boost=8.0,
    )
    assert boosted.confidence >= base.confidence


def test_narrative_forecast_bridge(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(40)]
    candles = {tf: _candles(closes) for tf in STORY_TIMEFRAMES}
    story = MarketStoryEngine(tmp_path).build(
        symbol="EURUSD",
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.75, "test", ()),
        regime=RegimeResult("trending", 0.7, "test"),
    )
    forecast = StoryForecastEngine(tmp_path).forecast(
        symbol="EURUSD",
        market_story=story,
        candles=candles,
        structure=_structure(),
        bias=MultiTimeframeBiasResult("bullish", 0.75, "test", ()),
        regime=RegimeResult("trending", 0.7, "test"),
    )
    legacy = forecast.to_narrative_forecast()
    assert legacy.current_story == forecast.story
    assert legacy.expected_pip_range == forecast.expected_pip_range
