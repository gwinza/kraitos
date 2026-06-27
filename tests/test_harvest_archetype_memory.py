"""Tests for harvest archetype memory."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from intelligence.harvest_archetype_memory import (
    HarvestArchetypeMemory,
    infer_archetype,
)


def test_infer_archetype_london_pullback() -> None:
    archetype = infer_archetype(
        session="london",
        regime="trending",
        trend_quality="institutional_trend",
        asset_state="strong_uptrend",
    )
    assert archetype == "london_pullback_harvest"


def test_infer_archetype_asian_range() -> None:
    archetype = infer_archetype(
        session="asia",
        regime="ranging",
        trend_quality="weak_trend",
        asset_state="ranging",
    )
    assert archetype == "asian_range_scalp"


def test_check_defaults_approved(tmp_path: Path) -> None:
    memory = HarvestArchetypeMemory(tmp_path)
    result = memory.check(
        symbol="EURUSD",
        session="london",
        regime="trending",
        trend_quality="institutional_trend",
        asset_state="strong_uptrend",
    )
    assert result.allowed
    assert result.status == "APPROVED"
    assert result.risk_multiplier == 1.0


def test_quarantined_archetype_blocks(tmp_path: Path) -> None:
    memory = HarvestArchetypeMemory(tmp_path)
    from intelligence.harvest_archetype_memory import ArchetypeRecord

    key = memory._key("EURUSD", "london_pullback_harvest", "london", "trending")
    memory._records[key] = ArchetypeRecord(
        symbol="EURUSD",
        archetype="london_pullback_harvest",
        session="london",
        regime="trending",
        trades=20,
        win_rate=0.3,
        profit_factor=0.5,
        status="QUARANTINED",
    )
    result = memory.check(
        symbol="EURUSD",
        session="london",
        regime="trending",
        trend_quality="institutional_trend",
        asset_state="strong_uptrend",
    )
    assert not result.allowed
    assert result.status == "QUARANTINED"


def test_refresh_from_journal(tmp_path: Path) -> None:
    journal = tmp_path / "logs" / "conservative_trade_journal.csv"
    journal.parent.mkdir(parents=True)
    frame = pd.DataFrame(
        {
            "event_time": ["2025-01-15T10:00:00+00:00"] * 10,
            "symbol": ["EURUSD"] * 10,
            "mode": ["harvest"] * 10,
            "result": ["win"] * 7 + ["loss"] * 3,
            "profit_loss": [50.0] * 7 + [-30.0] * 3,
            "r_multiple": [0.5] * 7 + [-0.3] * 3,
            "balance": [10_000 + i * 10 for i in range(10)],
            "regime": ["trending"] * 10,
        }
    )
    frame.to_csv(journal, index=False)
    memory = HarvestArchetypeMemory(tmp_path)
    records = memory.refresh_from_journal(journal)
    assert len(records) >= 1
    assert memory.path.exists()


def test_write_report(tmp_path: Path) -> None:
    memory = HarvestArchetypeMemory(tmp_path)
    path = memory.write_report()
    assert path.exists()
