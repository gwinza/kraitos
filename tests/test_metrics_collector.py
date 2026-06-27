"""Tests for validation metrics collection from trade logs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from validation.metrics_collector import collect_from_logs, run_validation_update, write_validation_metrics

pytestmark = pytest.mark.offline


def _write_journal(path: Path) -> None:
    path.write_text(
        "trade_id,event_time,symbol,timeframe,direction,entry,stop_loss,take_profit,"
        "confidence,mode,result,profit_loss,reason,balance,equity,lot_size,r_multiple\n"
        "t1,2025-01-01T12:00:00+00:00,EURUSD,H1,buy,1.1,1.098,1.104,0.8,harvest,win,2.0,tp,102.0,102.0,0.01,2.0\n"
        "t2,2025-01-02T12:00:00+00:00,EURUSD,H1,sell,1.1,1.102,1.096,0.7,harvest,loss,-1.0,sl,101.0,101.0,0.01,-1.0\n",
        encoding="utf-8",
    )


def _write_paper(path: Path) -> None:
    path.write_text(
        "trade_id,event_time,event_type,symbol,side,status,entry_price,exit_price,"
        "lot_size,stop_loss,take_profit,floating_pl,closed_pl,balance,reason\n"
        "p1,2025-02-01T12:00:00+00:00,close,EURUSD,buy,closed,1.1000,1.1010,0.10,1.0990,1.1020,0.0,10.0,10010.0,win\n"
        "p2,2025-02-02T12:00:00+00:00,close,EURUSD,sell,closed,1.1000,1.1010,0.10,1.1020,1.0980,0.0,-5.0,10005.0,loss\n",
        encoding="utf-8",
    )


def test_collect_from_logs_computes_metrics(tmp_path: Path):
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_journal(logs / "trade_journal.csv")
    _write_paper(logs / "paper_trades.csv")

    payload = collect_from_logs(tmp_path, backtest_initial_balance=100.0, paper_initial_balance=10_000.0)

    assert payload["backtest"]["total_trades"] == 2
    assert payload["backtest"]["win_rate"] == pytest.approx(0.5)
    assert payload["paper"]["total_trades"] == 2
    assert payload["summary"]["paper_trades"] == 2
    assert "profit_factor" in payload["backtest"]


def test_write_validation_metrics_creates_file(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    config_dir.joinpath("config.yaml").write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_paper(logs / "paper_trades.csv")

    path = write_validation_metrics(tmp_path, quick=True)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "conservative_metrics" in data
    assert "paper" in data
    assert "trust_verdict" in data
    assert "data_quality_score" in data
    assert data.get("validation_engine") == "conservative"


def test_run_validation_update_writes_report(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    config_dir.joinpath("config.yaml").write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_paper(logs / "paper_trades.csv")

    result, _text, metrics_path, report_path = run_validation_update(tmp_path, quick=True)

    assert metrics_path.exists()
    assert report_path.exists()
    assert result.status in {"NEEDS_MORE_DATA", "FAILED_VALIDATION", "APPROVED_FOR_PAPER_ONLY", "LIVE_READY"}
    report = report_path.read_text(encoding="utf-8")
    assert "Live Readiness Report" in report
    assert "Live trading enabled" in report
