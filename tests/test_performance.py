"""Tests for performance analytics."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from analytics import PerformanceAnalyzer, PerformanceError
from analytics.models import ClosedTradeRecord


def _paper_log(path: Path, rows: list[dict[str, str]]) -> None:
    columns = [
        "trade_id",
        "event_time",
        "event_type",
        "symbol",
        "side",
        "status",
        "entry_price",
        "exit_price",
        "lot_size",
        "stop_loss",
        "take_profit",
        "floating_pl",
        "closed_pl",
        "balance",
        "reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_analyze_metrics_from_closed_trades():
    trades = [
        ClosedTradeRecord(
            trade_id="t1",
            symbol="EURUSD",
            side="buy",
            exit_time=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            pnl=20.0,
            balance=10_020.0,
            session="london",
        ),
        ClosedTradeRecord(
            trade_id="t2",
            symbol="EURUSD",
            side="buy",
            exit_time=datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
            pnl=-10.0,
            balance=10_010.0,
            session="new_york",
        ),
        ClosedTradeRecord(
            trade_id="t3",
            symbol="GBPUSD",
            side="sell",
            exit_time=datetime(2025, 1, 2, 9, 0, tzinfo=timezone.utc),
            pnl=30.0,
            balance=10_040.0,
            session="london",
        ),
    ]

    metrics = PerformanceAnalyzer().analyze(trades, initial_balance=10_000.0)

    assert metrics.total_trades == 3
    assert metrics.win_rate == pytest.approx(2 / 3, rel=1e-3)
    assert metrics.loss_rate == pytest.approx(1 / 3, rel=1e-3)
    assert metrics.average_win == pytest.approx(25.0)
    assert metrics.average_loss == pytest.approx(10.0)
    assert metrics.profit_factor == pytest.approx(5.0)
    assert metrics.net_profit == pytest.approx(40.0)
    assert metrics.best_symbol == "GBPUSD"
    assert metrics.worst_symbol == "EURUSD"
    assert metrics.best_session == "london"
    assert metrics.max_drawdown >= 0


def test_load_paper_trades_csv(tmp_path: Path):
    log_path = tmp_path / "paper_trades.csv"
    _paper_log(
        log_path,
        [
            {
                "trade_id": "abc",
                "event_time": "2025-01-01T10:00:00+00:00",
                "event_type": "open",
                "symbol": "EURUSD",
                "side": "buy",
                "status": "open",
                "entry_price": "1.10000",
                "exit_price": "",
                "lot_size": "0.10",
                "stop_loss": "1.09800",
                "take_profit": "1.10300",
                "floating_pl": "0.00",
                "closed_pl": "0.00",
                "balance": "10000.00",
                "reason": "entry",
            },
            {
                "trade_id": "abc",
                "event_time": "2025-01-01T14:00:00+00:00",
                "event_type": "close",
                "symbol": "EURUSD",
                "side": "buy",
                "status": "closed",
                "entry_price": "1.10000",
                "exit_price": "1.10200",
                "lot_size": "0.10",
                "stop_loss": "1.09800",
                "take_profit": "1.10300",
                "floating_pl": "0.00",
                "closed_pl": "20.00",
                "balance": "10020.00",
                "reason": "take profit",
            },
        ],
    )

    metrics = PerformanceAnalyzer().from_log_paths(log_path)

    assert metrics.total_trades == 1
    assert metrics.net_profit == pytest.approx(20.0)


def test_load_executed_trades_jsonl(tmp_path: Path):
    jsonl_path = tmp_path / "executed_trades.jsonl"
    payload = {
        "event_id": "e1",
        "trace_id": "trace1",
        "timestamp": "2025-01-01T15:00:00+00:00",
        "category": "executed_trades",
        "event_type": "close",
        "symbol": "USDJPY",
        "message": "closed",
        "data": {
            "trade_id": "t10",
            "side": "sell",
            "closed_pl": 15.0,
            "balance": 10015.0,
        },
    }
    jsonl_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    metrics = PerformanceAnalyzer().from_log_paths(jsonl_path)

    assert metrics.total_trades == 1
    assert metrics.net_profit == pytest.approx(15.0)


def test_empty_trades_returns_zero_metrics():
    metrics = PerformanceAnalyzer().analyze([])

    assert metrics.total_trades == 0
    assert metrics.win_rate == 0.0
    assert metrics.best_symbol is None


def test_raises_when_log_missing(tmp_path: Path):
    with pytest.raises(PerformanceError, match="not found"):
        PerformanceAnalyzer().load_trades(tmp_path / "missing.csv")
