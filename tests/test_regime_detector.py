"""Tests for the market regime detector."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from strategies import RegimeDetector, RegimeDetectorConfig, RegimeDetectorError


def _make_candles(
    closes: np.ndarray,
    *,
    spread: float = 1.5,
    volume: float = 200.0,
    noise: float = 0.0002,
) -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index, close in enumerate(closes):
        open_ = close - noise / 2
        high = close + noise
        low = close - noise
        rows.append(
            {
                "time": start + timedelta(hours=index),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": volume,
                "spread": spread,
            }
        )
    return pd.DataFrame(rows)


def _trending_closes(length: int = 80, step: float = 0.0008) -> np.ndarray:
    return np.linspace(1.10, 1.10 + step * length, length)


def _ranging_closes(length: int = 80) -> np.ndarray:
    base = np.full(length, 1.10)
    oscillation = np.sin(np.linspace(0, 12, length)) * 0.0001
    return base + oscillation


def _volatile_closes(length: int = 80) -> np.ndarray:
    rng = np.random.default_rng(42)
    base = np.linspace(1.10, 1.12, length)
    shocks = np.zeros(length)
    shocks[-5:] = rng.normal(0, 0.003, 5)
    return base + shocks


def test_detects_trending_market():
    detector = RegimeDetector(RegimeDetectorConfig(min_candles=60))
    result = detector.detect(_make_candles(_trending_closes()))

    assert result.regime == "trending"
    assert result.confidence > 0
    assert "slope" in result.reason.lower()


def test_detects_ranging_market():
    detector = RegimeDetector(
        RegimeDetectorConfig(min_candles=60, compression_atr_ratio=1.0)
    )
    result = detector.detect(_make_candles(_ranging_closes()))

    assert result.regime == "ranging"
    assert "compressed" in result.reason.lower() or "flat" in result.reason.lower()


def test_detects_volatile_market():
    detector = RegimeDetector(RegimeDetectorConfig(min_candles=60))
    candles = _make_candles(_volatile_closes())
    candles.loc[candles.index[-1], ["high", "low"]] = [1.16, 1.08]

    result = detector.detect(candles)

    assert result.regime in {"volatile", "news_risk"}
    assert result.confidence > 0


def test_detects_low_liquidity():
    detector = RegimeDetector(RegimeDetectorConfig(min_candles=60, spread_limit=2.0))
    candles = _make_candles(_ranging_closes(), spread=4.0, volume=40.0)

    result = detector.detect(candles, spread_limit=2.0)

    assert result.regime == "low_liquidity"
    assert "spread" in result.reason.lower()


def test_detects_news_risk_when_flag_active():
    detector = RegimeDetector(RegimeDetectorConfig(min_candles=60))
    result = detector.detect(_make_candles(_ranging_closes()), news_risk_active=True)

    assert result.regime == "news_risk"
    assert result.confidence >= 0.9
    assert "news" in result.reason.lower()


def test_rejects_insufficient_candles():
    detector = RegimeDetector(RegimeDetectorConfig(min_candles=60))

    with pytest.raises(RegimeDetectorError, match="At least 60"):
        detector.detect(_make_candles(_ranging_closes(length=30)))
