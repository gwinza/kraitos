"""Tests for correlation-aware allocation."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from portfolio.correlation_allocator import CorrelationAllocator
from risk.models import OpenPosition, PortfolioState


def _portfolio(positions: tuple[OpenPosition, ...] = ()) -> PortfolioState:
    return PortfolioState(balance=10_000.0, open_positions=positions, peak_balance=10_000.0)


def _pos(symbol: str, side: str = "buy") -> OpenPosition:
    return OpenPosition(symbol, side, 0.1, 1.1, 1.09, 100.0)  # type: ignore[arg-type]


def test_cluster_overflow_scales_not_blocks(tmp_path: Path) -> None:
    allocator = CorrelationAllocator(tmp_path)
    allocator.set_symbol_pf({"AUDUSD": 1.6})
    portfolio = _portfolio((_pos("EURUSD"), _pos("GBPUSD")))
    scale = allocator.scale(symbol="AUDUSD", side="buy", portfolio=portfolio)
    assert scale.allow_trade
    assert 0.40 <= scale.scale_multiplier < 1.0
    assert scale.cluster_count == 2


def test_same_direction_mild_scale_only(tmp_path: Path) -> None:
    allocator = CorrelationAllocator(tmp_path)
    portfolio = PortfolioState(
        balance=8_800.0,
        peak_balance=10_000.0,
        open_positions=(_pos("EURUSD", "buy"),),
    )
    scale = allocator.scale(symbol="GBPUSD", side="buy", portfolio=portfolio, drawdown_pct=12.0)
    assert scale.allow_trade
    assert scale.scale_multiplier >= 0.70


def test_audusd_stricter_penalty(tmp_path: Path) -> None:
    allocator = CorrelationAllocator(tmp_path)
    allocator.set_symbol_pf({"AUDUSD": 1.2})
    scale = allocator.scale(symbol="AUDUSD", side="buy", portfolio=_portfolio())
    assert scale.scale_multiplier == pytest.approx(0.6)


def test_correlation_report_written(tmp_path: Path) -> None:
    allocator = CorrelationAllocator(tmp_path)
    allocator.scale(symbol="EURUSD", side="buy", portfolio=_portfolio())
    path = allocator.write_report()
    assert path is not None
    assert "Correlation Allocation Report" in path.read_text(encoding="utf-8")
