"""Tests for the micro scalper strategy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from strategies import MicroScalper, MicroScalperConfig, MicroScalperError


def _candles(
    closes: np.ndarray,
    *,
    spread: float = 1.2,
    volume: float = 250.0,
    minutes: int = 1,
) -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index, close in enumerate(closes):
        rows.append(
            {
                "time": start + timedelta(minutes=minutes * index),
                "open": close - 0.00005,
                "high": close + 0.0001,
                "low": close - 0.0001,
                "close": close,
                "tick_volume": volume,
                "spread": spread,
            }
        )
    return pd.DataFrame(rows)


def _bullish(length: int = 80, step: float = 0.00005) -> np.ndarray:
    return np.linspace(1.1000, 1.1000 + step * length, length)


def _bearish(length: int = 80, step: float = 0.00005) -> np.ndarray:
    return np.linspace(1.1000, 1.1000 - step * length, length)


def _flat(length: int = 80) -> np.ndarray:
    return np.full(length, 1.1000)


def test_buy_signal_on_aligned_momentum():
    m1 = _candles(_bullish())
    m5 = _candles(_bullish(), minutes=5)

    signal = MicroScalper().scan(m1, m5, spread_limit=2.0)

    assert signal.action == "buy"
    assert 1.0 <= signal.target_pips <= 3.0
    assert "BUY" in signal.reason


def test_sell_signal_on_aligned_momentum():
    m1 = _candles(_bearish())
    m5 = _candles(_bearish(), minutes=5)

    signal = MicroScalper().scan(m1, m5, spread_limit=2.0)

    assert signal.action == "sell"
    assert 1.0 <= signal.target_pips <= 3.0
    assert "SELL" in signal.reason


def test_rejects_high_spread():
    m1 = _candles(_bullish(), spread=3.0)
    m5 = _candles(_bullish(), minutes=5, spread=3.0)

    signal = MicroScalper().scan(m1, m5, spread_limit=2.0)

    assert signal.action == "no_trade"
    assert "Spread is too high" in signal.reason


def test_rejects_chaotic_volatility():
    closes = _bullish()
    m1 = _candles(closes)
    m1.loc[m1.index[-1], ["high", "low"]] = [1.12, 1.08]
    m5 = _candles(_bullish(), minutes=5)

    signal = MicroScalper().scan(m1, m5, spread_limit=2.0)

    assert signal.action == "no_trade"
    assert "chaotic" in signal.reason.lower()


def test_rejects_poor_liquidity():
    m1 = _candles(_bullish(), volume=30.0, spread=1.8)
    m5 = _candles(_bullish(), minutes=5, volume=30.0, spread=1.8)

    signal = MicroScalper().scan(m1, m5, spread_limit=2.0)

    assert signal.action == "no_trade"
    assert "Liquidity is poor" in signal.reason


def test_rejects_unclear_direction():
    m1 = _candles(_bullish())
    m5 = _candles(_bearish(), minutes=5)

    signal = MicroScalper().scan(m1, m5, spread_limit=2.0)

    assert signal.action == "no_trade"
    assert "unclear" in signal.reason.lower()


def test_rejects_flat_direction():
    m1 = _candles(_flat())
    m5 = _candles(_flat(), minutes=5)

    signal = MicroScalper().scan(m1, m5, spread_limit=2.0)

    assert signal.action == "no_trade"
    assert "unclear" in signal.reason.lower()


def test_rejects_insufficient_candles():
    m1 = _candles(_bullish(length=20))
    m5 = _candles(_bullish(length=20), minutes=5)

    with pytest.raises(MicroScalperError, match="M1 requires"):
        MicroScalper(MicroScalperConfig(min_m1_candles=60)).scan(m1, m5)
