"""Tests for the paper trading simulator."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from execution import PaperTrader, PaperTraderConfig, PaperTraderError


@pytest.fixture
def trader(tmp_path: Path) -> PaperTrader:
    log_path = tmp_path / "paper_trades.csv"
    return PaperTrader(
        PaperTraderConfig(
            initial_balance=10_000.0,
            spread_pips=0.0,
            log_path=log_path,
        )
    )


def test_open_trade_tracks_entry_and_balance(trader: PaperTrader):
    trade = trader.open_trade(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        lot_size=0.1,
        stop_loss=1.0980,
        take_profit=1.1030,
    )

    snapshot = trader.snapshot()

    assert trade.status == "open"
    assert trade.entry_price == 1.1000
    assert snapshot.balance == 10_000.0
    assert len(snapshot.open_trades) == 1
    assert len(snapshot.trade_history) == 1


def test_close_trade_updates_closed_pl_and_balance(trader: PaperTrader):
    trade = trader.open_trade(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        lot_size=0.1,
        stop_loss=1.0980,
        take_profit=1.1030,
    )

    closed = trader.close_trade(trade.trade_id, 1.1020, reason="take profit")

    snapshot = trader.snapshot()

    assert closed.status == "closed"
    assert closed.exit_price == 1.1020
    assert closed.closed_pl == pytest.approx(20.0)
    assert snapshot.closed_pl == pytest.approx(20.0)
    assert snapshot.balance == pytest.approx(10_020.0)
    assert len(snapshot.open_trades) == 0


def test_floating_pl_updates_on_mark_to_market(trader: PaperTrader):
    trade = trader.open_trade(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        lot_size=0.1,
        stop_loss=1.0980,
    )

    snapshot = trader.mark_to_market({"EURUSD": 1.1010})

    assert snapshot.floating_pl == pytest.approx(10.0)
    assert snapshot.equity == pytest.approx(10_010.0)
    assert snapshot.open_trades[0].trade_id == trade.trade_id


def test_scale_out_partially_closes_trade(trader: PaperTrader):
    trade = trader.open_trade(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        lot_size=0.2,
        stop_loss=1.0980,
    )

    trader.scale_out(trade.trade_id, 1.1010, fraction=0.5, reason="partial")

    snapshot = trader.snapshot()

    assert len(snapshot.open_trades) == 1
    assert snapshot.open_trades[0].lot_size == pytest.approx(0.1)
    assert snapshot.closed_pl == pytest.approx(10.0)


def test_update_stop_loss(trader: PaperTrader):
    trade = trader.open_trade(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        lot_size=0.1,
        stop_loss=1.0980,
    )

    updated = trader.update_stop_loss(trade.trade_id, 1.0990)

    assert updated.stop_loss == 1.0990


def test_writes_paper_trades_csv(trader: PaperTrader):
    trade = trader.open_trade(
        symbol="EURUSD",
        side="sell",
        entry_price=1.1000,
        lot_size=0.1,
        stop_loss=1.1020,
    )
    trader.close_trade(trade.trade_id, 1.0980, reason="target hit")

    log_path = trader.config.log_path
    assert log_path.exists()

    with log_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) >= 2
    assert rows[0]["event_type"] == "open"
    assert rows[-1]["event_type"] == "close"
    assert rows[-1]["exit_price"] == "1.09800"
    assert float(rows[-1]["balance"]) > 10_000.0


def test_sell_trade_profit_on_price_fall(trader: PaperTrader):
    trade = trader.open_trade(
        symbol="EURUSD",
        side="sell",
        entry_price=1.1000,
        lot_size=0.1,
        stop_loss=1.1020,
    )
    closed = trader.close_trade(trade.trade_id, 1.0980, reason="target hit")
    snapshot = trader.snapshot()

    assert closed.closed_pl == pytest.approx(20.0)
    assert snapshot.balance == pytest.approx(10_020.0)


def test_rejects_invalid_lot_size(trader: PaperTrader):
    with pytest.raises(PaperTraderError, match="lot_size"):
        trader.open_trade(
            symbol="EURUSD",
            side="buy",
            entry_price=1.1000,
            lot_size=0,
            stop_loss=1.0980,
        )
