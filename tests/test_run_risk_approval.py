"""Tests for explicit risk approval step."""

from __future__ import annotations

from core.models import SymbolCycleState
from core.steps.run_risk_approval import run_risk_approval
from execution.models import EntryConfirmation, EntryDecision


class _RuntimeStub:
    def __init__(self) -> None:
        self.event_logger = _LoggerStub()


class _LoggerStub:
    def __init__(self) -> None:
        self.approvals: list[dict] = []
        self.rejections: list[dict] = []

    def risk_approval(self, message, *, symbol, trace_id, lot_size, data=None):
        self.approvals.append(
            {"symbol": symbol, "lot_size": lot_size, "message": message}
        )

    def risk_rejection(self, message, *, symbol, trace_id, reason, data=None):
        self.rejections.append({"symbol": symbol, "reason": reason})


def test_reuses_entry_risk_without_duplicate_evaluation():
    runtime = _RuntimeStub()
    state = SymbolCycleState(
        symbol="EURUSD",
        trace_id="abc",
        entry=EntryDecision(
            action="enter_buy",
            explanation="ok",
            lot_size=0.5,
            confirmations=(
                EntryConfirmation(
                    name="risk",
                    passed=True,
                    detail="Risk approved with lot_size 0.50",
                ),
            ),
        ),
    )
    assert run_risk_approval(runtime, state) is True
    assert state.risk_approved is True
    assert state.risk_lot_size == 0.5
    assert len(runtime.event_logger.approvals) == 1


def test_rejects_when_entry_risk_failed():
    runtime = _RuntimeStub()
    state = SymbolCycleState(
        symbol="EURUSD",
        trace_id="abc",
        entry=EntryDecision(
            action="enter_buy",
            explanation="blocked",
            lot_size=0.0,
            confirmations=(
                EntryConfirmation(
                    name="risk",
                    passed=False,
                    detail="Risk rejected: Max open trades reached",
                ),
            ),
        ),
    )
    assert run_risk_approval(runtime, state) is False
    assert state.risk_approved is False
    assert len(runtime.event_logger.rejections) == 1
