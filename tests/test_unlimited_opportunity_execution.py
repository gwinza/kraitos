"""Tests for unlimited opportunity execution doctrine."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from controls.drawdown_risk import DrawdownRiskController
from core.risk_controller import catastrophic_gate
from core.signal_router import SignalRouter
from core.pipeline_models import PipelineResult
from execution.models import EntryDecision
from portfolio.capital_allocator import CapitalAllocator
from portfolio.capital_rotation import CapitalRotationEngine
from portfolio.correlation_allocator import CorrelationAllocator
from portfolio.opportunity_classifier import OpportunityClassifier
from portfolio.opportunity_score import OpportunityAllocationScore
from portfolio.portfolio_heat import PortfolioHeatMonitor
from portfolio.risk_budget import RiskBudgetAllocator
from portfolio.unlimited_opportunity_tracker import UnlimitedOpportunityTracker
from risk.models import OpenPosition, PortfolioState, RiskLimits, TradeRequest
from risk.risk_manager import RiskManager
from strategies.models import HarvestDecision, MicroScalpSignal


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


def _pipeline_result(
    *,
    symbol: str = "EURUSD",
    trace_id: str = "t1",
    setup_kind: str = "harvest",
    approved: bool = True,
    lot_size: float = 0.05,
) -> PipelineResult:
    from strategies.models import MultiTimeframeBiasResult, RegimeResult

    harvest = HarvestDecision(mode="conditional", allowed=True, target_pips=5.0, reason="ok")
    micro = MicroScalpSignal(action="no_trade", reason="n/a")
    if setup_kind == "micro_scalp":
        micro = MicroScalpSignal(action="buy", reason="scalp")
    return PipelineResult(
        symbol=symbol,
        trace_id=trace_id,
        opportunity_key=f"{symbol}:{setup_kind}",
        setup_kind=setup_kind,
        bid=1.0998,
        ask=1.1002,
        spread_pips=0.2,
        spread_limit=2.0,
        regime=RegimeResult(regime="trending", confidence=0.7, reason="trend"),
        bias=MultiTimeframeBiasResult(
            bias="bullish", confidence=0.7, explanation="bull", layers=()
        ),
        structure=None,
        harvest=harvest,
        micro_scalp=micro,
        entry=EntryDecision(action="enter_buy", explanation="test", lot_size=lot_size),
        risk=__import__("risk.models", fromlist=["RiskDecision"]).RiskDecision(
            approved=approved, reason="ok", lot_size=lot_size
        ),
        entry_price=1.1002,
        stop_loss=1.0980,
        take_profit=1.1020,
    )


def test_signal_router_routes_all_candidates_without_dropping() -> None:
    router = SignalRouter()
    results = [
        _pipeline_result(symbol="EURUSD", trace_id="a", setup_kind="harvest"),
        _pipeline_result(symbol="EURUSD", trace_id="b", setup_kind="micro_scalp"),
        _pipeline_result(symbol="GBPUSD", trace_id="c", setup_kind="harvest"),
    ]
    signals = router.route_all(results, risk_pct=1.0)
    assert len(signals) == 3
    trade_count = sum(1 for s in signals if s.decision == "TRADE")
    assert trade_count == 3


def test_twenty_candidates_all_execute(tmp_path) -> None:
    router = SignalRouter()
    results = [
        _pipeline_result(symbol=f"SYM{i:02d}", trace_id=f"t{i}", setup_kind="harvest")
        for i in range(20)
    ]
    signals = router.route_all(results, risk_pct=1.0)
    assert len(signals) == 20
    assert all(s.decision == "TRADE" for s in signals)


def test_fifty_candidates_scaled_sizes(tmp_path) -> None:
    allocator = CapitalAllocator(
        risk_budget=RiskBudgetAllocator(tmp_path),
        correlation=CorrelationAllocator(tmp_path),
        heat_monitor=PortfolioHeatMonitor(tmp_path),
        rotation=CapitalRotationEngine(),
    )
    positions = tuple(
        OpenPosition(f"SYM{i}", "buy", 0.1, 1.1, 1.09, 130.0) for i in range(10)
    )
    portfolio = _portfolio(open_positions=positions, daily_realized_pnl=-320.0)
    sizes: list[float] = []
    for i in range(50):
        tier_mult = 0.15 + (i % 5) * 0.05
        result = allocator.allocate(
            oas=_oas(oas=45.0 + i, tier="watchlist", mult=tier_mult),
            portfolio=portfolio,
            side="buy",
            base_risk_pct=0.5 + (i % 3) * 0.1,
        )
        assert result.allow_trade
        sizes.append(result.allocated_risk_pct)
    assert len(sizes) == 50
    assert all(s >= 0.01 for s in sizes)
    assert max(sizes) > min(sizes)


def test_risk_manager_scales_not_blocks_on_crowding() -> None:
    positions = tuple(
        OpenPosition(f"SYM{i}", "buy", 0.1, 1.1, 1.09, 100.0) for i in range(8)
    )
    manager = RiskManager(RiskLimits(max_open_trades=5))
    decision = manager.evaluate(_request(), _portfolio(open_positions=positions))
    assert decision.approved
    assert decision.lot_size >= 0.01


def test_dd_below_50_does_not_block() -> None:
    manager = RiskManager(RiskLimits())
    portfolio = _portfolio(balance=5_500.0, peak_balance=10_000.0)
    decision = manager.evaluate(_request(), portfolio)
    assert decision.approved
    assert decision.lot_size >= 0.01


def test_dd_at_50_blocks() -> None:
    manager = RiskManager(RiskLimits())
    portfolio = _portfolio(balance=5_000.0, peak_balance=10_000.0)
    decision = manager.evaluate(_request(), portfolio)
    assert not decision.approved


def test_emergency_stop_blocks() -> None:
    reason = catastrophic_gate(
        portfolio=_portfolio(),
        emergency_stop=True,
        valid_story=True,
    )
    assert reason == "Emergency stop active"


def test_classifier_never_rejects_valid_story(tmp_path) -> None:
    classifier = OpportunityClassifier(tmp_path)
    result = classifier.classify(
        symbol="EURUSD",
        valid_story=True,
        mode="harvest",
        target_pips=4.0,
        drawdown_pct=20.0,
    )
    assert not result.no_trade
    assert result.base_risk_pct >= 0.01


def test_tracker_records_multiple_same_timestamp() -> None:
    tracker = UnlimitedOpportunityTracker()
    moment = "2025-01-01T12:00:00"
    class Cand:
        def __init__(self, symbol: str, setup: str, intent: bool):
            self.symbol = symbol
            self.setup_kind = setup
            self.trade_intent = intent
            self.entry = None
            self.risk = None

    tracker.record_candidates(
        moment_key=moment,
        candidates=[
            Cand("EURUSD", "harvest", True),
            Cand("EURUSD", "micro_scalp", True),
            Cand("GBPUSD", "harvest", True),
        ],
    )
    assert tracker.opportunities_taken == 3
    assert tracker.trades_per_timestamp[moment] == 3


def test_loss_streak_scales_not_pauses() -> None:
    controller = DrawdownRiskController()
    for _ in range(6):
        controller.record_trade_result(symbol="EURUSD", mode="harvest", result="loss")
    allowed, _, mult = controller.evaluate_entry(
        symbol="EURUSD",
        side="buy",
        mode="harvest",
        portfolio=_portfolio(),
    )
    assert allowed
    assert mult < 1.0
    assert mult >= 0.05
