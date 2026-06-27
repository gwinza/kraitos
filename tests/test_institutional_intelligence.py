"""Tests for institutional market structure intelligence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from strategies.dxy_context_engine import DxyContextEngine
from strategies.false_breakout_engine import FalseBreakoutEngine
from strategies.institutional_structure_engine import InstitutionalStructureEngine
from strategies.liquidity_sweep_engine import LiquiditySweepEngine
from strategies.news_context_engine import NewsContextEngine
from strategies.range_intelligence_engine import RangeIntelligenceEngine
from strategies.session_intelligence_engine import SessionIntelligenceEngine
from strategies.models import NewsEvent


def _frame(closes: list[float], *, volume: float = 120.0) -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    prev = closes[0]
    for idx, close in enumerate(closes):
        open_ = prev
        high = max(open_, close) + 0.00015
        low = min(open_, close) - 0.00015
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


class TestInstitutionalStructureEngine:
    def test_structure_scores(self) -> None:
        result = InstitutionalStructureEngine().analyze(
            _frame(_trend_closes()), symbol="EURUSD", timeframe="H1"
        )
        assert result.structure_bias in {"bullish", "bearish", "range"}
        assert 0 <= result.bullish_structure_score <= 100
        assert 0 <= result.bearish_structure_score <= 100
        assert result.trade_opportunity


class TestLiquiditySweepEngine:
    def test_sweep_probability(self) -> None:
        closes = _trend_closes(60)
        closes[-1] = closes[-2] + 0.002
        result = LiquiditySweepEngine().analyze(_frame(closes), symbol="EURUSD")
        assert 0 <= result.liquidity_sweep_probability <= 1.0
        assert result.sweep_type in {
            "stop_hunt", "buy_side_sweep", "sell_side_sweep", "sweep_failure", "none"
        }


class TestFalseBreakoutEngine:
    def test_breakout_quality_score(self) -> None:
        result = FalseBreakoutEngine().analyze(_frame(_range_closes()), symbol="EURUSD")
        assert 0 <= result.breakout_quality_score <= 100
        assert result.breakout_class in {"genuine", "failed", "developing", "none"}
        assert result.trade_opportunity


class TestRangeIntelligenceEnhanced:
    def test_mean_reversion_and_continuation(self) -> None:
        result = RangeIntelligenceEngine().analyze(_frame(_range_closes(100)), symbol="EURUSD")
        assert 0 <= result.mean_reversion_score <= 100
        assert 0 <= result.range_continuation_probability <= 1.0
        assert result.range_breakout_preparation_score >= 0
        assert result.trade_opportunity


class TestSessionIntelligenceEngine:
    def test_session_quality(self) -> None:
        london_open = datetime(2025, 6, 10, 9, 0, tzinfo=timezone.utc)
        result = SessionIntelligenceEngine().analyze(symbol="EURUSD", at_time=london_open)
        assert 0 <= result.session_quality <= 100
        assert result.active_session in {"london", "new_york", "overlap", "asia", "off_hours"}
        assert result.session_scores.london >= 50


class TestDxyContextEngine:
    def test_gold_dxy_context(self) -> None:
        dxy_closes = [104.0 - i * 0.02 for i in range(60)]
        gold_closes = [2300.0 + i * 2.0 for i in range(60)]
        result = DxyContextEngine().analyze(
            _frame(dxy_closes),
            symbol="XAUUSD",
            asset_candles=_frame(gold_closes),
        )
        assert result.dxy_direction in {"rising", "falling", "neutral"}
        assert result.gold_alignment in {"aligned", "divergent", "neutral"}
        assert result.trade_opportunity


class TestNewsContextEngine:
    def test_news_context_not_veto(self) -> None:
        moment = datetime(2025, 6, 6, 12, 30, tzinfo=timezone.utc)
        events = [
            NewsEvent(
                currency="USD",
                impact_level="high",
                news_time=moment + timedelta(minutes=15),
                title="US Non-Farm Payrolls",
            )
        ]
        result = NewsContextEngine().analyze(events, symbol="EURUSD", at_time=moment)
        assert result.active_category == "nfp"
        assert result.size_multiplier < 1.0
        assert result.size_multiplier > 0
        assert "veto" not in result.trade_opportunity.lower()
        assert result.trade_opportunity
