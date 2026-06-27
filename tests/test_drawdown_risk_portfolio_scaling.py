"""Tests for drawdown risk with portfolio construction (no throttle stacking)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from controls.drawdown_risk import DrawdownRiskController
from risk.models import OpenPosition, PortfolioState


def _portfolio(positions: tuple[OpenPosition, ...] = ()) -> PortfolioState:
    return PortfolioState(balance=10_000.0, open_positions=positions, peak_balance=10_000.0)


def _pos(symbol: str) -> OpenPosition:
    return OpenPosition(symbol, "buy", 0.1, 1.1, 1.09, 100.0)


def test_portfolio_scaling_allows_cluster_overflow() -> None:
    controller = DrawdownRiskController(portfolio_scaling_mode=True)
    portfolio = _portfolio((_pos("EURUSD"), _pos("GBPUSD")))
    allowed, _, mult = controller.evaluate_entry(
        symbol="AUDUSD",
        side="buy",
        mode="harvest",
        portfolio=portfolio,
    )
    assert allowed
    assert mult == pytest.approx(1.0)


def test_legacy_mode_allows_cluster_overflow() -> None:
    controller = DrawdownRiskController(portfolio_scaling_mode=False)
    portfolio = _portfolio((_pos("EURUSD"), _pos("GBPUSD")))
    allowed, _, mult = controller.evaluate_entry(
        symbol="AUDUSD",
        side="buy",
        mode="harvest",
        portfolio=portfolio,
    )
    assert allowed
    assert mult == pytest.approx(1.0)
