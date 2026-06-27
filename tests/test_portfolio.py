"""Tests for portfolio state and daily P/L tracking."""

from __future__ import annotations

from pathlib import Path

import pytest

from config import load_config
from core.daily_tracker import DailyPnLTracker
from core.portfolio import build_portfolio_state
from execution.paper_trader import PaperTrader, PaperTraderConfig
from risk import RiskLimits, RiskManager


def test_daily_tracker_resets_on_new_day(tmp_path: Path):
    tracker = DailyPnLTracker(tmp_path / "daily_pnl_state.json")
    first = tracker.snapshot(10_000.0)
    assert first.daily_realized_pnl == 0.0
    assert first.day_start_balance == 10_000.0

    second = tracker.snapshot(10_150.0)
    assert second.daily_realized_pnl == pytest.approx(150.0)
    assert second.day_start_balance == 10_000.0


def test_portfolio_uses_daily_not_lifetime_pnl(tmp_path: Path):
    config = load_config(Path(__file__).resolve().parent.parent / "config" / "config.yaml")
    trader = PaperTrader(
        PaperTraderConfig(
            initial_balance=10_000.0,
            spread_pips=0.0,
            log_path=tmp_path / "paper_trades.csv",
        )
    )
    # Establish today's opening balance before any realized P/L.
    DailyPnLTracker(tmp_path / "logs" / "daily_pnl_state.json").snapshot(10_000.0)

    trade = trader.open_trade(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        lot_size=0.1,
        stop_loss=1.0980,
    )
    trader.close_trade(trade.trade_id, 1.1020)

    portfolio = build_portfolio_state(
        config=config,
        paper_trader=trader,
        risk_manager=RiskManager(RiskLimits()),
        project_root=tmp_path,
    )

    assert portfolio.daily_realized_pnl == pytest.approx(20.0)
    assert portfolio.day_start_balance == 10_000.0
    assert portfolio.balance == pytest.approx(10_020.0)


def test_portfolio_jpy_risk_uses_adjusted_pip_value(tmp_path: Path):
    config = load_config(Path(__file__).resolve().parent.parent / "config" / "config.yaml")
    trader = PaperTrader(
        PaperTraderConfig(
            initial_balance=10_000.0,
            spread_pips=0.0,
            log_path=tmp_path / "paper_trades.csv",
        )
    )
    trader.open_trade(
        symbol="USDJPY",
        side="buy",
        entry_price=150.00,
        lot_size=0.1,
        stop_loss=149.50,
    )
    portfolio = build_portfolio_state(
        config=config,
        paper_trader=trader,
        risk_manager=RiskManager(RiskLimits()),
        project_root=tmp_path,
    )
    position = portfolio.open_positions[0]
    assert position.risk_amount > 0
    assert position.risk_amount < 10_000.0
