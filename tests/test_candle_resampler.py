"""Tests for multi-timeframe candle resampling."""

from __future__ import annotations

import pandas as pd
import pytest

from backtesting.candle_resampler import build_multitimeframe_candles, build_symbol_candles

pytestmark = pytest.mark.offline


def _m1_frame(rows: int = 600) -> pd.DataFrame:
    times = pd.date_range("2025-01-06 08:00", periods=rows, freq="min", tz="UTC")
    close = pd.Series([1.10 + index * 0.00001 for index in range(rows)])
    return pd.DataFrame(
        {
            "time": times,
            "open": close - 0.0001,
            "high": close + 0.0002,
            "low": close - 0.0002,
            "close": close,
            "tick_volume": 1000,
            "spread": 1.0,
        }
    )


def test_build_multitimeframe_candles_creates_distinct_lengths():
    candles = build_multitimeframe_candles(_m1_frame(600))
    assert len(candles["M1"]) == 600
    assert len(candles["M5"]) == pytest.approx(120, rel=0.1)
    assert len(candles["H1"]) == pytest.approx(10, rel=0.2)
    assert len(candles["H8"]) >= 1


def test_build_symbol_candles_resamples_identical_frames():
    frame = _m1_frame(800)
    identical = {tf: frame for tf in ("M1", "M5", "H1", "H4", "H8", "M15")}
    normalized = build_symbol_candles({"EURUSD": identical})
    assert len(normalized["EURUSD"]["M1"]) == 800
    assert len(normalized["EURUSD"]["M5"]) < len(normalized["EURUSD"]["M1"])
