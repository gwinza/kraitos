"""Tests for R-multiple calculation helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from validation.metrics_collector import metrics_from_journal_frame
from validation.r_metrics import average_r_from_closed_frame, initial_risk_amount, trade_r_multiple

pytestmark = pytest.mark.offline


def test_initial_risk_amount_from_stop_distance():
    risk = initial_risk_amount(
        symbol="EURUSD",
        entry=1.1000,
        stop_loss=1.0980,
        lot_size=0.10,
    )
    assert risk > 0


def test_trade_r_multiple_recomputes_when_journal_stored_zero():
    row = {
        "symbol": "EURUSD",
        "entry": 1.1000,
        "stop_loss": 1.0980,
        "lot_size": 0.10,
        "profit_loss": 20.0,
        "r_multiple": 0.0,
    }
    assert trade_r_multiple(row) > 0


def test_average_r_from_closed_trades_with_zero_stored_r():
    frame = pd.DataFrame(
        [
            {
                "result": "win",
                "profit_loss": 20.0,
                "symbol": "EURUSD",
                "entry": 1.1000,
                "stop_loss": 1.0980,
                "lot_size": 0.10,
                "r_multiple": 0.0,
                "balance": 10020.0,
                "event_time": "2025-01-01T12:00:00+00:00",
            },
            {
                "result": "loss",
                "profit_loss": -10.0,
                "symbol": "EURUSD",
                "entry": 1.1000,
                "stop_loss": 1.1020,
                "lot_size": 0.10,
                "r_multiple": 0.0,
                "balance": 10010.0,
                "event_time": "2025-01-02T12:00:00+00:00",
            },
        ]
    )
    avg = average_r_from_closed_frame(frame)
    assert avg != 0.0

    metrics = metrics_from_journal_frame(frame, 10_000.0)
    assert metrics.average_r == pytest.approx(avg)
    assert metrics.average_r > 0
