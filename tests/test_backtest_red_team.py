"""Tests for backtest red-team audit and conservative execution."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from backtesting.execution_model import (
    ExecutionCostConfig,
    resolve_exit_price,
    slice_closed_candles,
    slice_inclusive_candles,
)
from paper_trading.virtual_account import OpenVirtualPosition
from validation.backtest_red_team import (
    RedTeamComparison,
    assess_trustworthiness,
    audit_known_biases,
    compare_candle_slices,
    generate_red_team_report,
)
from backtesting.performance_report import PerformanceMetrics

pytestmark = pytest.mark.offline


def _sample_candles() -> dict[str, pd.DataFrame]:
    times = pd.date_range("2025-01-06 10:00", periods=12, freq="5min", tz="UTC")
    close = pd.Series([1.10 + index * 0.0001 for index in range(12)])
    m5 = pd.DataFrame(
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
    return {"M5": m5, "H1": m5.iloc[::2].copy()}


def test_slice_closed_excludes_incomplete_htf_bar():
    candles = _sample_candles()
    moment = datetime(2025, 1, 6, 10, 7, tzinfo=timezone.utc)
    inclusive = slice_inclusive_candles(candles, moment)
    closed = slice_closed_candles(candles, moment)
    assert len(inclusive["M5"]) >= len(closed["M5"])
    assert len(inclusive["H1"]) > len(closed["H1"])


def test_compare_candle_slices_reports_positive_htf_delta():
    candles = _sample_candles()
    moment = datetime(2025, 1, 6, 10, 7, tzinfo=timezone.utc)
    delta = compare_candle_slices(candles, moment)
    assert delta.get("H1", 0) >= 1


def test_resolve_exit_sl_first_on_ambiguous_bar():
    position = OpenVirtualPosition(
        trade_id="t1",
        symbol="EURUSD",
        timeframe="M5",
        direction="buy",
        entry=1.1000,
        stop_loss=1.0990,
        take_profit=1.1010,
        lot_size=0.01,
        confidence=0.8,
        mode="harvest",
        reason="test",
        risk_amount=1.0,
        entry_time=datetime(2025, 1, 6, 10, 0, tzinfo=timezone.utc),
    )
    price, reason = resolve_exit_price(position, high=1.1015, low=1.0985, sl_first=True)
    assert reason == "stop_loss"
    assert price == pytest.approx(1.0990)


def test_audit_lists_critical_lookahead_findings():
    findings = audit_known_biases()
    codes = {finding.code for finding in findings}
    assert "incomplete_bar_lookahead" in codes
    assert "htf_partial_period" in codes
    assert any(finding.severity == "critical" for finding in findings)


def test_assess_trustworthiness_flags_invalid_when_win_rate_collapses():
    findings = audit_known_biases()
    comparison = RedTeamComparison(
        optimistic=PerformanceMetrics(
            initial_balance=10_000,
            final_balance=15_000,
            equity=15_000,
            total_return_pct=50.0,
            max_drawdown_pct=1.0,
            daily_drawdown_pct=0.0,
            win_rate=0.96,
            profit_factor=5.0,
            average_r=0.2,
            total_trades=200,
            winning_trades=192,
            losing_trades=8,
            gross_profit=5000,
            gross_loss=500,
            daily_pnl={},
            trading_disabled=False,
            trading_halted_daily=False,
        ),
        conservative=PerformanceMetrics(
            initial_balance=10_000,
            final_balance=10_200,
            equity=10_200,
            total_return_pct=2.0,
            max_drawdown_pct=5.0,
            daily_drawdown_pct=0.0,
            win_rate=0.42,
            profit_factor=0.9,
            average_r=-0.1,
            total_trades=80,
            winning_trades=34,
            losing_trades=46,
            gross_profit=400,
            gross_loss=200,
            daily_pnl={},
            trading_disabled=False,
            trading_halted_daily=False,
        ),
        optimistic_trades=200,
        conservative_trades=80,
        test_bars_m1=12000,
        test_symbols=("EURUSD",),
    )
    verdict = assess_trustworthiness(findings, comparison, reported_win_rate=0.962)
    assert verdict.rating in {"QUESTIONABLE", "INVALID"}
    assert verdict.reasons


def test_generate_red_team_report_writes_file(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    config_dir.joinpath("config.yaml").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "logs").mkdir()

    verdict = generate_red_team_report(tmp_path, m1_bars=3000, run_comparison=True)
    report_path = tmp_path / "logs" / "backtest_red_team_report.md"
    assert report_path.exists()
    text = report_path.read_text(encoding="utf-8")
    assert verdict.rating in {"TRUSTWORTHY", "QUESTIONABLE", "INVALID"}
    assert "Trust rating" in text
    assert "Optimistic vs conservative" in text
