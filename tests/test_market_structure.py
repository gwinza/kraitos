"""Tests for market structure analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from strategies import MarketStructureAnalyzer, MarketStructureConfig, MarketStructureError


def _candles_from_closes(closes: np.ndarray) -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index, close in enumerate(closes):
        wiggle = 0.0004 if index % 5 == 0 else 0.0001
        rows.append(
            {
                "time": start + timedelta(hours=index),
                "open": close,
                "high": close + wiggle,
                "low": close - wiggle,
                "close": close,
                "tick_volume": 100,
                "spread": 1.5,
            }
        )
    return pd.DataFrame(rows)


def _bullish_structure(length: int = 60) -> np.ndarray:
    steps = np.arange(length)
    return 1.10 + steps * 0.0005 + np.sin(steps * 0.8) * 0.002


def _bearish_structure(length: int = 60) -> np.ndarray:
    steps = np.arange(length)
    return 1.14 - steps * 0.0005 - np.sin(steps * 0.8) * 0.002


def test_detects_bullish_structure():
    analyzer = MarketStructureAnalyzer(MarketStructureConfig(min_candles=40))
    context = analyzer.analyze(_candles_from_closes(_bullish_structure()), symbol="EURUSD")

    assert context.trend == "bullish"
    assert context.higher_highs is True
    assert context.higher_lows is True
    assert len(context.swing_highs) > 0
    assert len(context.swing_lows) > 0


def test_detects_bearish_structure():
    analyzer = MarketStructureAnalyzer(MarketStructureConfig(min_candles=40))
    context = analyzer.analyze(_candles_from_closes(_bearish_structure()), symbol="EURUSD")

    assert context.trend == "bearish"
    assert context.lower_highs is True
    assert context.lower_lows is True


def test_detects_structure_events():
    analyzer = MarketStructureAnalyzer(MarketStructureConfig(min_candles=40))
    context = analyzer.analyze(_candles_from_closes(_bullish_structure()))

    kinds = {event.kind for event in context.structure_events}
    assert "higher_high" in kinds or "higher_low" in kinds


def test_builds_support_and_resistance_zones():
    analyzer = MarketStructureAnalyzer(
        MarketStructureConfig(min_candles=40, min_zone_touches=2, zone_tolerance_pct=0.002)
    )
    context = analyzer.analyze(_candles_from_closes(_bullish_structure()))

    assert isinstance(context.support_zones, tuple)
    assert isinstance(context.resistance_zones, tuple)


def test_detects_liquidity_zones_from_equal_levels():
    closes = np.full(60, 1.10)
    closes[10:13] = 1.1050
    closes[25:28] = 1.1051
    closes[40:43] = 1.0950
    closes[50:53] = 1.0951

    analyzer = MarketStructureAnalyzer(
        MarketStructureConfig(
            min_candles=40,
            liquidity_tolerance_pct=0.002,
            min_zone_touches=2,
        )
    )
    context = analyzer.analyze(_candles_from_closes(closes))

    assert len(context.liquidity_zones) >= 1
    assert context.liquidity_zones[0].kind == "liquidity"


def test_context_is_usable_by_other_modules():
    analyzer = MarketStructureAnalyzer(MarketStructureConfig(min_candles=40))
    context = analyzer.analyze(
        _candles_from_closes(_bullish_structure()),
        symbol="eurusd",
        timeframe="h1",
    )

    assert context.symbol == "EURUSD"
    assert context.timeframe == "H1"
    assert context.last_bos is None or context.last_bos.kind.startswith("bos_")
    assert context.last_choch is None or context.last_choch.kind.startswith("choch_")


def test_rejects_insufficient_candles():
    analyzer = MarketStructureAnalyzer(MarketStructureConfig(min_candles=40))

    with pytest.raises(MarketStructureError, match="At least 40"):
        analyzer.analyze(_candles_from_closes(_bullish_structure(length=20)))
