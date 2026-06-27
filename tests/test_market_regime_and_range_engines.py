from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from strategies.market_regime_engine import MarketRegimeEngine
from strategies.range_intelligence_engine import RangeIntelligenceEngine


def _frame(closes: list[float], *, volume: float = 120.0, spread: float = 1.0) -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    prev = closes[0]
    for idx, close in enumerate(closes):
        open_ = prev
        high = max(open_, close) + 0.00012
        low = min(open_, close) - 0.00012
        rows.append(
            {
                "time": start + timedelta(minutes=idx),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": volume + idx % 9,
                "spread": spread,
            }
        )
        prev = close
    return pd.DataFrame(rows)


def test_market_regime_detects_trend_environment() -> None:
    closes = [1.1000 + i * 0.00018 for i in range(120)]
    result = MarketRegimeEngine().analyze(_frame(closes), symbol="EURUSD")

    assert result.market_regime in {"strong_uptrend", "healthy_uptrend", "mature_uptrend"}
    assert result.trend_strength_score >= 50
    assert result.strategy_bias in {"trend_continuation", "pullback", "reduced_risk_trend"}
    assert result.evidence


def test_range_intelligence_identifies_horizontal_range() -> None:
    closes = [1.1000 + (0.0010 if i % 18 < 9 else -0.0010) for i in range(100)]
    result = RangeIntelligenceEngine().analyze(_frame(closes), symbol="EURUSD")

    assert result.range_status in {"horizontal_range", "triangular_range", "diagonal_range"}
    assert result.support_level < result.resistance_level
    assert result.range_quality_score >= 45
    assert result.equilibrium_zone > result.support_level
    assert result.equilibrium_zone < result.resistance_level


def test_market_regime_detects_breakout_preparation_from_compressed_range() -> None:
    closes: list[float] = []
    for i in range(120):
        width = max(0.00015, 0.0012 - i * 0.000008)
        closes.append(1.1000 + (width if i % 2 == 0 else -width))
    result = MarketRegimeEngine().analyze(_frame(closes), symbol="EURUSD")

    assert result.compression_probability >= 0.20
    assert result.breakout_preparation_score >= 35
    assert result.likely_next_regime in {"breakout", "breakout_up", "breakout_down", "continuation", "breakout_preparation"}
