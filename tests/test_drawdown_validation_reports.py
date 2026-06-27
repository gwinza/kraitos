"""Tests for drawdown validation report writers."""

from __future__ import annotations

from pathlib import Path

from validation.drawdown_attribution import (
    write_drawdown_reduction_validation_report,
    write_post_drawdown_throttle_undo_validation_report,
)

pytestmark = __import__("pytest").mark.offline


def test_post_drawdown_throttle_undo_validation_report_writer(tmp_path: Path):
    current = {
        "total_trades": 440,
        "win_rate": 0.87,
        "profit_factor": 2.0,
        "max_drawdown_pct": 20.5,
        "average_r": 0.14,
    }
    path = write_post_drawdown_throttle_undo_validation_report(
        tmp_path,
        current_metrics=current,
    )
    assert path == tmp_path / "logs" / "post_drawdown_throttle_undo_validation_report.md"
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Post Drawdown Throttle Undo Validation Report" in content
    assert "A (pre-DD throttles)" in content
    assert "D (post-undo — current)" in content
    assert "440" in content
    assert "diagnostic only" in content.lower()


def test_drawdown_reduction_validation_report_writer(tmp_path: Path):
    path = write_drawdown_reduction_validation_report(
        tmp_path,
        current_metrics={
            "total_trades": 200,
            "win_rate": 0.765,
            "profit_factor": 1.33,
            "max_drawdown_pct": 11.19,
            "average_r": 0.07,
        },
    )
    assert path.exists()
    assert "Drawdown Reduction Validation Report" in path.read_text(encoding="utf-8")
