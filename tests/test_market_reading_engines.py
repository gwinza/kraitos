"""Tests for advanced market reading engines."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from strategies.distribution_accumulation_engine import DistributionAccumulationEngine
from strategies.market_lifecycle_engine import MarketLifecycleEngine
from strategies.market_regime_engine import MarketRegimeEngine
from strategies.reversal_pressure_engine import ReversalPressureEngine
from strategies.retracement_vs_reversal_engine import RetracementVsReversalEngine
from strategies.trend_quality_engine import TrendQualityConfig, TrendQualityEngine


def _frame(closes: list[float], *, volume: float = 120.0) -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    prev = closes[0]
    for idx, close in enumerate(closes):
        open_ = prev
        high = max(open_, close) + 0.00012
        low = min(open_, close) - 0.00012
        rows.append(
            {
                "time": start + timedelta(hours=idx),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": volume + idx % 9,
                "spread": 1.0,
            }
        )
        prev = close
    return pd.DataFrame(rows)


def _trend_closes(steps: int = 80, delta: float = 0.00018) -> list[float]:
    return [1.1000 + i * delta for i in range(steps)]


def _range_closes(steps: int = 80) -> list[float]:
    return [1.1000 + (0.0010 if i % 18 < 9 else -0.0010) for i in range(steps)]


class TestTrendQualityMetrics:
    def test_metrics_populated(self) -> None:
        result = TrendQualityEngine(
            TrendQualityConfig(min_candles=30, lookback=70)
        ).analyze(_frame(_trend_closes()), symbol="EURUSD", timeframe="H1")
        assert result.trend_quality_score >= 0
        assert 0 <= result.metrics.hh_hl_quality <= 100
        assert 0 <= result.metrics.ll_lh_quality <= 100
        assert 0 <= result.metrics.trend_health <= 1.0
        assert 0 <= result.metrics.trend_participation <= 1.0


class TestReversalPressureEngine:
    def test_detects_pressure_on_exhaustion(self) -> None:
        closes = _trend_closes(60, 0.00012)
        for i in range(30):
            closes.append(closes[-1] + (0.00008 if i % 3 == 0 else -0.00004))
        result = ReversalPressureEngine().analyze(_frame(closes), symbol="EURUSD")
        assert 0 <= result.reversal_pressure_score <= 100
        assert result.trend_direction in {"bullish", "bearish", "neutral"}


class TestRetracementVsReversalEngine:
    def test_probabilities_sum_to_one(self) -> None:
        result = RetracementVsReversalEngine().analyze(
            _frame(_trend_closes()), symbol="EURUSD"
        )
        total = result.retracement_probability + result.reversal_probability
        assert abs(total - 1.0) < 0.02
        assert result.classification in {"retracement", "reversal", "unclear"}


class TestDistributionAccumulationEngine:
    def test_identifies_phase_with_opportunity(self) -> None:
        result = DistributionAccumulationEngine().analyze(
            _frame(_range_closes()), symbol="EURUSD"
        )
        assert result.phase in {
            "accumulation", "markup", "distribution", "markdown", "unclear"
        }
        assert result.trade_opportunity


class TestMarketLifecycleEngine:
    def test_classifies_lifecycle(self) -> None:
        result = MarketLifecycleEngine().analyze(
            _frame(_trend_closes()), symbol="EURUSD", timeframe="H1"
        )
        assert result.lifecycle_phase in {
            "accumulation", "expansion", "exhaustion", "reversal", "consolidation"
        }
        assert result.trade_opportunity
        assert result.trend_quality_score >= 0


class TestMarketRegimePrimary:
    def test_primary_regime_and_opportunity(self) -> None:
        result = MarketRegimeEngine().analyze(_frame(_trend_closes(120)), symbol="EURUSD")
        assert result.primary_regime in {
            "trending", "ranging", "breakout", "mean_reversion", "compression", "chaos"
        }
        assert result.trade_opportunity
        assert result.strategy_bias != "wait_for_clarity"

    def test_ranging_regime_has_range_opportunity(self) -> None:
        result = MarketRegimeEngine().analyze(_frame(_range_closes(120)), symbol="EURUSD")
        assert result.trade_opportunity
        assert "strategy:" in result.trade_opportunity
