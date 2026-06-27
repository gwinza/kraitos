"""Tests for DNA v1.0 audit metric recomputation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from validation.dna_v1_audit import (
    MIN_REWARD_RISK,
    audit_partial_exits,
    audit_thesis_rr,
    classify_thesis_quality,
    recompute_core_metrics,
    run_dna_v1_audit,
)
from validation.metrics_collector import metrics_from_journal_frame
from validation.r_metrics import CLOSED_RESULTS


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_recompute_matches_metrics_collector(project_root: Path) -> None:
    journal = project_root / "logs" / "conservative_trade_journal.csv"
    if not journal.exists():
        pytest.skip("conservative journal not present")
    frame = pd.read_csv(journal)
    reported = metrics_from_journal_frame(frame, 10_000.0)
    metrics = recompute_core_metrics(frame, initial_balance=10_000.0)
    assert metrics["profit_factor"] == pytest.approx(reported.profit_factor, rel=1e-9)
    assert metrics["event_avg_r"] == pytest.approx(reported.average_r, rel=1e-9)
    assert metrics["event_level"].win_rate == pytest.approx(reported.win_rate, rel=1e-9)


def test_position_count_le_event_count(project_root: Path) -> None:
    journal = project_root / "logs" / "conservative_trade_journal.csv"
    if not journal.exists():
        pytest.skip("conservative journal not present")
    frame = pd.read_csv(journal)
    metrics = recompute_core_metrics(frame)
    closed = frame[frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS)]
    assert metrics["position_count"] <= len(closed)
    assert metrics["position_count"] >= metrics["event_level"].total_trades - 100


def test_partial_exit_audit_structure(project_root: Path) -> None:
    journal = project_root / "logs" / "conservative_trade_journal.csv"
    if not journal.exists():
        pytest.skip("conservative journal not present")
    frame = pd.read_csv(journal)
    closed = frame[frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS)]
    partial = audit_partial_exits(closed)
    assert partial["partial_events"] > 0
    assert partial["unique_partial_trades"] == partial["partial_events"]
    assert partial["orphan_partial_trades"] >= 0


def test_thesis_rr_audit(project_root: Path) -> None:
    journal = project_root / "logs" / "conservative_trade_journal.csv"
    if not journal.exists():
        pytest.skip("conservative journal not present")
    frame = pd.read_csv(journal)
    rr = audit_thesis_rr(frame)
    assert rr["n_opens"] > 0
    assert rr["avg_pretrade_rr_tp2"] > 0


def test_classify_thesis_quality_sums(project_root: Path) -> None:
    journal = project_root / "logs" / "conservative_trade_journal.csv"
    if not journal.exists():
        pytest.skip("conservative journal not present")
    frame = pd.read_csv(journal)
    result = classify_thesis_quality(frame)
    total = result["class_a"] + result["class_b"] + result["class_c"]
    assert total == result["total"]
    assert result["total"] == (frame["result"] == "open").sum()


def test_run_dna_v1_audit_writes_reports(project_root: Path, tmp_path: Path) -> None:
    journal = project_root / "logs" / "conservative_trade_journal.csv"
    metrics = project_root / "logs" / "validation_metrics.json"
    if not journal.exists() or not metrics.exists():
        pytest.skip("validation artifacts not present")

    import shutil

    logs = tmp_path / "logs"
    logs.mkdir()
    shutil.copy(journal, logs / "conservative_trade_journal.csv")
    shutil.copy(metrics, logs / "validation_metrics.json")
    for name in [
        "council_trade_frequency_diagnostic.md",
        "unlimited_opportunity_execution_report.md",
        "participation_activity_report.md",
        "thesis_doctrine_report.md",
    ]:
        src = project_root / "logs" / name
        if src.exists():
            shutil.copy(src, logs / name)

    paths = run_dna_v1_audit(tmp_path)
    assert len(paths) == 6
    for path in paths.values():
        assert path.exists()
        assert path.stat().st_size > 200


def test_min_reward_risk_constant() -> None:
    assert MIN_REWARD_RISK == 0.80
