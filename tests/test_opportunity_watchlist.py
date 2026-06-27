"""Tests for opportunity watchlist."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from portfolio.opportunity_score import OpportunityAllocationScore
from portfolio.opportunity_watchlist import OpportunityWatchlist


def _oas(score: float = 72.0) -> OpportunityAllocationScore:
    return OpportunityAllocationScore(
        symbol="GBPUSD",
        oas=score,
        edge=75.0,
        diversification=70.0,
        stability=68.0,
        capacity=72.0,
        tier="reduced",
        risk_multiplier=0.5,
        allow_trade=True,
        reason="test",
    )


def test_watchlist_add_and_promote(tmp_path: Path) -> None:
    wl = OpportunityWatchlist(tmp_path)
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    entry = wl.add(
        symbol="GBPUSD",
        side="buy",
        oas=_oas(),
        state="WAITING_FOR_RISK_BUDGET",
        reason="heat over limit",
        evaluation_moment=now,
    )
    assert entry.state == "WAITING_FOR_RISK_BUDGET"
    promoted = wl.promote("GBPUSD", "buy", evaluation_moment=now)
    assert promoted is not None
    assert promoted.state == "PROMOTED_TO_TRADE"


def test_watchlist_expires_stale(tmp_path: Path) -> None:
    wl = OpportunityWatchlist(tmp_path, ttl_hours=1.0)
    past = datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc)
    wl.add(
        symbol="EURUSD",
        side="sell",
        oas=_oas(60.0),
        state="WAITING_FOR_SPREAD",
        reason="spread wide",
        evaluation_moment=past,
    )
    expired = wl.expire_stale(past + timedelta(hours=2))
    assert len(expired) == 1
    assert expired[0].state == "EXPIRED"
    assert len(wl.waiting()) == 0


def test_watchlist_classify_deferral() -> None:
    wl = OpportunityWatchlist()
    assert wl.classify_deferral(
        heat_over_limit=False,
        correlation_blocked=True,
        spread_too_wide=False,
        needs_confirmation=False,
    ) == "WAITING_FOR_CORRELATION_RELIEF"


def test_watchlist_report(tmp_path: Path) -> None:
    wl = OpportunityWatchlist(tmp_path)
    wl.add(
        symbol="USDJPY",
        side="buy",
        oas=_oas(),
        state="WAITING_FOR_CONFIRMATION",
        reason="needs bias",
    )
    path = wl.write_report()
    assert path is not None
    assert "USDJPY" in path.read_text(encoding="utf-8")
