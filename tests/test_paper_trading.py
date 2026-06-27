"""Tests for the paper trading validation layer."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from backtesting.performance_report import PerformanceReport
from core.signal_router import TradeSignal
from paper_trading.paper_executor import PaperExecutor
from paper_trading.virtual_account import (
    OpenVirtualPosition,
    SafetyLimits,
    ValidationConfig,
    VirtualAccount,
)

pytestmark = pytest.mark.offline


def _journal_path(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "trade_journal.csv"


def test_virtual_account_starts_at_100(tmp_path: Path):
    account = VirtualAccount(
        ValidationConfig(initial_balance=100.0, risk_per_trade_pct=1.0),
        journal_path=_journal_path(tmp_path),
    )
    assert account.balance == pytest.approx(100.0)
    assert account.equity == pytest.approx(100.0)


def test_virtual_account_records_closed_trade(tmp_path: Path):
    account = VirtualAccount(
        ValidationConfig(initial_balance=100.0),
        journal_path=_journal_path(tmp_path),
    )
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    position = OpenVirtualPosition(
        trade_id="t1",
        symbol="EURUSD",
        timeframe="H1",
        direction="buy",
        entry=1.1000,
        stop_loss=1.0980,
        take_profit=1.1040,
        lot_size=0.01,
        confidence=0.8,
        mode="harvest",
        reason="test entry",
        risk_amount=1.0,
        entry_time=now,
    )
    account.open_position(position)
    entry = account.close_position(
        "t1",
        exit_price=1.1040,
        exit_time=now,
        reason="take_profit",
    )

    assert entry.result == "win"
    assert entry.profit_loss > 0
    assert account.balance > 100.0
    assert _journal_path(tmp_path).exists()
    content = _journal_path(tmp_path).read_text(encoding="utf-8")
    assert "EURUSD" in content
    assert "take_profit" in content


def test_virtual_account_journals_macro_theme(tmp_path: Path):
    account = VirtualAccount(
        ValidationConfig(initial_balance=100.0),
        journal_path=_journal_path(tmp_path),
    )
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    account.open_position(
        OpenVirtualPosition(
            trade_id="theme1",
            symbol="GBPJPY",
            timeframe="H1",
            direction="sell",
            entry=190.0,
            stop_loss=191.0,
            take_profit=188.0,
            lot_size=0.01,
            confidence=0.8,
            mode="harvest",
            reason="JPY dominance",
            risk_amount=1.0,
            entry_time=now,
            trade_theme="JPY risk-off",
            theme_confidence=0.82,
        )
    )

    frame = pd.read_csv(_journal_path(tmp_path))
    assert frame.loc[0, "trade_theme"] == "JPY risk-off"
    assert frame.loc[0, "theme_confidence"] == pytest.approx(0.82)


def test_daily_drawdown_halts_trading(tmp_path: Path):
    account = VirtualAccount(
        ValidationConfig(
            initial_balance=100.0,
            safety=SafetyLimits(max_daily_drawdown_pct=5.0, max_total_drawdown_pct=50.0),
        ),
        journal_path=_journal_path(tmp_path),
    )
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    position = OpenVirtualPosition(
        trade_id="loss1",
        symbol="EURUSD",
        timeframe="H1",
        direction="buy",
        entry=1.1000,
        stop_loss=1.0980,
        take_profit=1.1100,
        lot_size=0.01,
        confidence=0.5,
        mode="normal",
        reason="test",
        risk_amount=10.0,
        entry_time=now,
    )
    account.open_position(position)
    account.close_position(
        "loss1",
        exit_price=1.0940,
        exit_time=now,
        reason="stop_loss",
    )

    assert account.balance == pytest.approx(94.0, abs=1.0)
    allowed, _ = account.can_trade(now)
    assert allowed is True


def test_catastrophic_drawdown_blocks_trading(tmp_path: Path):
    account = VirtualAccount(
        ValidationConfig(
            initial_balance=100.0,
            safety=SafetyLimits(catastrophic_drawdown_pct=50.0),
        ),
        journal_path=_journal_path(tmp_path),
    )
    now = datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc)
    account.balance = 49.0
    account.peak_balance = 100.0

    allowed, reason = account.can_trade(now)
    assert allowed is False
    assert account.trading_disabled is True
    assert "50%" in reason

    account.reset_trading()
    allowed, _ = account.can_trade(now)
    assert allowed is True


def test_paper_executor_opens_and_monitors_trade(tmp_path: Path):
    account = VirtualAccount(
        ValidationConfig(initial_balance=100.0, spread_pips=0.0),
        journal_path=_journal_path(tmp_path),
    )
    executor = PaperExecutor(account)

    signal = TradeSignal(
        symbol="EURUSD",
        decision="TRADE",
        direction="buy",
        confidence=0.75,
        entry=1.1000,
        stop_loss=1.0980,
        take_profit=1.1020,
        risk_pct=1.0,
        lot_size=0.01,
        reason="test trade",
        mode="harvest",
        trace_id="trace-1",
    )
    candles = {
        "H1": pd.DataFrame(
            [
                {
                    "time": datetime(2025, 1, 1, tzinfo=timezone.utc),
                    "open": 1.099,
                    "high": 1.101,
                    "low": 1.098,
                    "close": 1.100,
                    "tick_volume": 100,
                    "spread": 1.0,
                }
            ]
        )
    }

    position = executor.try_open(
        signal,
        candles=candles,
        moment=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert position is not None
    assert len(account.open_positions) == 1

    exit_bar = pd.Series(
        {
            "time": datetime(2025, 1, 1, 1, tzinfo=timezone.utc),
            "high": 1.103,
            "low": 1.099,
            "close": 1.102,
        }
    )
    closed = executor.monitor_symbol("EURUSD", exit_bar)
    assert len(closed) == 1
    assert len(account.closed_entries) == 1


def test_performance_report_summary(tmp_path: Path):
    account = VirtualAccount(
        ValidationConfig(initial_balance=100.0),
        journal_path=_journal_path(tmp_path),
    )
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    position = OpenVirtualPosition(
        trade_id="win1",
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
    account.open_position(position)
    account.close_position("win1", exit_price=1.1040, exit_time=now, reason="take_profit")

    summary = PerformanceReport(account).render()
    assert "Kraitos Validation Performance" in summary
    assert "Win rate" in summary
    assert "Average R" in summary
