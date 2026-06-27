"""Tests for self-improvement analytics."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.offline

from analytics.conviction_report import ConvictionReporter
from analytics.opportunity_cost_report import OpportunityCostReporter
from analytics.regime_performance_report import RegimePerformanceReporter
from analytics.thesis_accuracy_report import ThesisAccuracyReporter
from analytics.trade_intelligence import TradeIntelligenceEngine
from analytics.trade_records import EnrichedTradeRecord, RejectedOpportunityRecord, SkippedPeriodMetrics


def _trade(
    *,
    r: float,
    won: bool | None = None,
    conviction: float = 70.0,
    mode: str = "normal",
    regime: str = "trend",
    thesis_correct: bool | None = True,
    trade_id: str = "t1",
) -> EnrichedTradeRecord:
    won = won if won is not None else r > 0
    return EnrichedTradeRecord(
        trade_id=trade_id,
        symbol="EURUSD",
        side="buy",
        exit_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
        pnl=r * 100,
        r_multiple=r,
        outcome="win" if won else "loss",
        conviction_score=conviction,
        participation_mode=mode,
        thesis_correct=thesis_correct,
        primary_regime=regime,  # type: ignore[arg-type]
        exit_quality=0.7 if won else 0.4,
        invalidation_quality=0.6,
    )


class TestTradeIntelligence:
    def test_core_metrics(self) -> None:
        trades = [_trade(r=1.2), _trade(r=0.8), _trade(r=-1.0, thesis_correct=False)]
        report = TradeIntelligenceEngine().build_report(trades)
        assert report.core.total_trades == 3
        assert report.core.win_rate == pytest.approx(2 / 3, abs=0.01)
        assert report.core.profit_factor > 1.0
        assert report.core.expectancy > 0
        assert report.risk_adjusted_score > 0

    def test_overcaution_warning(self) -> None:
        trades = [_trade(r=-0.5, thesis_correct=False, trade_id="a")]
        rejected = [
            RejectedOpportunityRecord(
                symbol="EURUSD",
                side="buy",
                decision_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                reason="low conviction",
                missed_r=2.0,
                would_have_won=True,
            )
            for _ in range(5)
        ]
        periods = [
            SkippedPeriodMetrics("week1", 20, 5, 2),
            SkippedPeriodMetrics("week2", 8, 12, 6),
        ]
        report = TradeIntelligenceEngine().build_report(
            trades, rejected=rejected, period_metrics=periods
        )
        assert report.overcaution.triggered or report.overcaution.level in {"watch", "warning", "critical"}


class TestOpportunityCostReport:
    def test_over_cautious_verdict(self) -> None:
        report = OpportunityCostReporter().build(
            accepted_trades=[_trade(r=-0.5, thesis_correct=False)],
            rejected=[
                RejectedOpportunityRecord(
                    symbol="EURUSD",
                    side="buy",
                    decision_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                    reason="pass",
                    missed_r=3.0,
                    would_have_won=True,
                )
            ],
        )
        assert report.missed_r == 3.0
        assert report.verdict in {"over_cautious", "balanced", "under_disciplined"}


class TestRegimePerformanceReport:
    def test_regime_slices(self) -> None:
        trades = [
            _trade(r=1.0, regime="trend", trade_id="1"),
            _trade(r=0.5, regime="range", trade_id="2"),
            _trade(r=-0.5, regime="chaos", trade_id="3", thesis_correct=False),
        ]
        report = RegimePerformanceReporter().build(trades)
        active = [s for s in report.slices if s.trade_count > 0]
        assert len(active) >= 3
        assert report.best_regime in {"trend", "range", "breakout", "reversal", "chaos", "unknown"}


class TestConvictionReport:
    def test_conviction_vs_outcome(self) -> None:
        trades = [
            _trade(r=1.0, conviction=85, mode="aggressive", trade_id="1"),
            _trade(r=0.5, conviction=72, mode="normal", trade_id="2"),
            _trade(r=0.3, conviction=52, mode="probe", trade_id="3"),
            _trade(r=-0.8, conviction=78, mode="normal", trade_id="4", thesis_correct=False),
        ]
        report = ConvictionReporter().build(trades)
        assert 0 <= report.overall_conviction_accuracy <= 1.0
        assert len(report.buckets) == 6


class TestThesisAccuracyReport:
    def test_thesis_exit_quality(self) -> None:
        trades = [
            _trade(r=1.5, thesis_correct=True, trade_id="1"),
            _trade(r=-0.9, thesis_correct=False, trade_id="2"),
            _trade(r=0.4, thesis_correct=True, trade_id="3"),
        ]
        report = ThesisAccuracyReporter().build(trades)
        assert report.thesis_quality.sample_size >= 3
        assert report.market_reading_score >= 0
        assert report.summary
