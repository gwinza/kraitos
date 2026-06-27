"""Tests for dashboard data service."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from dashboard.data_service import DashboardDataService


def _write_paper_log(path: Path) -> None:
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
    rows = [
        {
            "trade_id": "t1",
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
            "floating_pl": "5.00",
            "closed_pl": "0.00",
            "balance": "10000.00",
            "reason": "entry",
        },
        {
            "trade_id": "t2",
            "event_time": "2025-01-01T11:00:00+00:00",
            "event_type": "close",
            "symbol": "GBPUSD",
            "side": "sell",
            "status": "closed",
            "entry_price": "1.30000",
            "exit_price": "1.29800",
            "lot_size": "0.10",
            "stop_loss": "1.30200",
            "take_profit": "1.29500",
            "floating_pl": "0.00",
            "closed_pl": "20.00",
            "balance": "10020.00",
            "reason": "take profit",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_load_snapshot_from_logs(tmp_path: Path):
    logs = tmp_path / "logs"
    csv_dir = logs / "csv"
    csv_dir.mkdir(parents=True)

    _write_paper_log(logs / "paper_trades.csv")

    with (logs / "dashboard_state.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "regime": "ranging",
                "regime_confidence": 0.65,
                "regime_reason": "Compressed volatility",
            },
            handle,
        )

    with (csv_dir / "trade_decisions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "event_type", "symbol", "message", "trace_id"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "timestamp": "2025-01-01T12:00:00+00:00",
                "event_type": "wait",
                "symbol": "EURUSD",
                "message": "Entry waiting: pending momentum",
                "trace_id": "abc123",
            }
        )

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        """
account:
  balance: 10000.0
risk:
  per_trade_pct: 1.0
  max_daily_drawdown_pct: 3.0
  max_open_trades: 5
trading:
  symbols: [EURUSD]
  timeframes: [M5]
  spread_limits:
    default: 2.0
  sessions: []
  live_enabled: false
  paper_enabled: true
  news_filter_enabled: false
""".strip(),
        encoding="utf-8",
    )

    snapshot = DashboardDataService(tmp_path).load_snapshot()

    assert snapshot.account_balance == 10020.0
    assert snapshot.mode == "paper"
    assert snapshot.regime == "ranging"
    assert snapshot.regime_confidence == 0.65
    assert len(snapshot.open_trades) == 1
    assert len(snapshot.recent_trades) == 1
    assert "pending momentum" in snapshot.latest_decision
