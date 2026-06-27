"""Tests for the structured event logging system."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from logs import KraitosEventLogger, init_event_logger
from logs.models import ALL_CATEGORIES


@pytest.fixture
def logger(tmp_path: Path) -> KraitosEventLogger:
    return KraitosEventLogger(tmp_path)


def test_creates_csv_and_json_files_per_category(logger: KraitosEventLogger, tmp_path: Path):
    trace_id = logger.new_trace_id()
    logger.system_event("startup complete", trace_id=trace_id)
    logger.trade_decision(
        "enter buy",
        symbol="EURUSD",
        trace_id=trace_id,
        action="enter_buy",
    )
    logger.rejected_trade(
        "spread too wide",
        symbol="EURUSD",
        trace_id=trace_id,
        reason="spread",
    )
    logger.risk_approval(
        "approved",
        symbol="EURUSD",
        trace_id=trace_id,
        lot_size=0.5,
    )
    logger.risk_rejection(
        "max trades",
        symbol="EURUSD",
        trace_id=trace_id,
        reason="max open trades",
    )
    logger.executed_trade(
        "paper open",
        symbol="EURUSD",
        trace_id=trace_id,
        event_type="open",
        data={"lot_size": 0.1},
    )
    logger.error("connection failed", trace_id=trace_id, symbol="EURUSD")

    for category in ALL_CATEGORIES:
        csv_path = tmp_path / "csv" / f"{category}.csv"
        json_path = tmp_path / "json" / f"{category}.jsonl"
        assert csv_path.exists(), category
        assert json_path.exists(), category


def test_trace_id_links_related_events(logger: KraitosEventLogger, tmp_path: Path):
    trace_id = logger.new_trace_id()
    logger.trade_decision("wait", symbol="GBPUSD", trace_id=trace_id, action="wait")
    logger.risk_approval("ok", symbol="GBPUSD", trace_id=trace_id, lot_size=0.2)

    csv_path = tmp_path / "csv" / "trade_decisions.csv"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[-1]["trace_id"] == trace_id

    risk_csv = tmp_path / "csv" / "risk_approvals.csv"
    with risk_csv.open(encoding="utf-8", newline="") as handle:
        risk_rows = list(csv.DictReader(handle))

    assert risk_rows[-1]["trace_id"] == trace_id


def test_jsonl_contains_structured_payload(logger: KraitosEventLogger, tmp_path: Path):
    trace_id = logger.new_trace_id()
    logger.executed_trade(
        "filled",
        symbol="EURUSD",
        trace_id=trace_id,
        event_type="close",
        data={"pnl": 12.5},
    )

    json_path = tmp_path / "json" / "executed_trades.jsonl"
    line = json_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    payload = json.loads(line)

    assert payload["trace_id"] == trace_id
    assert payload["data"]["pnl"] == 12.5


def test_error_log_captures_exception(logger: KraitosEventLogger, tmp_path: Path):
    try:
        raise ValueError("test failure")
    except ValueError as exc:
        logger.error("operation failed", exc=exc)

    json_path = tmp_path / "json" / "errors.jsonl"
    payload = json.loads(json_path.read_text(encoding="utf-8").strip())

    assert payload["data"]["exception_type"] == "ValueError"
    assert "test failure" in payload["data"]["exception_message"]


def test_global_logger_init(tmp_path: Path):
    event_logger = init_event_logger(tmp_path)
    assert event_logger.log_dir == tmp_path


def test_rejected_trade_accepts_list_payload(logger: KraitosEventLogger, tmp_path: Path):
    trace_id = logger.new_trace_id()
    logger.rejected_trade(
        "risk denied",
        symbol="GBPUSD",
        trace_id=trace_id,
        reason="max correlated exposure",
        data=[{"name": "risk", "passed": False, "detail": "exceeded"}],
    )

    json_path = tmp_path / "json" / "rejected_trades.jsonl"
    payload = json.loads(json_path.read_text(encoding="utf-8").strip())
    assert payload["data"]["confirmations"][0]["name"] == "risk"
