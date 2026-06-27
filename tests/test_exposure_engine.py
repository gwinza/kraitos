"""Tests for currency-leg portfolio exposure control."""

from __future__ import annotations

from portfolio.currency_strength_engine import PairStrengthAnalysis
from portfolio.exposure_engine import ExposureEngine
from risk.models import OpenPosition, PortfolioState


def _portfolio(*positions: OpenPosition) -> PortfolioState:
    return PortfolioState(
        balance=10_000.0,
        peak_balance=10_000.0,
        open_positions=tuple(positions),
    )


def _pos(symbol: str, side: str, risk_amount: float) -> OpenPosition:
    return OpenPosition(
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        volume=0.1,
        entry_price=1.1,
        stop_loss=1.0,
        risk_amount=risk_amount,
    )


def _analysis(
    symbol: str,
    pair_strength: float,
    theme: str = "USD weakness",
) -> PairStrengthAnalysis:
    return PairStrengthAnalysis(
        symbol=symbol,
        base_currency=symbol[:3],
        quote_currency=symbol[3:6],
        base_strength=4.0,
        quote_strength=-3.0,
        pair_strength=pair_strength,
        preferred_side="buy" if pair_strength > 0 else "sell",
        trade_theme=theme,
        theme_confidence=0.8,
        market_regime="trend",
    )


def test_exposure_snapshot_nets_base_and_quote_legs() -> None:
    engine = ExposureEngine()
    snapshot = engine.snapshot(_portfolio(_pos("GBPUSD", "buy", 100.0)))

    assert snapshot.currency_net["GBP"] == 0.01
    assert snapshot.currency_net["USD"] == -0.01
    assert snapshot.independent_ideas == 1


def test_existing_theme_scales_new_trade_even_when_allowed() -> None:
    engine = ExposureEngine()
    portfolio = _portfolio(_pos("GBPUSD", "buy", 100.0))
    decision = engine.evaluate_trade(
        portfolio=portfolio,
        symbol="EURUSD",
        side="buy",
        proposed_risk_pct=1.0,
        pair_analysis=_analysis("EURUSD", 7.0),
    )

    assert decision.allow_trade
    assert decision.action == "scale"
    assert decision.scale_multiplier < 1.0
    assert not decision.independent_idea
    assert decision.trade_theme == "USD weakness"


def test_concentration_above_exceptional_limit_rejects() -> None:
    engine = ExposureEngine()
    portfolio = _portfolio(
        _pos("GBPUSD", "buy", 3_000.0),
        _pos("EURUSD", "buy", 2_500.0),
    )
    decision = engine.evaluate_trade(
        portfolio=portfolio,
        symbol="AUDUSD",
        side="buy",
        proposed_risk_pct=10.0,
        pair_analysis=_analysis("AUDUSD", 8.0),
        exceptional_conviction=True,
    )

    assert not decision.allow_trade
    assert decision.action == "reject"


def test_adaptive_conviction_combines_pair_currency_and_portfolio() -> None:
    engine = ExposureEngine()
    decision = engine.evaluate_trade(
        portfolio=_portfolio(),
        symbol="GBPUSD",
        side="buy",
        proposed_risk_pct=1.0,
        pair_analysis=_analysis("GBPUSD", 7.0),
    )
    conviction = engine.adaptive_conviction(
        symbol="GBPUSD",
        side="buy",
        pair_conviction=7.0,
        pair_analysis=_analysis("GBPUSD", 7.0),
        exposure=decision,
        expected_r=1.5,
    )

    assert conviction.final_conviction > 7.0
    assert conviction.reward_worth_risk
    assert len(conviction.dialogue) == 7
