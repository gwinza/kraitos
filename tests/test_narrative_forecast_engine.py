"""Tests for Narrative Forecast Engine."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from intelligence.market_narrative_engine import MarketNarrativeEngine
from intelligence.narrative_forecast_engine import NarrativeForecastEngine
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult, SwingPoint


def _candles(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    times = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c + 0.001 for c in closes],
        "low": [c - 0.001 for c in closes],
        "close": closes,
        "tick_volume": [150] * n,
        "spread": [1.0] * n,
    })


def _setup(tmp_path: Path):
    closes = [1.10 + i * 0.0004 for i in range(40)]
    candles = {tf: _candles(closes) for tf in ("M1", "M5", "M15", "H1", "H4", "H8")}
    structure = MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend="bullish",
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=(SwingPoint(5, None, 1.11, "high"),),
        swing_lows=(SwingPoint(8, None, 1.09, "low"),),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )
    bias = MultiTimeframeBiasResult("bullish", 0.75, "test", ())
    regime = RegimeResult("trending", 0.8, "test")
    narrative = MarketNarrativeEngine(tmp_path).build(
        symbol="EURUSD",
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
    )
    return candles, structure, bias, regime, narrative


def test_forecast_output_fields(tmp_path: Path):
    candles, structure, bias, regime, narrative = _setup(tmp_path)
    engine = NarrativeForecastEngine(tmp_path)
    forecast = engine.forecast(
        symbol="EURUSD",
        narrative=narrative,
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
    )
    assert forecast.current_story
    assert forecast.expected_next_move
    assert forecast.expected_pip_range > 0
    assert 0 <= forecast.confidence <= 100
    assert forecast.invalidation
    assert forecast.recommended_strategy
    assert forecast.direction in {"bullish", "bearish", "neutral"}


def test_forecast_report_written(tmp_path: Path):
    candles, structure, bias, regime, narrative = _setup(tmp_path)
    engine = NarrativeForecastEngine(tmp_path)
    engine.forecast(
        symbol="EURUSD",
        narrative=narrative,
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
    )
    path = engine.write_report()
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "Narrative Forecast Report" in text
    assert "EURUSD" in text


def test_micro_class_forecast_pip_range(tmp_path: Path):
    from intelligence.market_narrative_engine import MarketNarrativeResult, TimeframeNarrative

    narrative = MarketNarrativeResult(
        symbol="EURUSD",
        slices=(
            TimeframeNarrative("M5", "compression", "squeeze", "pop", 65.0),
        ),
        primary_story="compression pop",
        primary_phase="compression",
        overall_confidence=58.0,
        compression_detected=True,
        micro_narrative_class="compression_pop",
    )
    candles, structure, bias, regime, _ = _setup(tmp_path)
    forecast = NarrativeForecastEngine(tmp_path).forecast(
        symbol="EURUSD",
        narrative=narrative,
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
    )
    assert 2.0 <= forecast.expected_pip_range <= 6.0
    assert forecast.recommended_strategy in {"compression_breakout", "micro_harvest"}


def test_exit_profile_continuation_allows_runner(tmp_path: Path):
    from intelligence.narrative_forecast_engine import NarrativeForecastEngine

    profile = NarrativeForecastEngine.exit_profile_for("trend_pause_resume")
    assert profile.allow_runner
    assert profile.trail_timeframe == "M5"

    fast = NarrativeForecastEngine.exit_profile_for("liquidity_sweep_snapback")
    assert not fast.allow_runner
    assert fast.target_multiplier > 1.0


def test_indicator_boost_refines_confidence(tmp_path: Path):
    candles, structure, bias, regime, narrative = _setup(tmp_path)
    engine = NarrativeForecastEngine(tmp_path)
    base = engine.forecast(
        symbol="EURUSD",
        narrative=narrative,
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
        indicator_confirmation_boost=0.0,
    )
    boosted = engine.forecast(
        symbol="EURUSD",
        narrative=narrative,
        candles=candles,
        structure=structure,
        bias=bias,
        regime=regime,
        indicator_confirmation_boost=8.0,
    )
    assert boosted.confidence >= base.confidence
