"""Tests for trend strength scoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from intelligence.trend_strength_engine import (
    QUALITY_THRESHOLDS,
    TrendStrengthEngine,
)
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult, SwingPoint, TimeframeBiasDetail


def _candles(closes: np.ndarray, *, minutes: int = 60) -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index, close in enumerate(closes):
        rows.append(
            {
                "time": start + timedelta(minutes=minutes * index),
                "open": close - 0.00005,
                "high": close + 0.0002,
                "low": close - 0.0002,
                "close": close,
                "tick_volume": 300.0,
                "spread": 1.0,
            }
        )
    return pd.DataFrame(rows)


def _bias(direction: str = "bullish", confidence: float = 0.8) -> MultiTimeframeBiasResult:
    layers = tuple(
        TimeframeBiasDetail(tf, direction, 0.7, role)  # type: ignore[arg-type]
        for tf, role in [
            ("H8", "macro"),
            ("H4", "macro"),
            ("H1", "structure"),
            ("M15", "setup"),
            ("M5", "setup"),
            ("M1", "precision_entry"),
        ]
    )
    return MultiTimeframeBiasResult(
        bias=direction,  # type: ignore[arg-type]
        confidence=confidence,
        explanation="test",
        layers=layers,
    )


def _structure(trend: str = "bullish") -> MarketContext:
    swing = SwingPoint(
        bar_index=5,
        time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        price=1.10,
        kind="high",  # type: ignore[arg-type]
    )
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend=trend,  # type: ignore[arg-type]
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=(swing, swing),
        swing_lows=(swing, swing),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


def _regime(name: str = "trending") -> RegimeResult:
    return RegimeResult(regime=name, confidence=0.9, reason="test")  # type: ignore[arg-type]


def test_trend_strength_scores_strong_uptrend_high() -> None:
    engine = TrendStrengthEngine()
    closes = np.linspace(1.10, 1.16, 80)
    candles = {
        "H8": _candles(closes, minutes=480),
        "H4": _candles(closes, minutes=240),
        "H1": _candles(closes),
        "M15": _candles(np.linspace(1.14, 1.16, 80), minutes=15),
        "M5": _candles(np.linspace(1.12, 1.16, 80), minutes=5),
        "M1": _candles(np.linspace(1.15, 1.16, 80), minutes=1),
    }
    _, result = engine.evaluate(
        symbol="EURUSD",
        candles=candles,
        bias=_bias("bullish"),
        structure=_structure("bullish"),
        regime=_regime("trending"),
        spread_pips=1.0,
        spread_limit=3.0,
    )
    assert 0 <= result.score <= 100
    assert result.quality in {
        "institutional_trend",
        "developing_trend",
        "weak_trend",
        "range_or_noise",
    }
    assert result.score >= QUALITY_THRESHOLDS["weak_trend"]


def test_trend_strength_classifies_range_low() -> None:
    engine = TrendStrengthEngine()
    flat = np.full(80, 1.10)
    candles = {
        "H8": _candles(flat, minutes=480),
        "H4": _candles(flat, minutes=240),
        "H1": _candles(flat),
        "M15": _candles(flat, minutes=15),
        "M5": _candles(flat, minutes=5),
        "M1": _candles(flat, minutes=1),
    }
    _, result = engine.evaluate(
        symbol="EURUSD",
        candles=candles,
        bias=_bias("neutral", confidence=0.4),
        structure=_structure("ranging"),
        regime=_regime("ranging"),
        spread_pips=1.0,
        spread_limit=3.0,
    )
    assert result.score < QUALITY_THRESHOLDS["developing_trend"]


def test_quality_threshold_mapping() -> None:
    engine = TrendStrengthEngine()
    snapshot = TrendStrengthEngine()._analyzer.analyze(  # noqa: SLF001
        symbol="EURUSD",
        candles={
            "H1": _candles(np.linspace(1.10, 1.14, 80)),
            "M1": _candles(np.linspace(1.13, 1.14, 80), minutes=1),
            "M5": _candles(np.linspace(1.12, 1.14, 80), minutes=5),
        },
        bias=_bias("bullish"),
        structure=_structure("bullish"),
        regime=_regime("trending"),
        spread_pips=1.0,
        spread_limit=3.0,
    )
    scored = engine.score_snapshot(snapshot, _bias("bullish"), _structure("bullish"), _regime("trending"))
    if scored.score >= 80:
        assert scored.quality == "institutional_trend"
    elif scored.score >= 60:
        assert scored.quality == "developing_trend"
    elif scored.score >= 40:
        assert scored.quality == "weak_trend"
    else:
        assert scored.quality == "range_or_noise"
