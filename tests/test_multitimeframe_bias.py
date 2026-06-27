"""Tests for multi-timeframe bias analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from strategies import MultiTimeframeBiasAnalyzer, MultiTimeframeBiasError


def _series(closes: np.ndarray, *, spread: float = 1.5, volume: float = 200.0) -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index, close in enumerate(closes):
        rows.append(
            {
                "time": start + timedelta(minutes=index),
                "open": close - 0.0001,
                "high": close + 0.0002,
                "low": close - 0.0002,
                "close": close,
                "tick_volume": volume,
                "spread": spread,
            }
        )
    return pd.DataFrame(rows)


def _bullish(length: int = 80) -> np.ndarray:
    return np.linspace(1.10, 1.12, length)


def _bearish(length: int = 80) -> np.ndarray:
    return np.linspace(1.12, 1.10, length)


def _neutral(length: int = 80) -> np.ndarray:
    return np.full(length, 1.10)


def _bundle(
    macro: np.ndarray,
    structure: np.ndarray,
    setup: np.ndarray,
    precision: np.ndarray,
) -> dict[str, pd.DataFrame]:
    return {
        "H8": _series(macro),
        "H4": _series(macro),
        "H1": _series(structure),
        "M15": _series(setup),
        "M5": _series(setup),
        "M1": _series(precision),
    }


def test_bullish_bias_when_all_timeframes_align():
    data = _bundle(_bullish(), _bullish(), _bullish(), _bullish())
    result = MultiTimeframeBiasAnalyzer().evaluate(data)

    assert result.bias == "bullish"
    assert result.confidence >= 0.6
    assert "Bullish bias" in result.explanation
    assert len(result.layers) == 6


def test_bearish_bias_when_all_timeframes_align():
    data = _bundle(_bearish(), _bearish(), _bearish(), _bearish())
    result = MultiTimeframeBiasAnalyzer().evaluate(data)

    assert result.bias == "bearish"
    assert result.confidence >= 0.6
    assert "Bearish bias" in result.explanation


def test_neutral_bias_on_flat_market():
    data = _bundle(_neutral(), _neutral(), _neutral(), _neutral())
    result = MultiTimeframeBiasAnalyzer().evaluate(data)

    assert result.bias == "neutral"
    assert "Neutral bias" in result.explanation


def test_layers_include_roles():
    data = _bundle(_bullish(), _bullish(), _bullish(), _bullish())
    result = MultiTimeframeBiasAnalyzer().evaluate(data)

    roles = {layer.timeframe: layer.role for layer in result.layers}
    assert roles["H8"] == "macro"
    assert roles["H4"] == "macro"
    assert roles["H1"] == "structure"
    assert roles["M15"] == "setup"
    assert roles["M5"] == "setup"
    assert roles["M1"] == "precision_entry"


def test_rejects_missing_timeframe():
    data = _bundle(_bullish(), _bullish(), _bullish(), _bullish())
    del data["M1"]

    with pytest.raises(MultiTimeframeBiasError, match="Missing required timeframes"):
        MultiTimeframeBiasAnalyzer().evaluate(data)


def test_rejects_insufficient_candles():
    data = _bundle(_bullish(length=20), _bullish(), _bullish(), _bullish())

    with pytest.raises(MultiTimeframeBiasError, match="H8 requires"):
        MultiTimeframeBiasAnalyzer().evaluate(data)
