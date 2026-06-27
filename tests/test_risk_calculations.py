"""Offline tests for risk calculation and lot sizing."""

from __future__ import annotations

import pytest

from config.settings import KraitosConfig
from risk import OpenPosition, PortfolioState, RiskLimits, RiskManager, TradeRequest
from tests.fixtures import load_validated_config


def _portfolio(**kwargs) -> PortfolioState:
    defaults = {
        "balance": 10_000.0,
        "open_positions": (),
        "daily_realized_pnl": 0.0,
        "day_start_balance": 10_000.0,
    }
    defaults.update(kwargs)
    return PortfolioState(**defaults)


@pytest.mark.offline
class TestRiskCalculations:
    def test_position_risk_amount_for_buy(self):
        amount = RiskManager.position_risk_amount(
            volume=0.5,
            entry_price=1.1000,
            stop_loss=1.0980,
            pip_size=0.0001,
            pip_value_per_lot=10.0,
        )
        # 20 pips * $10/pip * 0.5 lots = $100
        assert amount == pytest.approx(100.0)

    def test_position_risk_amount_for_sell(self):
        amount = RiskManager.position_risk_amount(
            volume=0.25,
            entry_price=1.1000,
            stop_loss=1.1020,
            pip_size=0.0001,
            pip_value_per_lot=10.0,
        )
        assert amount == pytest.approx(50.0)

    def test_evaluate_returns_risk_amount_in_decision_path(self):
        manager = RiskManager(RiskLimits(per_trade_pct=1.0))
        decision = manager.evaluate(
            TradeRequest(
                symbol="EURUSD",
                side="buy",
                entry_price=1.1000,
                stop_loss=1.0980,
            ),
            _portfolio(),
            harvest_score=95.0,
        )
        assert decision.approved is True
        assert decision.lot_size == pytest.approx(0.5)


@pytest.mark.offline
class TestLotSizing:
    def test_calculate_lot_size_standard_formula(self):
        manager = RiskManager(RiskLimits(per_trade_pct=1.0, pip_size=0.0001))
        lot_size = manager.calculate_lot_size(
            balance=10_000,
            risk_pct=1.0,
            entry_price=1.1000,
            stop_loss=1.0980,
            pip_size=0.0001,
            pip_value_per_lot=10.0,
        )
        assert lot_size == pytest.approx(0.5)

    def test_lot_size_rounds_down_to_step(self):
        manager = RiskManager(RiskLimits(per_trade_pct=0.75, lot_step=0.01))
        lot_size = manager.calculate_lot_size(
            balance=10_000,
            risk_pct=0.75,
            entry_price=1.1000,
            stop_loss=1.0983,
            pip_size=0.0001,
            pip_value_per_lot=10.0,
        )
        assert lot_size == pytest.approx(0.44)

    def test_lot_size_respects_max_lot_cap(self):
        manager = RiskManager(
            RiskLimits(per_trade_pct=5.0, max_lot_size=0.2, pip_size=0.0001)
        )
        lot_size = manager.calculate_lot_size(
            balance=100_000,
            risk_pct=5.0,
            entry_price=1.1000,
            stop_loss=1.0990,
            pip_size=0.0001,
            pip_value_per_lot=10.0,
        )
        assert lot_size == pytest.approx(0.2)

    def test_lot_size_below_minimum_returns_zero(self):
        manager = RiskManager(
            RiskLimits(per_trade_pct=0.01, min_lot_size=0.01, pip_size=0.0001)
        )
        lot_size = manager.calculate_lot_size(
            balance=100.0,
            risk_pct=0.01,
            entry_price=1.1000,
            stop_loss=1.0500,
            pip_size=0.0001,
            pip_value_per_lot=10.0,
        )
        assert lot_size == 0.0

    def test_jpy_pair_uses_correct_pip_size(self):
        manager = RiskManager(RiskLimits(per_trade_pct=1.0))
        decision = manager.evaluate(
            TradeRequest(
                symbol="USDJPY",
                side="buy",
                entry_price=150.00,
                stop_loss=149.50,
            ),
            _portfolio(),
        )
        assert decision.approved is True
        assert decision.lot_size > 0

    def test_from_config_builds_limits_from_yaml(self, kraitos_config: KraitosConfig):
        manager = RiskManager.from_config(kraitos_config)
        assert manager.limits.per_trade_pct == kraitos_config.risk.per_trade_pct
        assert manager.limits.max_open_trades == kraitos_config.risk.max_open_trades

    def test_open_position_risk_accumulates_for_symbol_cap(self):
        positions = (
            OpenPosition(
                symbol="EURUSD",
                side="buy",
                volume=0.4,
                entry_price=1.1000,
                stop_loss=1.0980,
                risk_amount=150.0,
            ),
        )
        manager = RiskManager(RiskLimits(max_risk_per_symbol_pct=2.0, per_trade_pct=1.0))
        decision = manager.evaluate(
            TradeRequest(
                symbol="EURUSD",
                side="buy",
                entry_price=1.1000,
                stop_loss=1.0980,
            ),
            _portfolio(open_positions=positions),
        )
        assert decision.approved is True
        assert decision.lot_size >= 0.01
        assert decision.lot_size < 0.5
