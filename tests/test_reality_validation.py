"""Tests for reality validation protocol."""

from __future__ import annotations

from pathlib import Path

import pytest

from validation.reality_validation import SUCCESS_CRITERIA, build_result_from_journal


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_build_result_from_journal(project_root: Path) -> None:
    journal = project_root / "logs" / "conservative_trade_journal.csv"
    if not journal.exists():
        pytest.skip("conservative journal not present")
    result = build_result_from_journal(journal, data_source="synthetic")
    assert result.overall.trades > 0
    assert result.overall.win_rate >= SUCCESS_CRITERIA["min_wr"]
    assert result.overall.profit_factor >= SUCCESS_CRITERIA["min_pf"]
    assert result.thesis_stats.get("tp1_hit_rate", 0) > 0.5


def test_import_pipeline_report(project_root: Path) -> None:
    from data.importers.pipeline import run_import_pipeline

    reports, path = run_import_pipeline(project_root)
    assert path.exists()
    assert "Data Import Report" in path.read_text(encoding="utf-8")
