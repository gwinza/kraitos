"""Tests for the trade entry engine."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from execution import EntryContext, EntryEngine
from execution.entry_engine import EntryEngineError
from logs import KraitosEventLogger
from risk import OpenPosition, PortfolioState, RiskLimits, RiskManager
from strategies.trend_quality_engine import TradeStory, TrendQualityMetrics, TrendQualityResult
from strategies.models import (
    MarketContext,
    MicroScalpSignal,
    MultiTimeframeBiasResult,
    RegimeResult,
    SwingPoint,
    TimeframeBiasDetail,
)


def _swing(kind: str, price: float) -> SwingPoint:
    return SwingPoint(
        bar_index=10,
        time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        price=price,
        kind=kind,  # type: ignore[arg-type]
    )


def _bias(direction: str) -> MultiTimeframeBiasResult:
    layers = tuple(
        TimeframeBiasDetail(tf, direction, 0.7, role)  # type: ignore[arg-type]
        for tf, role in [
            ("H8", "macro"),
            ("H4", "macro"),
            ("H1", "structure"),
            ("M15", "setup"),
            ("M5", "setup"),
            ("M1", "precision_entry"),
        ]
    )
    return MultiTimeframeBiasResult(
        bias=direction,  # type: ignore[arg-type]
        confidence=0.75,
        explanation="test",
        layers=layers,
    )


def _structure(trend: str = "bullish") -> MarketContext:
    bullish = trend == "bullish"
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend=trend,  # type: ignore[arg-type]
        higher_highs=bullish,
        higher_lows=bullish,
        lower_highs=not bullish,
        lower_lows=not bullish,
        swing_highs=(_swing("high", 1.12), _swing("high", 1.13)),
        swing_lows=(_swing("low", 1.10), _swing("low", 1.11)),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


def _timing_ready_candles(*, bullish: bool = True) -> pd.DataFrame:
    """M5 frame with 3-bar consolidation for should_enter()."""
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    base = 1.1000
    for index in range(16):
        drift = index * 0.00008 if bullish else -index * 0.00008
        close = base + drift
        rows.append(
            {
                "time": start + timedelta(minutes=5 * index),
                "open": close - 0.00002,
                "high": close + 0.00012,
                "low": close - 0.00012,
                "close": close,
                "tick_volume": 200,
                "spread": 1.2,
            }
        )
    flat_close = rows[-1]["close"]
    for offset in range(3):
        rows.append(
            {
                "time": start + timedelta(minutes=5 * (16 + offset)),
                "open": flat_close,
                "high": flat_close + 0.00003,
                "low": flat_close - 0.00003,
                "close": flat_close,
                "tick_volume": 200,
                "spread": 1.2,
            }
        )
    return pd.DataFrame(rows)


def _context(**kwargs) -> EntryContext:
    defaults = {
        "symbol": "EURUSD",
        "bias": _bias("bullish"),
        "structure": _structure("bullish"),
        "regime": RegimeResult(regime="trending", confidence=0.7, reason="ok"),  # type: ignore[arg-type]
        "momentum": MicroScalpSignal(action="buy", reason="momentum ok", target_pips=30.0),
        "current_spread": 1.5,
        "spread_limit": 2.0,
        "entry_price": 1.1000,
        "stop_loss": 1.0980,
        "portfolio": PortfolioState(balance=10_000, day_start_balance=10_000),
        "risk_manager": RiskManager(RiskLimits()),
        "candles": _timing_ready_candles(),
    }
    defaults.update(kwargs)
    return EntryContext(**defaults)


def _trend_quality_metrics(**kwargs) -> TrendQualityMetrics:
    defaults = {
        "hh_hl_quality": 75,
        "ll_lh_quality": 70,
        "trend_acceleration": 0.6,
        "trend_exhaustion": 0.2,
        "trend_health": 0.75,
        "trend_participation": 0.7,
    }
    defaults.update(kwargs)
    return TrendQualityMetrics(**defaults)


def _trend_quality(
    *,
    direction: str = "bullish",
    phase: str = "expansion",
    continuation: float = 0.75,
    reversal: float = 0.20,
    score: int = 78,
) -> TrendQualityResult:
    return TrendQualityResult(
        symbol="EURUSD",
        timeframe="H1",
        trend_direction=direction,  # type: ignore[arg-type]
        trend_quality_score=score,
        trend_phase=phase,  # type: ignore[arg-type]
        continuation_probability=continuation,
        reversal_probability=reversal,
        regime="trending",
        explanation="test trend quality",
        trade_story=TradeStory(
            previous_thesis="prior",
            current_thesis=f"{direction} {phase}",
            what_changed="test",
            trend_state="stable",
            action="continue",
            explanation="test",
        ),
        metrics=_trend_quality_metrics(),
    )


def test_enter_buy_when_all_confirmations_pass():
    decision = EntryEngine().evaluate(_context())

    assert decision.action == "enter_buy"
    assert decision.lot_size > 0
    assert "Enter BUY" in decision.explanation
    assert len(decision.confirmations) == 15
    assert all(check.passed for check in decision.confirmations)


def test_enter_sell_for_bearish_setup():
    decision = EntryEngine().evaluate(
        _context(
            bias=_bias("bearish"),
            structure=_structure("bearish"),
            momentum=MicroScalpSignal(action="sell", reason="momentum ok", target_pips=30.0),
            stop_loss=1.1020,
            candles=_timing_ready_candles(bullish=False),
        )
    )

    assert decision.action == "enter_sell"
    assert "Enter SELL" in decision.explanation


def test_wait_when_atr_timing_not_ready():
    decision = EntryEngine().evaluate(_context(candles=None))

    assert decision.action == "wait"
    assert "ATR timing" in decision.explanation


def test_reject_when_spread_too_wide():
    decision = EntryEngine().evaluate(_context(current_spread=3.0))

    assert decision.action == "reject"
    assert "spread" in decision.explanation.lower()


def test_reduces_size_when_liquidity_poor():
    normal = EntryEngine().evaluate(_context())
    decision = EntryEngine().evaluate(
        _context(regime=RegimeResult(regime="low_liquidity", confidence=0.8, reason="thin"))  # type: ignore[arg-type]
    )

    assert decision.action == "enter_buy"
    assert decision.lot_size < normal.lot_size
    assert "liquidity" in decision.explanation.lower()


def test_scales_when_open_positions_crowded():
    positions = tuple(
        OpenPosition(
            symbol=f"S{i}",
            side="buy",
            volume=0.1,
            entry_price=1.1,
            stop_loss=1.09,
            risk_amount=50,
        )
        for i in range(5)
    )
    decision = EntryEngine().evaluate(
        _context(portfolio=PortfolioState(balance=10_000, open_positions=positions))
    )

    assert decision.action == "enter_buy"
    assert decision.lot_size > 0
    assert "lot_size" in decision.explanation.lower()


def test_scaled_entry_logs_structured_payload(tmp_path):
    event_logger = KraitosEventLogger(tmp_path)
    positions = tuple(
        OpenPosition(
            symbol=f"S{i}",
            side="buy",
            volume=0.1,
            entry_price=1.1,
            stop_loss=1.09,
            risk_amount=50,
        )
        for i in range(5)
    )
    decision = EntryEngine(event_logger=event_logger).evaluate(
        _context(
            trace_id=event_logger.new_trace_id(),
            portfolio=PortfolioState(balance=10_000, open_positions=positions),
        )
    )

    assert decision.action == "enter_buy"
    decisions_path = tmp_path / "json" / "trade_decisions.jsonl"
    assert decisions_path.exists()
    payload = json.loads(decisions_path.read_text(encoding="utf-8").strip())
    assert isinstance(payload["data"]["confirmations"], list)


def test_reduces_size_when_structure_not_confirmed():
    normal = EntryEngine().evaluate(_context())
    structure = replace(
        _structure("bullish"),
        trend="ranging",
        higher_highs=False,
        higher_lows=False,
    )
    decision = EntryEngine().evaluate(_context(structure=structure))

    assert decision.action == "enter_buy"
    assert decision.lot_size < normal.lot_size
    assert "structure" in decision.explanation.lower()


def test_reduces_size_when_momentum_conflicts():
    normal = EntryEngine().evaluate(_context())
    decision = EntryEngine().evaluate(
        _context(
            momentum=MicroScalpSignal(action="sell", reason="wrong way", target_pips=30.0)
        )
    )

    assert decision.action == "enter_buy"
    assert decision.lot_size < normal.lot_size
    assert "momentum" in decision.explanation.lower()


def test_reduces_size_when_expected_value_is_negative():
    normal = EntryEngine().evaluate(_context())
    decision = EntryEngine().evaluate(
        _context(
            momentum=MicroScalpSignal(action="buy", reason="tiny target", target_pips=2.0)
        )
    )

    assert decision.action == "enter_buy"
    assert decision.lot_size < normal.lot_size
    assert "expectancy" in decision.explanation.lower() or "tradable" in decision.explanation.lower()


def test_planned_target_overrides_tiny_micro_target_for_tradability():
    decision = EntryEngine().evaluate(
        _context(
            momentum=MicroScalpSignal(action="buy", reason="precision confirms", target_pips=2.0),
            expected_target_pips=30.0,
        )
    )

    assert decision.action == "enter_buy"
    tradability = next(check for check in decision.confirmations if check.name == "tradability")
    assert "TP1 1.50R" in tradability.detail


def test_reduces_size_when_bullish_trend_is_reversing():
    normal = EntryEngine().evaluate(_context(trend_quality=_trend_quality()))
    decision = EntryEngine().evaluate(
        _context(
            trend_quality=_trend_quality(
                direction="bullish",
                phase="reversal_warning",
                continuation=0.35,
                reversal=0.62,
                score=35,
            )
        )
    )

    assert decision.action == "enter_buy"
    assert decision.lot_size < normal.lot_size
    assert "trend quality" in decision.explanation.lower()


def test_reduces_size_when_trend_is_exhausted_but_continuation_still_leads():
    normal = EntryEngine().evaluate(_context(trend_quality=_trend_quality()))
    reduced = EntryEngine().evaluate(
        _context(
            trend_quality=_trend_quality(
                direction="bullish",
                phase="exhaustion",
                continuation=0.58,
                reversal=0.42,
                score=52,
            )
        )
    )

    assert reduced.action == "enter_buy"
    assert reduced.lot_size == pytest.approx(normal.lot_size * 0.75)


def test_confirmed_bearish_reversal_allows_sell_bias():
    decision = EntryEngine().evaluate(
        _context(
            bias=_bias("bearish"),
            structure=_structure("bearish"),
            momentum=MicroScalpSignal(action="sell", reason="momentum ok", target_pips=30.0),
            stop_loss=1.1020,
            candles=_timing_ready_candles(bullish=False),
            trend_quality=_trend_quality(
                direction="bearish",
                phase="confirmed_reversal",
                continuation=0.30,
                reversal=0.74,
                score=44,
            ),
        )
    )

    assert decision.action == "enter_sell"


def test_reject_when_bias_neutral():
    decision = EntryEngine().evaluate(_context(bias=_bias("neutral")))

    assert decision.action == "reject"
    assert (
        "bias" in decision.explanation.lower()
        or "resolved" in decision.explanation.lower()
        or "directional" in decision.explanation.lower()
    )


def test_enter_sell_when_bias_neutral_but_story_resolved():
    neutral = MultiTimeframeBiasResult(
        bias="neutral",  # type: ignore[arg-type]
        confidence=0.35,
        explanation="test",
        layers=_bias("bearish").layers,
    )
    decision = EntryEngine().evaluate(
        _context(
            bias=neutral,
            structure=_structure("bearish"),
            momentum=MicroScalpSignal(action="sell", reason="momentum ok", target_pips=30.0),
            stop_loss=1.1020,
            candles=_timing_ready_candles(bullish=False),
            resolved_side="sell",
            patience_ready=True,
        )
    )

    assert decision.action == "enter_sell"
    bias_check = next(c for c in decision.confirmations if c.name == "bias")
    assert bias_check.passed
    assert "Patience-confirmed" in bias_check.detail


def test_bias_failure_is_soft_not_hard_gate():
    """Weak bias reduces size but does not hard-reject when side is story-resolved."""
    normal = EntryEngine().evaluate(_context())
    neutral = MultiTimeframeBiasResult(
        bias="neutral",  # type: ignore[arg-type]
        confidence=0.35,
        explanation="test",
        layers=_bias("bullish").layers,
    )
    weak = EntryEngine().evaluate(
        _context(
            bias=neutral,
            resolved_side="buy",
            patience_ready=True,
        )
    )
    assert weak.action == "enter_buy"
    assert weak.lot_size <= normal.lot_size


def test_rejects_invalid_entry_price():
    with pytest.raises(EntryEngineError, match="entry_price"):
        EntryEngine().evaluate(_context(entry_price=0))
