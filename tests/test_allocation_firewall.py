"""Unit tests for AllocationFirewallEngine."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from risk.allocation_firewall import (
    AllocationFirewallConfig,
    AllocationFirewallEngine,
    AllocationOpportunity,
)
from risk.models import OpenPosition, PortfolioState


def _portfolio(**kwargs) -> PortfolioState:
    defaults = {
        "balance": 10_000.0,
        "open_positions": (),
        "daily_realized_pnl": 0.0,
        "day_start_balance": 10_000.0,
        "peak_balance": 10_000.0,
        "margin_utilization_pct": 0.0,
    }
    defaults.update(kwargs)
    return PortfolioState(**defaults)


def _opp(**kwargs) -> AllocationOpportunity:
    defaults = {"symbol": "EURUSD", "side": "buy", "base_risk_percent": 1.0}
    defaults.update(kwargs)
    return AllocationOpportunity(**defaults)


def _pos(symbol: str, risk: float = 100.0) -> OpenPosition:
    return OpenPosition(symbol, "buy", 0.1, 1.1, 1.09, risk)


def test_high_harvest_score_full_multiplier() -> None:
    engine = AllocationFirewallEngine()
    decision = engine.determine_allocation(
        _opp(harvest_score=92.0),
        _portfolio(),
    )
    assert decision.execute
    assert decision.layer_multipliers["opportunity"] == pytest.approx(1.0)
    assert decision.risk_percent == pytest.approx(1.0)


def test_low_harvest_score_still_executes() -> None:
    engine = AllocationFirewallEngine()
    decision = engine.determine_allocation(
        _opp(harvest_score=65.0),
        _portfolio(),
    )
    assert decision.execute
    assert decision.layer_multipliers["opportunity"] == pytest.approx(0.50)
    assert decision.risk_percent >= 0.05


def test_portfolio_crowding_scales_not_rejects() -> None:
    positions = tuple(_pos(f"S{i}") for i in range(12))
    engine = AllocationFirewallEngine()
    decision = engine.determine_allocation(_opp(), _portfolio(open_positions=positions))
    assert decision.execute
    assert decision.layer_multipliers["portfolio"] == pytest.approx(0.60)


def test_correlation_second_position_scales() -> None:
    engine = AllocationFirewallEngine()
    decision = engine.determine_allocation(
        _opp(symbol="EURUSD"),
        _portfolio(open_positions=(_pos("GBPUSD"),)),
    )
    assert decision.execute
    assert decision.layer_multipliers["correlation"] == pytest.approx(0.80)


def test_drawdown_adaptation_scales() -> None:
    engine = AllocationFirewallEngine()
    decision = engine.determine_allocation(
        _opp(),
        _portfolio(balance=9_600.0, peak_balance=10_000.0),
    )
    assert decision.execute
    assert decision.layer_multipliers["drawdown"] == pytest.approx(0.80)


def test_margin_elevation_scales() -> None:
    engine = AllocationFirewallEngine()
    decision = engine.determine_allocation(
        _opp(margin_utilization_pct=45.0),
        _portfolio(),
    )
    assert decision.execute
    assert decision.layer_multipliers["margin"] == pytest.approx(0.80)


def test_catastrophic_drawdown_blocks() -> None:
    engine = AllocationFirewallEngine()
    decision = engine.determine_allocation(
        _opp(),
        _portfolio(balance=4_900.0, peak_balance=10_000.0),
    )
    assert not decision.execute
    assert decision.risk_percent == 0.0


def test_minimum_risk_floor() -> None:
    cfg = AllocationFirewallConfig(minimum_risk_percent=0.05)
    engine = AllocationFirewallEngine(config=cfg)
    positions = tuple(_pos(f"S{i}") for i in range(35))
    decision = engine.determine_allocation(
        _opp(harvest_score=62.0, base_risk_percent=1.0),
        _portfolio(
            open_positions=positions,
            balance=8_000.0,
            peak_balance=10_000.0,
            margin_utilization_pct=90.0,
        ),
    )
    assert decision.execute
    assert decision.risk_percent >= 0.05


def test_explanation_is_human_readable() -> None:
    engine = AllocationFirewallEngine()
    decision = engine.determine_allocation(
        _opp(harvest_score=88.0),
        _portfolio(open_positions=(_pos("GBPUSD"),)),
    )
    assert "Harvest Score 88" in decision.explanation
    assert "Final allocation:" in decision.explanation


def test_combined_layers_multiply() -> None:
    engine = AllocationFirewallEngine()
    decision = engine.determine_allocation(
        _opp(harvest_score=88.0, base_risk_percent=1.0),
        _portfolio(open_positions=tuple(_pos(f"S{i}") for i in range(8))),
    )
    expected = (
        decision.layer_multipliers["opportunity"]
        * decision.layer_multipliers["portfolio"]
        * decision.layer_multipliers["correlation"]
        * decision.layer_multipliers["drawdown"]
        * decision.layer_multipliers["margin"]
        * decision.layer_multipliers["daily_loss"]
        * decision.layer_multipliers["symbol_exposure"]
    )
    assert decision.allocation_multiplier == pytest.approx(min(1.0, expected), rel=0.01)
