"""Tests for ATR entry/exit timing engine."""

from __future__ import annotations

import pandas as pd
import pytest

from execution.atr_timing_engine import compute_atr, should_enter, should_exit


def _frame(closes: list[float], *, spread: float = 0.0002) -> pd.DataFrame:
    rows = []
    for i, close in enumerate(closes):
        rows.append(
            {
                "time": pd.Timestamp("2025-01-10", tz="UTC") + pd.Timedelta(minutes=5 * i),
                "open": close - spread / 2,
                "high": close + spread,
                "low": close - spread,
                "close": close,
                "tick_volume": 100,
                "spread": 1.0,
            }
        )
    return pd.DataFrame(rows)


def test_consolidation_allows_entry() -> None:
    base = [1.1000 + i * 0.0001 for i in range(20)]
    base[-3:] = [1.1020, 1.10201, 1.10202]
    m5 = _frame(base, spread=0.00005)
    atr = compute_atr(m5)
    result = should_enter(side="buy", candles=m5, atr=atr)
    assert result.allowed
    assert result.trigger == "consolidation"


def test_retracement_allows_entry() -> None:
    closes = [1.1000] * 10
    closes.extend([1.1005, 1.1010, 1.1015, 1.1020, 1.1025, 1.1018])
    m5 = _frame(closes)
    atr = compute_atr(m5)
    result = should_enter(side="buy", candles=m5, atr=atr)
    assert result.allowed
    assert result.trigger == "retracement"


def test_entry_blocks_without_trigger() -> None:
    closes = [1.1000 + i * 0.0010 for i in range(15)]
    m5 = _frame(closes)
    result = should_enter(side="buy", candles=m5)
    assert not result.allowed


def test_exit_holds_when_regret_without_peak_progress() -> None:
    """Chop that never reached 0.30R should not hard-exit on mild regret."""
    closes = [1.1000 + (i % 3) * 0.00005 for i in range(60)]
    m5 = _frame(closes, spread=0.00008)
    atr = compute_atr(m5)
    result = should_exit(
        side="buy",
        entry_price=1.1000,
        current_price=1.0998,
        stop_loss=1.0980,
        candles=m5,
        bars_since_entry=25,
        best_price=1.1003,
        atr=atr,
        exit_phase="profit_protection",
        partial_taken=True,
    )
    assert result.action in {"HOLD", "TRAIL"}
    assert result.action != "EXIT"


def test_exit_regret_after_grace() -> None:
    closes = [1.1000 + i * 0.0002 for i in range(50)]
    closes.extend([1.1098 - i * 0.0010 for i in range(12)])
    m5 = _frame(closes)
    atr = compute_atr(m5)
    result = should_exit(
        side="buy",
        entry_price=1.1000,
        current_price=1.0990,
        stop_loss=1.0980,
        candles=m5,
        bars_since_entry=25,
        best_price=1.1030,
        atr=atr,
        exit_phase="profit_protection",
        partial_taken=True,
    )
    assert result.action == "EXIT"


def test_exit_trails_before_hard_regret_cut() -> None:
    closes = [1.1000 + i * 0.0002 for i in range(55)]
    closes.extend([1.1018, 1.1016, 1.1014])
    m5 = _frame(closes)
    atr = compute_atr(m5)
    result = should_exit(
        side="buy",
        entry_price=1.1000,
        current_price=1.1014,
        stop_loss=1.0980,
        candles=m5,
        bars_since_entry=25,
        best_price=1.1018,
        atr=atr,
        exit_phase="profit_protection",
        partial_taken=True,
    )
    assert result.action in {"HOLD", "TRAIL"}


def test_exit_holds_during_grace() -> None:
    closes = [1.1000 + i * 0.0001 for i in range(30)]
    m5 = _frame(closes)
    result = should_exit(
        side="buy",
        entry_price=1.1000,
        current_price=1.1005,
        stop_loss=1.0980,
        candles=m5,
        bars_since_entry=5,
        best_price=1.1010,
        exit_phase="thesis_protection",
    )
    assert result.action == "HOLD"


def test_thesis_protection_ignores_regret() -> None:
    closes = [1.1000 + i * 0.0002 for i in range(50)]
    closes.extend([1.1098 - i * 0.0010 for i in range(12)])
    m5 = _frame(closes)
    result = should_exit(
        side="buy",
        entry_price=1.1000,
        current_price=1.0990,
        stop_loss=1.0980,
        candles=m5,
        bars_since_entry=25,
        best_price=1.1030,
        exit_phase="thesis_protection",
    )
    assert result.action == "HOLD"
