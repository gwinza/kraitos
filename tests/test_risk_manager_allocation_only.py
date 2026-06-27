"""Tests for Risk Manager Allocation-Only Doctrine."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from controls.drawdown_risk import DrawdownRiskController
from core.risk_controller import catastrophic_gate
from portfolio.capital_allocator import CapitalAllocator
from portfolio.capital_rotation import CapitalRotationEngine
from portfolio.correlation_allocator import CorrelationAllocator
from portfolio.opportunity_classifier import OpportunityClassifier
from portfolio.opportunity_score import OpportunityAllocationScore
from portfolio.portfolio_heat import PortfolioHeatMonitor
from portfolio.risk_budget import RiskBudgetAllocator
from risk.models import OpenPosition, PortfolioState, RiskLimits, TradeRequest
from risk.risk_manager import RiskManager


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


def _pos(symbol: str, risk: float = 100.0) -> OpenPosition:
    return OpenPosition(symbol, "buy", 0.1, 1.1, 1.09, risk)


def _oas(oas: float = 80.0, tier: str = "standard", mult: float = 0.75) -> OpportunityAllocationScore:
    return OpportunityAllocationScore(
        symbol="EURUSD",
        oas=oas,
        edge=80.0,
        diversification=75.0,
        stability=70.0,
        capacity=72.0,
        tier=tier,
        risk_multiplier=mult,
        allow_trade=True,
        reason="test",
    )


def test_max_open_trades_scales_not_blocks() -> None:
    positions = tuple(_pos(f"SYM{i}") for i in range(6))
    manager = RiskManager(RiskLimits(max_open_trades=5))
    decision = manager.evaluate(_request(), _portfolio(open_positions=positions))
    assert decision.approved
    assert decision.lot_size >= 0.01
    assert "Portfolio crowding" in decision.reason or "crowding" in decision.reason.lower()


def test_daily_loss_scales_not_blocks() -> None:
    manager = RiskManager(RiskLimits(max_daily_loss_pct=3.0))
    decision = manager.evaluate(
        _request(),
        _portfolio(daily_realized_pnl=-350.0),
    )
    assert decision.approved
    assert decision.lot_size >= 0.01
    assert "Daily loss" in decision.reason or "scale" in decision.reason.lower()


def test_correlation_scales_not_blocks() -> None:
    positions = (_pos("GBPUSD", 220.0),)
    manager = RiskManager(
        RiskLimits(
            max_correlated_exposure_pct=3.0,
            per_trade_pct=1.0,
            max_risk_per_symbol_pct=5.0,
        )
    )
    decision = manager.evaluate(_request(symbol="EURUSD"), _portfolio(open_positions=positions))
    assert decision.approved
    assert decision.lot_size >= 0.01


def test_symbol_exposure_scales_not_blocks() -> None:
    positions = (_pos("EURUSD", 150.0),)
    manager = RiskManager(RiskLimits(max_risk_per_symbol_pct=2.0, per_trade_pct=1.0))
    decision = manager.evaluate(_request(), _portfolio(open_positions=positions))
    assert decision.approved
    assert decision.lot_size >= 0.01


def test_heat_scales_not_blocks(tmp_path) -> None:
    monitor = PortfolioHeatMonitor(tmp_path)
    positions = tuple(_pos(f"SYM{i}", 130.0) for i in range(10))
    assessment = monitor.assess(_portfolio(open_positions=positions))
    assert assessment.scale_multiplier >= 0.10
    assert assessment.action != "suppress"


def test_loss_streak_scales_not_blocks() -> None:
    controller = DrawdownRiskController()
    for _ in range(5):
        controller.record_trade_result(symbol="EURUSD", mode="harvest", result="loss")
    _, _, mult = controller.evaluate_entry(
        symbol="EURUSD",
        side="buy",
        mode="harvest",
        portfolio=_portfolio(),
    )
    assert mult < 1.0
    assert mult >= 0.05


def test_dd_below_40_scales_not_blocks() -> None:
    manager = RiskManager(RiskLimits())
    portfolio = _portfolio(balance=8_500.0, peak_balance=10_000.0)
    decision = manager.evaluate(_request(), portfolio)
    assert decision.approved
    assert decision.lot_size >= 0.01


def test_dd_at_45_scales_micro_not_blocks() -> None:
    manager = RiskManager(RiskLimits())
    portfolio = _portfolio(balance=5_500.0, peak_balance=10_000.0)
    assert portfolio.drawdown_pct == pytest.approx(45.0)
    decision = manager.evaluate(_request(), portfolio)
    assert decision.approved
    assert decision.lot_size >= 0.01


def test_dd_at_50_blocks() -> None:
    manager = RiskManager(RiskLimits())
    portfolio = _portfolio(balance=5_000.0, peak_balance=10_000.0)
    decision = manager.evaluate(_request(), portfolio)
    assert not decision.approved
    assert "50%" in decision.reason


def test_emergency_stop_blocks() -> None:
    reason = catastrophic_gate(
        portfolio=_portfolio(),
        emergency_stop=True,
        valid_story=True,
    )
    assert reason == "Emergency stop active"


def test_live_trading_violation_blocks() -> None:
    reason = catastrophic_gate(
        portfolio=_portfolio(),
        live_safety_ok=False,
        valid_story=True,
    )
    assert reason == "Live safety violated"


def test_risk_budget_daily_loss_scales(tmp_path) -> None:
    allocator = RiskBudgetAllocator(tmp_path)
    portfolio = _portfolio(daily_realized_pnl=-320.0)
    decision = allocator.allocate(oas=_oas(), portfolio=portfolio)
    assert decision.allow_trade
    assert decision.daily_loss_multiplier <= 0.25


def test_capital_allocator_always_allows_valid_story(tmp_path) -> None:
    allocator = CapitalAllocator(
        risk_budget=RiskBudgetAllocator(tmp_path),
        correlation=CorrelationAllocator(tmp_path),
        heat_monitor=PortfolioHeatMonitor(tmp_path),
        rotation=CapitalRotationEngine(),
    )
    positions = tuple(_pos(f"SYM{i}", 130.0) for i in range(10))
    portfolio = _portfolio(open_positions=positions, daily_realized_pnl=-320.0)
    result = allocator.allocate(oas=_oas(), portfolio=portfolio, side="buy")
    assert result.allow_trade
    assert result.allocated_risk_pct >= 0.01


def test_correlation_allocator_never_blocks(tmp_path) -> None:
    allocator = CorrelationAllocator(tmp_path)
    portfolio = _portfolio(
        open_positions=(_pos("EURUSD"), _pos("GBPUSD"), _pos("AUDUSD")),
    )
    scale = allocator.scale(symbol="NZDUSD", side="buy", portfolio=portfolio)
    assert scale.allow_trade
    assert scale.scale_multiplier >= 0.20
