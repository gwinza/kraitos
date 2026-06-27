"""Tests for strategy quality analysis and runtime gate."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from controls.strategy_quality_gate import StrategyQualityGate
from validation.strategy_quality import (
    PF_FULL_RISK,
    PF_QUARANTINE,
    _adaptive_multiplier,
    analyze_conservative_journal,
    refresh_strategy_quality_from_journal,
    save_strategy_quality_filters,
    write_strategy_quality_reports,
)


def _sample_journal(path: Path) -> None:
    rows = [
        {
            "event_time": "2024-06-01T10:00:00+00:00",
            "symbol": "EURUSD",
            "mode": "harvest",
            "result": "win",
            "profit_loss": 120.0,
            "balance": 10_120.0,
            "r_multiple": 1.2,
        },
        {
            "event_time": "2024-06-02T10:00:00+00:00",
            "symbol": "EURUSD",
            "mode": "harvest",
            "result": "loss",
            "profit_loss": -50.0,
            "balance": 10_070.0,
            "r_multiple": -0.5,
        },
        {
            "event_time": "2024-06-03T10:00:00+00:00",
            "symbol": "GBPUSD",
            "mode": "harvest",
            "result": "loss",
            "profit_loss": -80.0,
            "balance": 9_990.0,
            "r_multiple": -0.8,
        },
        {
            "event_time": "2024-06-04T10:00:00+00:00",
            "symbol": "GBPUSD",
            "mode": "harvest",
            "result": "loss",
            "profit_loss": -90.0,
            "balance": 9_900.0,
            "r_multiple": -0.9,
        },
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def test_adaptive_multiplier_rules() -> None:
    assert _adaptive_multiplier(1.0, 5.0) == 0.0
    assert _adaptive_multiplier(1.2, 5.0) == 0.5
    assert _adaptive_multiplier(1.5, 8.0) == 1.0
    assert _adaptive_multiplier(1.5, 12.0) == 0.5


def test_analyze_journal_writes_reports_and_filters(tmp_path: Path) -> None:
    journal = tmp_path / "logs" / "conservative_trade_journal.csv"
    journal.parent.mkdir(parents=True)
    _sample_journal(journal)

    analysis = refresh_strategy_quality_from_journal(tmp_path)
    assert analysis.overall.total_trades == 4
    assert (tmp_path / "logs" / "strategy_quality_report.md").exists()
    assert (tmp_path / "logs" / "symbol_expectancy_report.md").exists()
    assert (tmp_path / "logs" / "regime_expectancy_report.md").exists()
    assert (tmp_path / "logs" / "strategy_quality_filters.json").exists()


def test_strategy_quality_gate_blocks_disabled_symbol(tmp_path: Path) -> None:
    journal = tmp_path / "journal.csv"
    _sample_journal(journal)
    bucket = analyze_conservative_journal(journal)
    bucket.disabled_symbols = ["GBPUSD"]
    bucket.symbol_risk_multipliers = {"GBPUSD": 0.0, "EURUSD": 1.0}
    save_strategy_quality_filters(tmp_path, bucket)
    write_strategy_quality_reports(tmp_path, bucket)

    gate = StrategyQualityGate.from_project(tmp_path)
    assert gate.enabled
    allowed, _ = gate.symbol_allowed("GBPUSD")
    assert not allowed
    assert gate.risk_multiplier("GBPUSD") == 0.0
    assert gate.risk_multiplier("EURUSD") == 1.0


def test_gate_strict_confirmation_raises_thresholds() -> None:
    gate = StrategyQualityGate(
        enabled=True,
        drawdown_strict_pct=10.0,
    )
    assert gate.min_bias_confidence(0.6, 9.0) == 0.6
    assert gate.min_bias_confidence(0.6, 11.0) == pytest.approx(0.75)
    assert gate.min_structure_swings(2, 11.0) == 3


def test_gate_quarantines_symbol_mode() -> None:
    gate = StrategyQualityGate(
        enabled=True,
        quarantined_symbol_modes=frozenset({"EURUSD:harvest"}),
        pf_quarantine=PF_QUARANTINE,
    )
    ok, reason = gate.symbol_mode_allowed("EURUSD", "harvest")
    assert not ok
    assert str(PF_QUARANTINE) in reason
    ok, _ = gate.symbol_mode_allowed("EURUSD", "precision")
    assert ok
