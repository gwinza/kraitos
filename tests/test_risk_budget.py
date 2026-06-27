"""Tests for global portfolio risk budget."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from portfolio.opportunity_score import OpportunityAllocationScore
from portfolio.risk_budget import RiskBudgetAllocator, _heat_zone
from risk.models import OpenPosition, PortfolioState


def _oas(oas: float, tier: str = "standard", mult: float = 0.75) -> OpportunityAllocationScore:
    allow = oas >= 50.0
    return OpportunityAllocationScore(
        symbol="EURUSD",
        oas=oas,
        edge=80.0,
        diversification=75.0,
        stability=70.0,
        capacity=72.0,
        tier=tier,
        risk_multiplier=mult,
        allow_trade=allow,
        reason="test",
    )


def _portfolio(risk_amount: float = 0.0) -> PortfolioState:
    positions = ()
    if risk_amount > 0:
        positions = (OpenPosition("EURUSD", "buy", 0.1, 1.1, 1.09, risk_amount),)
    return PortfolioState(balance=10_000.0, open_positions=positions, peak_balance=10_000.0)


def test_heat_zone_classification() -> None:
    assert _heat_zone(6.0) == "normal"
    assert _heat_zone(9.0) == "elevated"
    assert _heat_zone(11.0) == "max"
    assert _heat_zone(13.0) == "over_limit"


def test_risk_budget_scales_at_elevated_heat(tmp_path: Path) -> None:
    allocator = RiskBudgetAllocator(tmp_path)
    portfolio = _portfolio(risk_amount=850.0)
    decision = allocator.allocate(oas=_oas(88.0, "premium", 1.0), portfolio=portfolio)
    assert decision.heat_zone == "elevated"
    assert decision.combined_multiplier < 1.0
    assert decision.allow_trade


def test_risk_budget_scales_low_oas_not_reject(tmp_path: Path) -> None:
    allocator = RiskBudgetAllocator(tmp_path)
    decision = allocator.allocate(
        oas=_oas(45.0, "defer", 0.15),
        portfolio=_portfolio(),
    )
    assert decision.allow_trade
    assert decision.combined_multiplier > 0.0


def test_risk_budget_report_written(tmp_path: Path) -> None:
    allocator = RiskBudgetAllocator(tmp_path)
    allocator.allocate(oas=_oas(80.0), portfolio=_portfolio())
    path = allocator.write_report()
    assert path is not None
    assert path.exists()
    assert "Risk Budget Report" in path.read_text(encoding="utf-8")
