"""Tests for spread-aware R-based position sizing."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from core.risk_controller import RiskController
from risk.models import RiskDecision


def test_reduces_size_when_expected_r_low() -> None:
    decision = RiskDecision(approved=True, reason="ok", lot_size=0.20)
    scaled = RiskController._apply_r_aware_sizing(
        None,  # type: ignore[arg-type]
        decision,
        spread_pips=1.5,
        target_pips=2.0,
        stop_pips=40.0,
        forecast_confidence=60.0,
        expected_r=0.01,
    )
    assert scaled.approved
    assert scaled.lot_size < 0.20


def test_boosts_size_when_high_confidence_high_r() -> None:
    decision = RiskDecision(approved=True, reason="ok", lot_size=0.20)
    scaled = RiskController._apply_r_aware_sizing(
        None,  # type: ignore[arg-type]
        decision,
        spread_pips=1.0,
        target_pips=12.0,
        stop_pips=40.0,
        forecast_confidence=85.0,
        expected_r=0.28,
    )
    assert scaled.approved
    assert scaled.lot_size > 0.20


def test_neutral_r_leaves_size_unchanged() -> None:
    decision = RiskDecision(approved=True, reason="ok", lot_size=0.15)
    scaled = RiskController._apply_r_aware_sizing(
        None,  # type: ignore[arg-type]
        decision,
        spread_pips=1.0,
        target_pips=5.0,
        stop_pips=40.0,
        forecast_confidence=55.0,
        expected_r=0.10,
    )
    assert scaled.lot_size == 0.15
