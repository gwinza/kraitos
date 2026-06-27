"""Tests for learning.trade_review_brain."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from learning.trade_review_brain import ClosedTradeContext, TradeReviewBrain


def _trade(**kwargs) -> ClosedTradeContext:
    defaults = {
        "trade_id": "t1",
        "symbol": "GBPJPY",
        "side": "buy",
        "entry_price": 188.50,
        "exit_price": 189.20,
        "stop_loss": 188.00,
        "r_multiple": 1.4,
        "net_pl": 70.0,
        "won": True,
        "entry_type": "liquidity_sweep_rejection",
        "exit_action": "TRAIL",
        "peak_r": 2.1,
        "trough_r": -0.2,
        "bars_held": 18,
        "story_direction": "bullish",
        "story_confidence": 76.0,
        "story_narrative": "H4 buyers in control",
        "thesis_text": "Sweep reclaim long",
        "invalidation_level": 188.00,
        "session": "london",
    }
    defaults.update(kwargs)
    return ClosedTradeContext(**defaults)


def test_winner_well_timed_lesson(tmp_path: Path):
    record = TradeReviewBrain(tmp_path).review(_trade())
    assert record.won
    assert record.lesson.confidence >= 60
    assert record.lesson.lesson
    assert record.findings.entry_timing == "well_timed"
    assert record.findings.story_verdict == "correct"
    assert record.lesson.recommended_change in {
        "boost_entry_type_on_symbol",
        "hold_runners_on_acceleration",
        "boost_conviction_on_setup",
    }


def test_late_entry_loss_lesson(tmp_path: Path):
    record = TradeReviewBrain(tmp_path).review(
        _trade(
            trade_id="t2",
            won=False,
            r_multiple=-0.9,
            net_pl=-45.0,
            exit_price=188.05,
            peak_r=0.15,
            trough_r=-0.95,
            bars_held=4,
        )
    )
    assert not record.won
    assert record.findings.entry_timing in {"too_late", "too_early", "unclear"}
    assert record.lesson.recommended_change in {
        "increase_entry_patience",
        "reduce_size_on_setup",
        "improve_story_confirmation",
        "tighten_stop_selection",
        "reduce_entry_patience",
    }
    assert "loss" in record.lesson.lesson.lower() or "late" in record.lesson.lesson.lower()


def test_exit_too_early_on_winner(tmp_path: Path):
    record = TradeReviewBrain(tmp_path).review(
        _trade(
            trade_id="t3",
            peak_r=2.8,
            r_multiple=1.0,
            exit_price=189.00,
        )
    )
    assert record.findings.exit_timing == "too_early"
    assert record.lesson.recommended_change == "hold_runners_on_acceleration"


def test_wrong_story_loss(tmp_path: Path):
    record = TradeReviewBrain(tmp_path).review(
        _trade(
            trade_id="t4",
            side="buy",
            story_direction="bearish",
            won=False,
            r_multiple=-1.0,
            net_pl=-50.0,
            exit_price=188.00,
            peak_r=0.1,
            trough_r=-1.0,
        )
    )
    assert record.findings.story_verdict == "incorrect"
    assert record.lesson.recommended_change == "improve_story_confirmation"


def test_feeds_personality_memory(tmp_path: Path):
    from learning.pair_personality_memory import PairPersonalityMemory

    personality = PairPersonalityMemory(tmp_path)
    brain = TradeReviewBrain(tmp_path, personality_memory=personality)
    brain.review(_trade(trade_id="mem-1"))
    profile = personality.get_profile("GBPJPY")
    assert profile.total_trades == 1


def test_scoring_adjustments_from_lessons(tmp_path: Path):
    brain = TradeReviewBrain(tmp_path)
    for i in range(3):
        brain.review(_trade(trade_id=f"win-{i}", won=True, r_multiple=1.2))
    adj = brain.scoring_adjustments("GBPJPY")
    assert "conviction_boost" in adj


def test_persist_and_report(tmp_path: Path):
    brain = TradeReviewBrain(tmp_path)
    brain.review(_trade())
    report = brain.write_report()
    assert report.exists()
    assert brain.lessons_path.exists()
    content = brain.lessons_path.read_text(encoding="utf-8")
    assert "GBPJPY" in content
