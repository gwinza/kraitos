"""Tests for partial exit resolution in conservative execution model."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.offline

from backtesting.execution_model import resolve_position_exit
from paper_trading.virtual_account import OpenVirtualPosition


def _position(**kwargs) -> OpenVirtualPosition:
    defaults = {
        "trade_id": "t1",
        "symbol": "EURUSD",
        "timeframe": "M5",
        "direction": "buy",
        "entry": 1.1000,
        "stop_loss": 1.0960,
        "take_profit": 1.1005,
        "lot_size": 0.15,
        "confidence": 0.9,
        "mode": "harvest",
        "reason": "test",
        "risk_amount": 10.0,
        "entry_time": datetime(2023, 1, 1, tzinfo=timezone.utc),
        "partial_tp": 1.10025,
        "runner_tp": 1.1005,
        "partial_fraction": 0.5,
        "move_stop_to_breakeven": True,
    }
    defaults.update(kwargs)
    return OpenVirtualPosition(**defaults)


def test_partial_tp_triggers_before_runner() -> None:
    event = resolve_position_exit(_position(), high=1.10030, low=1.09990)
    assert event is not None
    assert event.partial
    assert event.reason == "partial_take_profit"
    assert event.fraction == 0.5


def test_runner_tp_after_partial_taken() -> None:
    pos = _position(partial_taken=True, partial_tp=None)
    event = resolve_position_exit(pos, high=1.10060, low=1.09990)
    assert event is not None
    assert not event.partial
    assert event.reason == "take_profit"
