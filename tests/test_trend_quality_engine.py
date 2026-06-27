"""Tests for trend quality and reversal supervision."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from strategies.trend_quality_engine import TrendQualityConfig, TrendQualityEngine

pytestmark = pytest.mark.offline


def _frame_from_closes(
    closes: list[float],
    *,
    volume_start: int = 1000,
    volume_step: int = 0,
) -> pd.DataFrame:
    start = datetime(2025, 3, 1, tzinfo=timezone.utc)
    rows = []
    for index, close in enumerate(closes):
        prev = closes[index - 1] if index else close
        body = abs(close - prev)
        wick = max(0.00025, body * 0.35)
        rows.append(
            {
                "time": start + timedelta(hours=index),
                "open": prev,
                "high": max(close, prev) + wick,
                "low": min(close, prev) - wick,
                "close": close,
                "tick_volume": max(volume_start + index * volume_step, 100),
                "spread": 1.0,
            }
        )
    return pd.DataFrame(rows)


def _engine() -> TrendQualityEngine:
    return TrendQualityEngine(TrendQualityConfig(min_candles=30, lookback=90))


def _healthy_bullish() -> list[float]:
    closes: list[float] = []
    price = 1.2000
    for cycle in range(10):
        impulse = 0.0020 + cycle * 0.00018
        pullback = 0.00055
        closes.extend([price, price + impulse * 0.5, price + impulse, price + impulse - pullback])
        price = price + impulse - pullback
    return closes


def _bullish_exhaustion() -> list[float]:
    closes: list[float] = []
    price = 1.2000
    for cycle in range(10):
        impulse = max(0.0025 - cycle * 0.00018, 0.00065)
        pullback = min(0.00045 + cycle * 0.00011, impulse * 0.82)
        closes.extend([price, price + impulse, price + impulse - pullback * 0.4, price + impulse - pullback])
        price = price + impulse - pullback
    return closes


def _distribution() -> list[float]:
    closes = _healthy_bullish()[:24]
    top = closes[-1] + 0.001
    for index in range(36):
        # Overlapping failed pushes around the same high.
        closes.append(top + (0.00035 if index % 4 == 0 else -0.00025) - (index % 3) * 0.00008)
    return closes


def _confirmed_bearish_reversal() -> list[float]:
    closes = _healthy_bullish()[:28]
    top = closes[-1]
    closes.extend(
        [
            top - 0.0012,
            top - 0.0024,
            top - 0.0014,
            top - 0.0032,
            top - 0.0022,
            top - 0.0045,
            top - 0.0030,
            top - 0.0060,
            top - 0.0040,
            top - 0.0075,
            top - 0.0055,
            top - 0.0090,
        ]
    )
    return closes


def test_bullish_healthy_trend_has_high_continuation_probability() -> None:
    result = _engine().analyze(
        _frame_from_closes(_healthy_bullish(), volume_step=5),
        symbol="GBPUSD",
        timeframe="H1",
    )

    assert result.trend_direction == "bullish"
    assert result.trend_phase in {"expansion", "healthy_pullback"}
    assert result.trend_quality_score >= 65
    assert result.continuation_probability > result.reversal_probability


def test_bullish_exhaustion_raises_reversal_probability() -> None:
    result = _engine().analyze(
        _frame_from_closes(_bullish_exhaustion(), volume_step=-5),
        symbol="GBPUSD",
        timeframe="H1",
    )

    assert result.trend_direction in {"bullish", "neutral"}
    assert result.trend_phase in {"exhaustion", "distribution", "reversal_warning"}
    assert result.reversal_probability >= 0.35


def test_distribution_blocks_aggressive_buys() -> None:
    result = _engine().analyze(
        _frame_from_closes(_distribution(), volume_step=-3),
        symbol="GBPUSD",
        timeframe="H1",
    )

    assert result.trend_phase in {"distribution", "exhaustion", "reversal_warning"}
    assert result.trade_story.action in {"reduce_size", "pause"}


def test_confirmed_bearish_reversal_allows_new_sell_bias() -> None:
    result = _engine().analyze(
        _frame_from_closes(_confirmed_bearish_reversal(), volume_step=4),
        symbol="GBPUSD",
        timeframe="H1",
    )

    assert result.trend_direction == "bearish"
    assert result.trend_phase in {"confirmed_reversal", "reversal_warning"}
    assert result.reversal_probability >= result.continuation_probability
    assert result.trade_story.action in {"reverse_bias", "pause"}


def test_gbpusd_march_april_style_deterioration_sequence() -> None:
    early = _engine().analyze(
        _frame_from_closes(_healthy_bullish(), volume_step=5),
        symbol="GBPUSD",
        timeframe="H1",
    )
    late_march = _engine().analyze(
        _frame_from_closes(_distribution(), volume_step=-3),
        symbol="GBPUSD",
        timeframe="H1",
        previous_thesis=early.trade_story.current_thesis,
    )
    early_april = _engine().analyze(
        _frame_from_closes(_confirmed_bearish_reversal(), volume_step=4),
        symbol="GBPUSD",
        timeframe="H1",
        previous_thesis=late_march.trade_story.current_thesis,
    )

    assert early.continuation_probability > early.reversal_probability
    assert late_march.trade_story.action in {"reduce_size", "pause"}
    assert early_april.trend_direction == "bearish"
    assert early_april.trade_story.action in {"reverse_bias", "pause"}
