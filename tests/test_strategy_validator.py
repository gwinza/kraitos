"""Tests for the strategy validation gate and live readiness report."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backtesting.performance_report import PerformanceMetrics
from paper_trading.virtual_account import (
    OpenVirtualPosition,
    SafetyLimits,
    ValidationConfig,
    VirtualAccount,
)
from validation import (
    ForwardTestTracker,
    LiveReadinessReport,
    StrategyValidationInput,
    StrategyValidator,
    ValidationThresholds,
)

pytestmark = pytest.mark.offline


def _metrics(
    *,
    total_trades: int = 100,
    win_rate: float = 0.55,
    profit_factor: float = 1.5,
    max_drawdown_pct: float = 10.0,
    average_r: float = 0.4,
    trading_halted_daily: bool = False,
    trading_disabled: bool = False,
    initial_balance: float = 100.0,
    final_balance: float = 110.0,
) -> PerformanceMetrics:
    winners = int(total_trades * win_rate)
    losers = total_trades - winners
    gross_profit = profit_factor * 10.0 if losers else 15.0
    gross_loss = 10.0 if losers else 0.0
    return PerformanceMetrics(
        initial_balance=initial_balance,
        final_balance=final_balance,
        equity=final_balance,
        total_return_pct=((final_balance - initial_balance) / initial_balance * 100.0)
        if initial_balance
        else 0.0,
        max_drawdown_pct=max_drawdown_pct,
        daily_drawdown_pct=0.0,
        win_rate=win_rate,
        profit_factor=profit_factor,
        average_r=average_r,
        total_trades=total_trades,
        winning_trades=winners,
        losing_trades=losers,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        daily_pnl={},
        trading_disabled=trading_disabled,
        trading_halted_daily=trading_halted_daily,
    )


def _passing_backtest(**overrides) -> PerformanceMetrics:
    return _metrics(total_trades=500, **overrides)


def _passing_paper(**overrides) -> PerformanceMetrics:
    return _metrics(total_trades=30, **overrides)


def test_needs_more_data_when_backtest_trades_insufficient():
    validator = StrategyValidator()
    result = validator.validate(
        StrategyValidationInput(
            backtest=_metrics(total_trades=50),
            paper=_passing_paper(),
        )
    )
    assert result.status == "NEEDS_MORE_DATA"
    assert any("backtest_trade_count" in reason for reason in result.summary_reasons) or any(
        criterion.name == "backtest_trade_count" and not criterion.passed
        for criterion in result.criteria
    )


def test_approved_for_paper_only_when_backtest_passes_but_paper_insufficient():
    validator = StrategyValidator()
    result = validator.validate(
        StrategyValidationInput(
            backtest=_passing_backtest(),
            paper=_metrics(total_trades=10),
            trust_verdict="TRUSTWORTHY",
        )
    )
    assert result.status == "APPROVED_FOR_PAPER_ONLY"
    assert result.backtest_trades == 500
    assert result.paper_trades == 10


def test_failed_validation_when_metrics_below_threshold():
    validator = StrategyValidator()
    result = validator.validate(
        StrategyValidationInput(
            backtest=_passing_backtest(win_rate=0.40),
            paper=_passing_paper(),
        )
    )
    assert result.status == "FAILED_VALIDATION"
    failed = [c for c in result.criteria if c.phase == "backtest" and c.name == "win_rate"]
    assert failed and not failed[0].passed


def test_failed_validation_on_daily_drawdown_breach():
    validator = StrategyValidator()
    result = validator.validate(
        StrategyValidationInput(
            backtest=_passing_backtest(),
            paper=_passing_paper(trading_halted_daily=True),
        )
    )
    assert result.status == "FAILED_VALIDATION"


def test_questionable_trust_verdict_blocks_live_ready():
    validator = StrategyValidator()
    result = validator.validate(
        StrategyValidationInput(
            backtest=_passing_backtest(),
            paper=_passing_paper(),
            trust_verdict="QUESTIONABLE",
        )
    )
    assert result.status == "FAILED_VALIDATION"
    assert result.status != "LIVE_READY"


def test_failed_validation_on_critical_system_errors():
    validator = StrategyValidator()
    result = validator.validate(
        StrategyValidationInput(
            backtest=_passing_backtest(),
            paper=_passing_paper(),
            critical_errors=("MT5 connection lost",),
        )
    )
    assert result.status == "FAILED_VALIDATION"
    assert "MT5 connection lost" in result.critical_errors


def test_live_ready_when_all_criteria_pass():
    validator = StrategyValidator()
    result = validator.validate(
        StrategyValidationInput(
            strategy_name="eurusd_harvest",
            backtest=_passing_backtest(),
            paper=_passing_paper(),
            live_trading_enabled=False,
            trust_verdict="TRUSTWORTHY",
        )
    )
    assert result.status == "LIVE_READY"
    assert result.live_ready is True
    assert any("DISABLED" in reason for reason in result.summary_reasons)


def test_live_ready_still_reports_live_trading_disabled():
    validator = StrategyValidator()
    result = validator.validate(
        StrategyValidationInput(
            backtest=_passing_backtest(),
            paper=_passing_paper(),
            live_trading_enabled=False,
            trust_verdict="TRUSTWORTHY",
        )
    )
    assert result.status == "LIVE_READY"
    assert result.live_trading_enabled is False


def test_profit_factor_infinity_passes_threshold():
    validator = StrategyValidator()
    result = validator.validate(
        StrategyValidationInput(
            backtest=_passing_backtest(profit_factor=float("inf")),
            paper=_passing_paper(profit_factor=float("inf")),
            trust_verdict="TRUSTWORTHY",
        )
    )
    assert result.status == "LIVE_READY"


def test_forward_test_tracker_reads_virtual_account(tmp_path: Path):
    account = VirtualAccount(
        ValidationConfig(initial_balance=100.0),
        journal_path=tmp_path / "trade_journal.csv",
    )
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    for index in range(3):
        trade_id = f"t{index}"
        account.open_position(
            OpenVirtualPosition(
                trade_id=trade_id,
                symbol="EURUSD",
                timeframe="H1",
                direction="buy",
                entry=1.1000,
                stop_loss=1.0980,
                take_profit=1.1040,
                lot_size=0.01,
                confidence=0.8,
                mode="harvest",
                reason="test",
                risk_amount=1.0,
                entry_time=now,
            )
        )
        account.close_position(
            trade_id,
            exit_price=1.1040,
            exit_time=now,
            reason="take_profit",
        )

    tracker = ForwardTestTracker(strategy_name="test_strategy")
    tracker.set_paper_account(account)
    snapshot = tracker.snapshot()

    assert snapshot.paper_trades == 3
    assert snapshot.paper.total_trades == 3


def test_forward_test_tracker_records_critical_errors():
    tracker = ForwardTestTracker()
    tracker.record_critical_error("pipeline crash")
    tracker.record_critical_error("pipeline crash")
    assert tracker.critical_errors == ("pipeline crash",)


def test_live_readiness_report_explains_not_ready():
    tracker = ForwardTestTracker(strategy_name="demo")
    tracker.set_backtest_metrics(_metrics(total_trades=20))
    tracker.set_paper_metrics(_metrics(total_trades=5))

    report = LiveReadinessReport()
    result, text = report.generate(tracker, live_trading_enabled=False)

    assert result.status == "NEEDS_MORE_DATA"
    assert "KRAITOS LIVE READINESS REPORT" in text
    assert "NEEDS_MORE_DATA" in text
    assert "DISABLED" in text
    assert "backtest_trade_count" in text


def test_live_readiness_report_live_ready_with_disabled_trading():
    tracker = ForwardTestTracker(strategy_name="validated")
    tracker.set_backtest_metrics(_passing_backtest())
    tracker.set_paper_metrics(_passing_paper())
    tracker.set_trust_verdict("TRUSTWORTHY")

    report = LiveReadinessReport()
    result, text = report.generate(tracker, live_trading_enabled=False)

    assert result.status == "LIVE_READY"
    assert "LIVE_READY" in text
    assert "DISABLED" in text
    assert "No real orders will be placed" in text


def test_live_readiness_report_failed_validation_lists_failures():
    tracker = ForwardTestTracker(strategy_name="weak")
    tracker.set_backtest_metrics(_passing_backtest(profit_factor=1.0))
    tracker.set_paper_metrics(_passing_paper())

    report = LiveReadinessReport()
    result, text = report.generate(tracker)

    assert result.status == "FAILED_VALIDATION"
    assert "FAIL" in text
    assert "profit_factor" in text


def test_custom_thresholds_enforced():
    validator = StrategyValidator(
        ValidationThresholds(min_backtest_trades=50, min_paper_trades=15)
    )
    result = validator.validate(
        StrategyValidationInput(
            backtest=_metrics(total_trades=50, win_rate=0.55, profit_factor=1.4),
            paper=_metrics(total_trades=15, win_rate=0.55, profit_factor=1.4),
            trust_verdict="TRUSTWORTHY",
        )
    )
    assert result.status == "LIVE_READY"


def test_average_r_must_be_strictly_positive():
    validator = StrategyValidator()
    result = validator.validate(
        StrategyValidationInput(
            backtest=_passing_backtest(average_r=0.0),
            paper=_passing_paper(),
        )
    )
    assert result.status == "FAILED_VALIDATION"


def test_live_readiness_report_approved_for_paper_only():
    tracker = ForwardTestTracker(strategy_name="paper_phase")
    tracker.set_backtest_metrics(_passing_backtest())
    tracker.set_paper_metrics(_metrics(total_trades=12))
    tracker.set_trust_verdict("TRUSTWORTHY")

    report = LiveReadinessReport()
    result, text = report.generate(tracker)

    assert result.status == "APPROVED_FOR_PAPER_ONLY"
    assert "APPROVED_FOR_PAPER_ONLY" in text
    assert "NEXT STEPS" in text
    assert "paper" in text.lower()


def test_live_ready_with_live_trading_enabled_shows_broker_guard_message():
    tracker = ForwardTestTracker(strategy_name="validated")
    tracker.set_backtest_metrics(_passing_backtest())
    tracker.set_paper_metrics(_passing_paper())
    tracker.set_trust_verdict("TRUSTWORTHY")

    report = LiveReadinessReport()
    result, text = report.generate(tracker, live_trading_enabled=True)

    assert result.status == "LIVE_READY"
    assert "broker confirmation guards" in text
    assert "not fully validated" not in text


def test_live_readiness_report_with_broker_settings_from_config():
    from config import load_config
    from config.broker_settings import BrokerSettings

    config = load_config()
    broker_settings = BrokerSettings.from_env(config_raw=config.raw)

    tracker = ForwardTestTracker(strategy_name="config_smoke")
    tracker.set_backtest_metrics(_passing_backtest())
    tracker.set_paper_metrics(_passing_paper())
    tracker.set_trust_verdict("TRUSTWORTHY")

    report = LiveReadinessReport()
    result, text = report.generate(tracker, broker_settings=broker_settings)

    assert result.status == "LIVE_READY"
    assert broker_settings.live_trading is False
    assert result.live_trading_enabled is False
    assert "DISABLED" in text


@pytest.mark.parametrize(
    "backtest_trades,paper_trades,expected_status",
    [
        (20, 5, "NEEDS_MORE_DATA"),
        (500, 10, "APPROVED_FOR_PAPER_ONLY"),
        (500, 30, "LIVE_READY"),
    ],
)
def test_readiness_report_status_matrix(backtest_trades, paper_trades, expected_status):
    tracker = ForwardTestTracker(strategy_name="matrix")
    tracker.set_backtest_metrics(_metrics(total_trades=backtest_trades))
    tracker.set_paper_metrics(_metrics(total_trades=paper_trades))
    if expected_status in {"LIVE_READY", "APPROVED_FOR_PAPER_ONLY"}:
        tracker.set_trust_verdict("TRUSTWORTHY")

    report = LiveReadinessReport()
    result, text = report.generate(tracker)

    assert result.status == expected_status
    assert expected_status in text
    assert "CRITERIA" in text
    assert "SUMMARY" in text
