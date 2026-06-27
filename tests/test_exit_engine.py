"""Tests for the trade exit engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from execution import ExitContext, ExitEngine, ExitEngineConfig, OpenTrade
from execution.exit_engine import ExitEngineError
from strategies.models import MarketContext, SwingPoint


def _candles(closes: np.ndarray) -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index, close in enumerate(closes):
        rows.append(
            {
                "time": start + timedelta(minutes=index),
                "open": close - 0.00005,
                "high": close + 0.0001,
                "low": close - 0.0001,
                "close": close,
                "tick_volume": 200,
                "spread": 1.2,
            }
        )
    return pd.DataFrame(rows)


def _structure() -> MarketContext:
    swing = SwingPoint(
        bar_index=5,
        time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        price=1.10,
        kind="low",
    )
    return MarketContext(
        symbol="EURUSD",
        timeframe="M5",
        trend="bullish",
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=(swing,),
        swing_lows=(swing,),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


def _trade(**kwargs) -> OpenTrade:
    defaults = {
        "symbol": "EURUSD",
        "side": "buy",
        "entry_price": 1.1000,
        "stop_loss": 1.0980,
        "volume": 0.1,
        "take_profit": 1.1030,
        "bars_since_entry": 25,
        "best_price": 1.1020,
        "partial_taken": False,
    }
    defaults.update(kwargs)
    return OpenTrade(**defaults)


def _context(**kwargs) -> ExitContext:
    defaults = {
        "trade": _trade(),
        "current_price": 1.1010,
        "candles": _candles(np.linspace(1.0990, 1.1010, 60)),
        "structure": _structure(),
    }
    defaults.update(kwargs)
    return ExitContext(**defaults)


def test_cut_loss_when_stop_hit():
    decision = ExitEngine().evaluate(_context(current_price=1.0975))

    assert decision.action == "cut_loss"
    assert "Stop loss" in decision.reason


def test_take_profit_when_target_reached():
    decision = ExitEngine().evaluate(_context(current_price=1.1035))

    assert decision.action == "take_profit"
    assert "Take profit" in decision.reason


def test_close_early_on_severe_atr_regret_after_grace():
    falling = np.linspace(1.1020, 1.0990, 60)
    decision = ExitEngine().evaluate(
        _context(
            current_price=1.0990,
            candles=_candles(falling),
            trade=_trade(
                best_price=1.1020,
                bars_since_entry=25,
                partial_taken=True,
                take_profit=None,
            ),
        )
    )

    assert decision.action == "close_early"
    assert "ATR regret" in decision.reason


def test_trail_stop_on_moderate_regret():
    closes = [1.1000 + i * 0.0002 for i in range(55)]
    closes.extend([1.1018, 1.1016, 1.1014])
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index, close in enumerate(closes):
        rows.append(
            {
                "time": start + timedelta(minutes=index),
                "open": close - 0.00005,
                "high": close + 0.0001,
                "low": close - 0.0001,
                "close": close,
                "tick_volume": 200,
                "spread": 1.2,
            }
        )
    frame = pd.DataFrame(rows)
    decision = ExitEngine().evaluate(
        _context(
            current_price=1.1014,
            candles=frame,
            trade=_trade(
                take_profit=None,
                best_price=1.1018,
                bars_since_entry=25,
                partial_taken=True,
            ),
        )
    )

    assert decision.action in {"trail_stop", "hold_trade"}
    if decision.action == "trail_stop":
        assert decision.new_stop_loss is not None


def test_trail_stop_when_in_profit():
    rising = np.linspace(1.0990, 1.1015, 60)
    decision = ExitEngine().evaluate(
        _context(
            current_price=1.1012,
            candles=_candles(rising),
            trade=_trade(
                take_profit=None,
                best_price=1.1015,
                bars_since_entry=25,
                partial_taken=True,
            ),
        )
    )

    assert decision.action == "trail_stop"
    assert decision.new_stop_loss is not None
    assert decision.new_stop_loss > 1.0980


def test_hold_thesis_protection_before_tp1():
    rising = np.linspace(1.0990, 1.1010, 60)
    decision = ExitEngine().evaluate(
        _context(
            current_price=1.1008,
            candles=_candles(rising),
            trade=_trade(
                take_profit=None,
                bars_since_entry=8,
                best_price=1.1010,
                invalidation_level=1.0975,
            ),
        )
    )

    assert decision.action == "hold_trade"
    assert "thesis protection" in decision.reason.lower()


def test_thesis_invalidation_exits_before_tp1():
    decision = ExitEngine().evaluate(
        _context(
            current_price=1.0975,
            trade=_trade(stop_loss=1.0960, invalidation_level=1.0980, take_profit=None),
        )
    )

    assert decision.action == "close_early"
    assert "invalidation" in decision.reason.lower()


def test_hold_runner_leg_uses_profit_protection():
    rising = np.linspace(1.0990, 1.1015, 60)
    decision = ExitEngine().evaluate(
        _context(
            current_price=1.1010,
            candles=_candles(rising),
            trade=_trade(partial_taken=True, take_profit=None, bars_since_entry=25),
        )
    )

    assert decision.action in {"hold_trade", "trail_stop"}


def test_rejects_insufficient_candles():
    with pytest.raises(ExitEngineError, match="At least"):
        ExitEngine().evaluate(
            _context(
                candles=_candles(np.linspace(1.10, 1.11, 10)),
                trade=_trade(partial_taken=True, take_profit=None),
            )
        )
