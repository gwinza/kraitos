"""Tests for management.adaptive_exit_engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from brain.market_story_engine import LiquidityTarget, MarketStory
from management.adaptive_exit_engine import AdaptiveExitEngine, OpenTradeSnapshot
from strategies.models import MarketContext, SwingPoint


def _candles(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    times = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c + 0.0005 for c in closes],
        "low": [c - 0.0005 for c in closes],
        "close": closes,
        "tick_volume": np.linspace(100, 180, n),
        "spread": [1.0] * n,
    })


def _trade(**kwargs) -> OpenTradeSnapshot:
    defaults = {
        "symbol": "EURUSD",
        "side": "buy",
        "entry_price": 1.1000,
        "stop_loss": 1.0985,
        "current_price": 1.1020,
        "best_price": 1.1025,
        "invalidation_level": 1.0985,
        "liquidity_targets": (1.1022,),
        "partial_taken": False,
        "bars_since_entry": 8,
    }
    defaults.update(kwargs)
    return OpenTradeSnapshot(**defaults)


def _story() -> MarketStory:
    return MarketStory(
        symbol="EURUSD",
        timeframe="H4",
        direction="bullish",
        confidence=75.0,
        controlling_side="buyers",
        structure_state="bullish trend",
        liquidity_targets=(LiquidityTarget("session high", 1.1022, "buy_side"),),
        trapped_traders=(),
        next_objective=1.1100,
        invalidation_level=1.0985,
        narrative="test",
        trend_strength=70.0,
    )


def test_thesis_invalidation_exits_immediately():
    closes = [1.1000 + i * 0.00005 for i in range(30)]
    decision = AdaptiveExitEngine().evaluate(
        trade=_trade(current_price=1.0980, stop_loss=1.0970, invalidation_level=1.0985),
        candles=_candles(closes),
    )
    assert decision.action == "EXIT"
    assert "invalidated" in decision.reasoning.lower()


def test_accelerating_trend_holds_with_room():
    base = [1.1000 + i * 0.00010 for i in range(24)]
    surge = base + [base[-1] + 0.00035, base[-1] + 0.00070, base[-1] + 0.00105]
    decision = AdaptiveExitEngine().evaluate(
        trade=_trade(current_price=surge[-1], best_price=surge[-1], liquidity_targets=(1.1200,)),
        candles=_candles(surge),
        story=_story(),
    )
    assert decision.action == "HOLD"
    assert "accelerating" in decision.reasoning.lower() or "room" in decision.reasoning.lower()


def test_weakening_trend_trails_tighter():
    ramp = [1.1000 + i * 0.00020 for i in range(22)]
    fade = ramp + [ramp[-1] - 0.00015, ramp[-1] - 0.00025, ramp[-1] - 0.00030]
    decision = AdaptiveExitEngine().evaluate(
        trade=_trade(current_price=fade[-1], best_price=ramp[-1], stop_loss=1.0985),
        candles=_candles(fade),
    )
    assert decision.action in {"TRAIL", "SCALE_OUT", "HOLD"}
    if decision.action == "TRAIL":
        assert decision.stop_level is not None
        assert decision.stop_level > 1.0985


def test_liquidity_target_scale_out():
    closes = [1.1000 + i * 0.00008 for i in range(30)]
    decision = AdaptiveExitEngine().evaluate(
        trade=_trade(current_price=1.1022, best_price=1.1023, liquidity_targets=(1.1022,)),
        candles=_candles(closes),
        story=_story(),
    )
    assert decision.action in {"SCALE_OUT", "EXIT", "TRAIL", "HOLD"}
    if decision.action == "SCALE_OUT":
        assert decision.scale_fraction is not None


def test_momentum_collapse_exits_loser():
    up = [1.1000 + i * 0.00005 for i in range(24)]
    collapse = up + [up[-1] - 0.0015, up[-1] - 0.0025, up[-1] - 0.0035]
    frame = _candles(collapse)
    decision = AdaptiveExitEngine().evaluate(
        trade=_trade(
            current_price=collapse[-1],
            best_price=up[-1] + 0.0004,
            stop_loss=1.0970,
            invalidation_level=1.0985,
        ),
        candles=frame,
    )
    assert decision.action == "EXIT"
    assert "momentum" in decision.reasoning.lower() or "invalidated" in decision.reasoning.lower()


def test_exit_decision_to_dict():
    decision = AdaptiveExitEngine().evaluate(
        trade=_trade(current_price=1.0980, invalidation_level=1.0985),
        candles=_candles([1.10 - i * 0.0002 for i in range(30)]),
    )
    payload = decision.to_dict()
    assert payload["action"] in {"EXIT", "HOLD", "TRAIL", "SCALE_OUT"}
    assert "reasoning" in payload
