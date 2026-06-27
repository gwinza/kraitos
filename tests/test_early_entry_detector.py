"""Tests for learning.early_entry_detector."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from learning.early_entry_detector import EarlyEntryDetector


def test_early_losses_trigger_delay(tmp_path):
    detector = EarlyEntryDetector(tmp_path)
    for _ in range(3):
        detector.record_outcome(
            symbol="GBPUSD",
            side="sell",
            entry_type="pullback_into_value",
            loss_class="good_idea_early",
            r_multiple=-1.0,
            won=False,
        )
    decision = detector.evaluate_delay(
        symbol="GBPUSD",
        side="sell",
        entry_type="pullback_into_value",
        confirmation_strength=65.0,
    )
    assert decision.delay
    assert "early-entry memory" in decision.reason.lower()
