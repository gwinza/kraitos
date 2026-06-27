"""Tests for the backtesting engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from backtesting import BacktestConfig, BacktestError, Backtester, TradeSignal


def _candles(prices: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index, (open_, high, low, close) in enumerate(prices):
        rows.append(
            {
                "time": start + timedelta(hours=index),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": 100,
                "spread": 2,
            }
        )
    return pd.DataFrame(rows)


def test_buy_take_profit_hit():
    candles = _candles(
        [
            (1.1000, 1.1010, 1.0990, 1.1005),
            (1.1005, 1.1050, 1.1000, 1.1040),
        ]
    )
    signals = [
        TradeSignal(
            bar_index=0,
            side="buy",
            volume=0.1,
            stop_loss=1.0950,
            take_profit=1.1040,
        )
    ]
    config = BacktestConfig(initial_balance=10_000, spread_pips=0.0, pip_size=0.0001)

    result = Backtester(config).run(candles, signals)

    assert result.metrics is not None
    assert result.metrics.total_trades == 1
    assert result.metrics.winning_trades == 1
    assert result.metrics.win_rate == 1.0
    assert result.metrics.final_balance > result.metrics.initial_balance
    assert result.trades[0].exit_reason == "take_profit"


def test_buy_stop_loss_hit():
    candles = _candles(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),
            (1.1000, 1.1005, 1.0940, 1.0950),
        ]
    )
    signals = [
        TradeSignal(
            bar_index=0,
            side="buy",
            volume=0.1,
            stop_loss=1.0950,
            take_profit=1.1100,
        )
    ]
    config = BacktestConfig(initial_balance=10_000, spread_pips=0.0)

    result = Backtester(config).run(candles, signals)

    assert result.metrics is not None
    assert result.metrics.losing_trades == 1
    assert result.metrics.final_balance < result.metrics.initial_balance
    assert result.trades[0].exit_reason == "stop_loss"


def test_sell_take_profit_hit():
    candles = _candles(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),
            (1.1000, 1.1005, 1.0940, 1.0950),
        ]
    )
    signals = [
        TradeSignal(
            bar_index=0,
            side="sell",
            volume=0.1,
            stop_loss=1.1050,
            take_profit=1.0950,
        )
    ]
    config = BacktestConfig(initial_balance=10_000, spread_pips=0.0)

    result = Backtester(config).run(candles, signals)

    assert result.metrics is not None
    assert result.metrics.winning_trades == 1
    assert result.trades[0].exit_reason == "take_profit"


def test_spread_reduces_profit():
    candles = _candles(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),
            (1.1000, 1.1050, 1.0990, 1.1040),
        ]
    )
    signals = [
        TradeSignal(
            bar_index=0,
            side="buy",
            volume=0.1,
            stop_loss=1.0900,
            take_profit=1.1040,
        )
    ]

    no_spread = Backtester(BacktestConfig(spread_pips=0.0)).run(candles, signals)
    with_spread = Backtester(BacktestConfig(spread_pips=2.0)).run(candles, signals)

    assert with_spread.metrics.final_balance < no_spread.metrics.final_balance


def test_metrics_profit_factor_and_drawdown():
    candles = _candles(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),
            (1.1000, 1.1050, 1.0990, 1.1040),
            (1.1040, 1.1045, 1.0980, 1.0990),
            (1.0990, 1.1030, 1.0980, 1.1020),
        ]
    )
    signals = [
        TradeSignal(bar_index=0, side="buy", volume=0.1, stop_loss=1.0950, take_profit=1.1040),
        TradeSignal(bar_index=2, side="buy", volume=0.1, stop_loss=1.0950, take_profit=1.1030),
    ]
    config = BacktestConfig(initial_balance=10_000, spread_pips=0.0)

    result = Backtester(config).run(candles, signals)

    assert result.metrics.total_trades == 2
    assert result.metrics.profit_factor > 0
    assert result.metrics.max_drawdown >= 0
    assert "equity" in result.equity_curve.columns
    assert len(result.equity_curve) == len(candles)


def test_trade_closed_on_final_bar_if_still_open():
    candles = _candles(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),
            (1.1000, 1.1010, 1.0995, 1.1005),
        ]
    )
    signals = [
        TradeSignal(
            bar_index=0,
            side="buy",
            volume=0.1,
            stop_loss=1.0800,
            take_profit=1.2000,
        )
    ]

    result = Backtester(BacktestConfig(spread_pips=0.0)).run(candles, signals)

    assert result.trades[0].exit_reason == "close"
    assert result.metrics.total_return != 0 or result.trades[0].pnl != 0


def test_rejects_invalid_signal_index():
    candles = _candles([(1.1, 1.2, 1.0, 1.15)])
    signals = [TradeSignal(bar_index=5, side="buy", volume=0.1, stop_loss=1.0, take_profit=1.2)]

    with pytest.raises(BacktestError, match="out of range"):
        Backtester().run(candles, signals)


def test_rejects_signal_without_exit_levels():
    candles = _candles([(1.1, 1.2, 1.0, 1.15)])
    signals = [TradeSignal(bar_index=0, side="buy", volume=0.1)]

    with pytest.raises(BacktestError, match="stop_loss and/or take_profit"):
        Backtester().run(candles, signals)
