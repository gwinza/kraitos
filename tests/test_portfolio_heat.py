"""Tests for portfolio heat monitor."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from portfolio.portfolio_heat import PortfolioHeatMonitor
from risk.models import OpenPosition, PortfolioState


def _portfolio(risk_total: float) -> PortfolioState:
    count = max(1, int(risk_total / 100))
    positions = tuple(
        OpenPosition(f"SYM{i}", "buy", 0.1, 1.1, 1.09, 100.0)
        for i in range(count)
    )
    return PortfolioState(balance=10_000.0, open_positions=positions, peak_balance=10_000.0)


def test_heat_cool_band(tmp_path: Path) -> None:
    monitor = PortfolioHeatMonitor(tmp_path)
    assessment = monitor.assess(_portfolio(200.0))
    assert assessment.band in {"low", "moderate"}
    assert assessment.scale_multiplier >= 0.85


def test_heat_catastrophic_scales_to_floor(tmp_path: Path) -> None:
    monitor = PortfolioHeatMonitor(tmp_path)
    assessment = monitor.assess(_portfolio(1300.0))
    assert assessment.band in {"extreme", "catastrophic"}
    assert assessment.scale_multiplier == pytest.approx(0.10)


def test_heat_report(tmp_path: Path) -> None:
    monitor = PortfolioHeatMonitor(tmp_path)
    monitor.assess(_portfolio(500.0))
    path = monitor.write_report()
    assert path is not None
    assert "Portfolio Heat Report" in path.read_text(encoding="utf-8")
