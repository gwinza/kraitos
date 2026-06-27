"""Tests for capital rotation engine."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from portfolio.capital_rotation import CapitalRotationEngine


def test_rotation_favors_high_pf_archetype(tmp_path: Path) -> None:
    engine = CapitalRotationEngine(tmp_path, rotation_interval=5)
    for _ in range(10):
        engine.record_trade(
            symbol="EURUSD",
            mode="harvest",
            result="win",
            r_multiple=0.25,
            drawdown_pct=3.0,
        )
    prefs = engine.preferences()
    key = ("EURUSD", "harvest")
    assert key in prefs
    assert prefs[key].bias in {"favor", "neutral"}
    assert prefs[key].rolling_pf >= 1.0


def test_rotation_reduces_deteriorating(tmp_path: Path) -> None:
    engine = CapitalRotationEngine(tmp_path, rotation_interval=3)
    for _ in range(8):
        engine.record_trade(
            symbol="AUDUSD",
            mode="harvest",
            result="loss",
            r_multiple=-1.0,
            drawdown_pct=14.0,
        )
    mult = engine.risk_multiplier("AUDUSD", "harvest")
    assert mult <= 0.6


def test_rotation_report(tmp_path: Path) -> None:
    engine = CapitalRotationEngine(tmp_path, rotation_interval=2)
    engine.record_trade(
        symbol="GBPUSD", mode="scalp", result="win", r_multiple=0.1, drawdown_pct=2.0
    )
    engine.record_trade(
        symbol="GBPUSD", mode="scalp", result="win", r_multiple=0.2, drawdown_pct=2.0
    )
    path = engine.write_report()
    assert path is not None
    assert "Capital Rotation Report" in path.read_text(encoding="utf-8")
