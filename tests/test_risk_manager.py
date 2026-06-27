"""Tests for the risk manager."""

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


def test_calculate_lot_size_from_risk():
    manager = RiskManager(RiskLimits(per_trade_pct=1.0, pip_size=0.0001))

    lot_size = manager.calculate_lot_size(
        balance=10_000,
        risk_pct=1.0,
        entry_price=1.1000,
        stop_loss=1.0980,
        pip_size=0.0001,
        pip_value_per_lot=10.0,
    )

    assert lot_size == 0.5


def test_approves_valid_trade():
    manager = RiskManager(RiskLimits())
    decision = manager.evaluate(_request(), _portfolio())

    assert decision.approved is True
    assert decision.lot_size > 0
    assert "Allocation approved" in decision.reason


def test_scales_when_max_open_trades_reached():
    positions = tuple(
        OpenPosition(
            symbol=f"SYM{i}",
            side="buy",
            volume=0.1,
            entry_price=1.1,
            stop_loss=1.09,
            risk_amount=50,
        )
        for i in range(6)
    )
    manager = RiskManager(RiskLimits(max_open_trades=5))
    decision = manager.evaluate(_request(), _portfolio(open_positions=positions))

    assert decision.approved is True
    assert decision.lot_size >= 0.01
    assert "Portfolio crowding" in decision.reason or "crowding" in decision.reason.lower()


def test_scales_when_max_daily_loss_reached():
    manager = RiskManager(RiskLimits(max_daily_loss_pct=3.0))
    decision = manager.evaluate(
        _request(),
        _portfolio(daily_realized_pnl=-350.0),
    )

    assert decision.approved is True
    assert decision.lot_size >= 0.01


def test_scales_when_symbol_risk_exceeded():
    positions = (
        OpenPosition(
            symbol="EURUSD",
            side="buy",
            volume=0.5,
            entry_price=1.1000,
            stop_loss=1.0980,
            risk_amount=150.0,
        ),
    )
    manager = RiskManager(RiskLimits(max_risk_per_symbol_pct=2.0, per_trade_pct=1.0))
    decision = manager.evaluate(_request(), _portfolio(open_positions=positions))

    assert decision.approved is True
    assert decision.lot_size >= 0.01


def test_scales_when_correlated_exposure_exceeded():
    positions = (
        OpenPosition(
            symbol="GBPUSD",
            side="buy",
            volume=0.5,
            entry_price=1.3000,
            stop_loss=1.2980,
            risk_amount=220.0,
        ),
    )
    manager = RiskManager(
        RiskLimits(
            max_correlated_exposure_pct=3.0,
            per_trade_pct=1.0,
            max_risk_per_symbol_pct=5.0,
        )
    )
    decision = manager.evaluate(_request(symbol="EURUSD"), _portfolio(open_positions=positions))

    assert decision.approved is True
    assert decision.lot_size >= 0.01


def test_rejects_invalid_buy_stop_loss():
    manager = RiskManager(RiskLimits())
    decision = manager.evaluate(
        _request(stop_loss=1.1010),
        _portfolio(),
    )

    assert decision.approved is False
    assert "below entry" in decision.reason
    assert decision.lot_size == 0.0


def test_floors_to_min_lot_when_base_too_small():
    manager = RiskManager(RiskLimits(per_trade_pct=0.01, min_lot_size=0.01))
    decision = manager.evaluate(
        _request(stop_loss=1.0000),
        _portfolio(balance=100.0, peak_balance=100.0),
    )

    assert decision.approved is True
    assert decision.lot_size >= 0.01


def test_catastrophic_drawdown_blocks():
    manager = RiskManager(RiskLimits())
    decision = manager.evaluate(
        _request(),
        _portfolio(balance=5_000.0, peak_balance=10_000.0),
    )
    assert decision.approved is False
    assert "50%" in decision.reason
