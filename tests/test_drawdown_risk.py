"""Tests for catastrophic drawdown protection and diagnostic loss streaks."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.offline

from controls.drawdown_risk import DrawdownRiskController, tier_for_drawdown
from risk.models import OpenPosition, PortfolioState


def _portfolio(
    *,
    balance: float = 10_000.0,
    peak: float = 12_000.0,
    positions: tuple[OpenPosition, ...] = (),
) -> PortfolioState:
    return PortfolioState(
        balance=balance,
        open_positions=positions,
        peak_balance=peak,
    )


def _position(symbol: str, side: str = "buy", risk: float = 100.0) -> OpenPosition:
    return OpenPosition(
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        volume=0.1,
        entry_price=1.1,
        stop_loss=1.09,
        risk_amount=risk,
    )


def test_drawdown_tier_catastrophic_only() -> None:
    assert tier_for_drawdown(2.0).risk_multiplier == pytest.approx(1.0)
    assert tier_for_drawdown(12.0).risk_multiplier == pytest.approx(1.0)
    assert tier_for_drawdown(42.0).advisory is True
    assert tier_for_drawdown(42.0).risk_multiplier == pytest.approx(0.10)
    assert tier_for_drawdown(52.0).block_new_entries is True


def test_cluster_cap_does_not_block() -> None:
    controller = DrawdownRiskController()
    portfolio = _portfolio(
        balance=11_500.0,
        peak=12_000.0,
        positions=(
            _position("EURUSD"),
            _position("GBPUSD"),
        ),
    )
    allowed, reason, mult = controller.evaluate_entry(
        symbol="AUDUSD",
        side="buy",
        mode="harvest",
        portfolio=portfolio,
    )
    assert allowed
    assert mult == pytest.approx(1.0)


def test_correlated_stacking_allowed() -> None:
    controller = DrawdownRiskController()
    portfolio = _portfolio(balance=8_500.0, peak=10_000.0, positions=(_position("EURUSD", "buy"),))
    allowed, _, mult = controller.evaluate_entry(
        symbol="GBPUSD",
        side="buy",
        mode="harvest",
        portfolio=portfolio,
        trend_score=85.0,
        trend_quality="institutional_trend",
    )
    assert allowed
    assert mult == pytest.approx(1.0)


def test_no_a_plus_gate_below_catastrophic() -> None:
    controller = DrawdownRiskController()
    portfolio = _portfolio(balance=8_000.0, peak=10_000.0)
    allowed, _, mult = controller.evaluate_entry(
        symbol="EURUSD",
        side="buy",
        mode="harvest",
        portfolio=portfolio,
        trend_score=70.0,
        trend_quality="developing_trend",
    )
    assert allowed
    assert mult == pytest.approx(1.0)


def test_loss_streak_tracked_not_reduced() -> None:
    controller = DrawdownRiskController()
    moment = datetime(2025, 1, 10, 12, 0, tzinfo=timezone.utc)
    for _ in range(3):
        controller.record_trade_result(
            symbol="GBPUSD",
            mode="harvest",
            result="loss",
            evaluation_moment=moment,
        )
    assert controller.loss_streak_count("GBPUSD", "harvest") == 3
    assert controller.loss_streak_multiplier("GBPUSD", "harvest") == pytest.approx(0.75)


def test_loss_streak_never_pauses() -> None:
    controller = DrawdownRiskController()
    moment = datetime(2025, 1, 10, 12, 0, tzinfo=timezone.utc)
    for _ in range(5):
        controller.record_trade_result(
            symbol="AUDUSD",
            mode="harvest",
            result="loss",
            evaluation_moment=moment,
        )
    paused, _ = controller.is_paused("AUDUSD", "harvest", moment)
    assert not paused


def test_addons_allowed_in_elevated_dd() -> None:
    controller = DrawdownRiskController()
    portfolio = _portfolio(balance=8_800.0, peak=10_000.0)
    allowed, _, mult = controller.evaluate_entry(
        symbol="EURUSD",
        side="buy",
        mode="harvest",
        portfolio=portfolio,
        is_addon=True,
    )
    assert allowed
    assert mult == pytest.approx(1.0)
    controller = DrawdownRiskController()
    portfolio = _portfolio(balance=4_900.0, peak=10_000.0)
    allowed, reason, mult = controller.evaluate_entry(
        symbol="EURUSD",
        side="buy",
        mode="harvest",
        portfolio=portfolio,
    )
    assert not allowed
    assert "50%" in (reason or "")
    assert mult == 0.0
