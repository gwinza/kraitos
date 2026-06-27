"""Tests for risk.symbol_specialisation_control."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from risk.symbol_specialisation_control import SymbolSpecialisationControl


def test_gbpjpy_confidence_boost():
    ctrl = SymbolSpecialisationControl()
    boosted = ctrl.adjust_conviction_score("GBPJPY", 70.0)
    assert boosted > 70.0


def test_gbpusd_reduced_risk_unless_exceptional():
    ctrl = SymbolSpecialisationControl()
    decision = ctrl.evaluate(symbol="GBPUSD", conviction_score=65.0)
    assert decision.risk_multiplier < 1.0
    exceptional = ctrl.evaluate(symbol="GBPUSD", conviction_score=85.0, setup_quality=82.0)
    assert exceptional.risk_multiplier >= 0.55
