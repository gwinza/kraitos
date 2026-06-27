"""Integration tests — RiskManager delegates to AllocationFirewallEngine."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from risk import (
    OpenPosition,
    PortfolioState,
    RiskLimits,
    RiskManager,
    TradeRequest,
)


def _portfolio(**kwargs) -> PortfolioState:
    defaults = {
        "balance": 10_000.0,
        "open_positions": (),
        "daily_realized_pnl": 0.0,
        "day_start_balance": 10_000.0,
        "peak_balance": 10_000.0,
    }
    defaults.update(kwargs)
    return PortfolioState(**defaults)


def _request(**kwargs) -> TradeRequest:
    defaults = {
        "symbol": "EURUSD",
        "side": "buy",
        "entry_price": 1.1000,
        "stop_loss": 1.0980,
    }
    defaults.update(kwargs)
    return TradeRequest(**defaults)


def test_risk_manager_uses_firewall_for_sizing() -> None:
    manager = RiskManager(RiskLimits(per_trade_pct=1.0))
    baseline = manager.evaluate(_request(), _portfolio())
    crowded = manager.evaluate(
        _request(),
        _portfolio(open_positions=tuple(
            OpenPosition(f"S{i}", "buy", 0.1, 1.1, 1.09, 50.0) for i in range(8)
        )),
    )
    assert baseline.approved and crowded.approved
    assert crowded.lot_size < baseline.lot_size
    assert "Allocation approved" in crowded.reason


def test_harvest_score_increases_allocation_vs_low_score() -> None:
    manager = RiskManager(RiskLimits(per_trade_pct=1.0))
    high = manager.evaluate(_request(), _portfolio(), harvest_score=92.0)
    low = manager.evaluate(_request(), _portfolio(), harvest_score=62.0)
    assert high.approved and low.approved
    assert high.lot_size >= low.lot_size


def test_symbol_exposure_scales_not_rejects() -> None:
    positions = (
        OpenPosition("EURUSD", "buy", 0.4, 1.1000, 1.0980, 150.0),
    )
    manager = RiskManager(RiskLimits(max_risk_per_symbol_pct=2.0, per_trade_pct=1.0))
    decision = manager.evaluate(_request(), _portfolio(open_positions=positions))
    assert decision.approved
    assert decision.lot_size >= 0.01
    assert "Symbol exposure" in decision.reason or decision.lot_size < 0.5


def test_catastrophic_dd_blocks_via_firewall() -> None:
    manager = RiskManager(RiskLimits())
    decision = manager.evaluate(
        _request(),
        _portfolio(balance=5_000.0, peak_balance=10_000.0),
    )
    assert not decision.approved
    assert "Catastrophic" in decision.reason


def test_invalid_geometry_still_rejects() -> None:
    manager = RiskManager(RiskLimits())
    decision = manager.evaluate(
        _request(stop_loss=1.1050),
        _portfolio(),
    )
    assert not decision.approved
