"""Tests for learning.pair_personality_memory."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from learning.pair_personality_memory import (
    PRIORITY_INSTRUMENTS,
    PairPersonalityMemory,
    infer_entry_type_from_reason,
    normalize_entry_type,
)


def _record_wins(
    memory: PairPersonalityMemory,
    symbol: str,
    entry_type: str,
    *,
    count: int,
    avg_r: float,
) -> None:
    for i in range(count):
        memory.record_outcome(
            trade_id=f"{symbol}-{entry_type}-win-{i}",
            symbol=symbol,
            won=True,
            r_multiple=avg_r,
            net_pl=avg_r * 10.0,
            entry_type=entry_type,
            setup_key=entry_type,
            session="london",
        )


def _record_losses(
    memory: PairPersonalityMemory,
    symbol: str,
    entry_type: str,
    *,
    count: int,
) -> None:
    for i in range(count):
        memory.record_outcome(
            trade_id=f"{symbol}-{entry_type}-loss-{i}",
            symbol=symbol,
            won=False,
            r_multiple=-0.8,
            net_pl=-8.0,
            entry_type=entry_type,
            setup_key=entry_type,
            session="london",
            failure_pattern=f"{entry_type}_late_entry",
        )


def test_priority_instruments_defined():
    assert "GBPJPY" in PRIORITY_INSTRUMENTS
    assert "EURUSD" in PRIORITY_INSTRUMENTS


def test_gbpjpy_prefers_liquidity_sweep_over_breakout_retest(tmp_path: Path):
    memory = PairPersonalityMemory(tmp_path)
    _record_wins(memory, "GBPJPY", "liquidity_sweep_rejection", count=8, avg_r=1.2)
    _record_wins(memory, "GBPJPY", "retest_broken_structure", count=8, avg_r=0.15)
    _record_losses(memory, "GBPJPY", "retest_broken_structure", count=4)

    ranked = memory.rank_entry_types(
        "GBPJPY",
        ("retest_broken_structure", "liquidity_sweep_rejection"),
    )
    assert ranked[0].entry_type == "liquidity_sweep_rejection"
    assert ranked[0].score > ranked[1].score
    assert "GBPJPY" in ranked[0].reason

    guidance = memory.guidance_for(
        "GBPJPY",
        entry_candidates=("retest_broken_structure", "liquidity_sweep_rejection"),
        session="london",
    )
    assert guidance.preferred_entry == "liquidity_sweep_rejection"
    assert "liquidity" in guidance.explanation.lower()


def test_separate_memory_per_symbol(tmp_path: Path):
    memory = PairPersonalityMemory(tmp_path)
    _record_wins(memory, "EURUSD", "pullback_into_value", count=6, avg_r=0.9)
    _record_wins(memory, "GBPUSD", "compression_before_expansion", count=6, avg_r=1.1)

    eur = memory.get_profile("EURUSD")
    gbp = memory.get_profile("GBPUSD")
    assert "pullback_into_value" in eur.best_entry_types
    assert "compression_before_expansion" in gbp.best_entry_types
    assert eur.symbol != gbp.symbol


def test_failure_patterns_tracked(tmp_path: Path):
    memory = PairPersonalityMemory(tmp_path)
    _record_losses(memory, "XAUUSD", "liquidity_sweep_rejection", count=3)
    profile = memory.get_profile("XAUUSD")
    assert profile.common_failure_patterns
    assert profile.failure_patterns


def test_entry_type_boost_uses_history(tmp_path: Path):
    memory = PairPersonalityMemory(tmp_path)
    _record_wins(memory, "USDJPY", "pullback_into_value", count=6, avg_r=0.7)
    boost = memory.entry_type_boost("USDJPY", "pullback_into_value")
    unknown = memory.entry_type_boost("USDJPY", "liquidity_sweep_rejection")
    assert boost > unknown


def test_infer_entry_from_journal_reason():
    reason = "Story opportunity: liquidity_sweep; pullback after BOS"
    assert infer_entry_type_from_reason(reason) == "liquidity_sweep_rejection"


def test_refresh_from_journal(tmp_path: Path):
    journal = tmp_path / "logs" / "conservative_trade_journal.csv"
    journal.parent.mkdir(parents=True)
    frame = pd.DataFrame([
        {
            "trade_id": "t1",
            "event_time": "2024-06-01T10:00:00+00:00",
            "symbol": "GBPJPY",
            "result": "win",
            "profit_loss": 25.0,
            "r_multiple": 1.1,
            "reason": "Story opportunity: liquidity_sweep",
        },
        {
            "trade_id": "t2",
            "event_time": "2024-06-01T14:00:00+00:00",
            "symbol": "GBPJPY",
            "result": "loss",
            "profit_loss": -15.0,
            "r_multiple": -0.7,
            "reason": "breakout retest failed",
        },
    ])
    frame.to_csv(journal, index=False)

    memory = PairPersonalityMemory(tmp_path)
    profiles = memory.refresh_from_journal(journal)
    assert "GBPJPY" in profiles
    assert profiles["GBPJPY"].total_trades == 2


def test_persist_and_reload(tmp_path: Path):
    memory = PairPersonalityMemory(tmp_path)
    _record_wins(memory, "EURUSD", "trend_continuation", count=5, avg_r=0.6)
    memory.save()

    reloaded = PairPersonalityMemory(tmp_path)
    profile = reloaded.get_profile("EURUSD")
    assert profile.total_trades == 5
    assert normalize_entry_type("liquidity_sweep") == "liquidity_sweep_rejection"
