"""Tests for thesis-projected entry/exit (no travel evidence gate)."""

from __future__ import annotations

import pandas as pd
import pytest

from intelligence.individual_trade_doctrine import (
    DynamicExitEngine,
    DynamicExitPlan,
    IndividualTradeDoctrineEngine,
    ThesisProjectionEngine,
    reset_individual_trade_tracker,
)
from intelligence.thesis_projection_learning_engine import (
    ThesisProjectionBucketStats,
    ThesisProjectionLearningEngine,
)


def _m1_frame(
    *,
    start: str = "2025-01-10 08:00:00+00:00",
    n: int = 30,
    bullish: bool = True,
) -> pd.DataFrame:
    ts = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    if bullish:
        close = pd.Series([1.1000 + i * 0.00005 for i in range(n)])
    else:
        close = pd.Series([1.1000 - i * 0.00005 for i in range(n)])
    return pd.DataFrame(
        {
            "time": ts,
            "open": close - 0.00002,
            "high": close + 0.00010,
            "low": close - 0.00010,
            "close": close,
            "tick_volume": 100,
            "spread": 1.0,
        }
    )


def _m5_bullish_reclaim(sweep: float = 1.0990) -> tuple[pd.DataFrame, pd.DataFrame]:
    m1 = _m1_frame(n=40, bullish=True)
    m1.loc[m1.index[:5], "low"] = sweep - 0.0005
    m1.loc[m1.index[-1], "close"] = sweep + 0.0008
    m5 = m1.iloc[::5].copy().reset_index(drop=True)
    return m1, m5


def _with_entry_timing(m5: pd.DataFrame) -> pd.DataFrame:
    """Tight 3-bar consolidation so should_enter() passes."""
    out = m5.copy()
    mid = float(out.iloc[-4]["close"])
    for idx in out.index[-3:]:
        out.loc[idx, "open"] = mid
        out.loc[idx, "high"] = mid + 0.00005
        out.loc[idx, "low"] = mid - 0.00005
        out.loc[idx, "close"] = mid + 0.00001
    return out


@pytest.fixture
def engine() -> IndividualTradeDoctrineEngine:
    reset_individual_trade_tracker()
    return IndividualTradeDoctrineEngine()


def test_story_clear_projects_entry_from_thesis_levels(
    engine: IndividualTradeDoctrineEngine,
) -> None:
    m1 = _m1_frame(bullish=False, n=20)
    m5 = _with_entry_timing(m1.iloc[::5].reset_index(drop=True))
    plan = engine.build_plan(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        target_liquidity=1.1040,
        opportunity_type="liquidity_sweep",
        regime_label="ranging",
        story_clear=True,
        structure_trend="bearish",
        bias_label="bullish",
        spread_pips=1.0,
        spread_limit=3.0,
        candles={"M1": m1, "M5": m5},
        thesis_confidence=65.0,
        thesis_reward_risk=1.5,
    )
    assert plan.readiness.state == "READY_NOW"
    assert plan.entry_allowed
    assert "Thesis entry" in plan.readiness.reasons[0]


def test_bullish_sweep_enters_when_thesis_projects_levels(
    engine: IndividualTradeDoctrineEngine,
) -> None:
    m1, m5 = _m5_bullish_reclaim(sweep=1.0990)
    m5 = _with_entry_timing(m5)
    plan = engine.build_plan(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1010,
        stop_loss=1.0990,
        target_liquidity=1.1040,
        opportunity_type="liquidity_sweep",
        regime_label="ranging",
        story_clear=True,
        structure_trend="bearish",
        bias_label="bullish",
        spread_pips=1.0,
        spread_limit=3.0,
        candles={"M1": m1, "M5": m5},
        sweep_level=1.0990,
        thesis_confidence=72.0,
        thesis_reward_risk=1.2,
    )
    assert plan.readiness.state == "READY_NOW"
    assert plan.entry_allowed


def test_choppy_fragile_gets_fast_tp_and_reduced_size(engine: IndividualTradeDoctrineEngine) -> None:
    m1, m5 = _m5_bullish_reclaim()
    m5 = _with_entry_timing(m5)
    plan = engine.build_plan(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1010,
        stop_loss=1.0990,
        target_liquidity=1.1025,
        opportunity_type="mean_reversion_snapback",
        regime_label="ranging",
        story_clear=True,
        structure_trend="neutral",
        bias_label="neutral",
        spread_pips=1.0,
        spread_limit=3.0,
        candles={"M1": m1, "M5": m5},
        thesis_confidence=60.0,
        thesis_reward_risk=0.9,
    )
    assert plan.personality.kind == "RANGE_MEAN_REVERSION"
    assert plan.tp_mode == "FAST_TP"
    assert plan.tp1_r <= 0.90
    if plan.entry_allowed:
        assert plan.size_multiplier <= 0.75


def test_trend_continuation_allows_runner(engine: IndividualTradeDoctrineEngine) -> None:
    m1, m5 = _m5_bullish_reclaim()
    m5 = _with_entry_timing(m5)
    plan = engine.build_plan(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1050,
        stop_loss=1.1030,
        target_liquidity=1.1120,
        opportunity_type="pullback_continuation",
        regime_label="trending",
        story_clear=True,
        structure_trend="bullish",
        bias_label="bullish",
        spread_pips=1.0,
        spread_limit=3.0,
        candles={"M1": m1, "M5": m5},
        thesis_confidence=80.0,
        thesis_reward_risk=2.0,
    )
    assert plan.personality.kind == "TREND_CONTINUATION"
    assert plan.tp_mode in {"NORMAL_TP", "EXPANSION_TP"}


def test_low_reward_skips_or_reduces(engine: IndividualTradeDoctrineEngine) -> None:
    plan = engine.build_plan(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        target_liquidity=1.1005,
        opportunity_type="liquidity_sweep",
        regime_label="ranging",
        story_clear=True,
        structure_trend="bullish",
        bias_label="bullish",
        spread_pips=2.0,
        spread_limit=3.0,
        candles={"M1": _m1_frame(), "M5": _m1_frame(n=10).iloc[::2]},
        thesis_confidence=55.0,
        thesis_reward_risk=0.2,
    )
    assert not plan.entry_allowed or plan.tp1_r <= 0.90


def test_early_exit_on_regret_after_grace() -> None:
    closes = [1.1000 + i * 0.0002 for i in range(50)]
    closes.extend([1.1098 - i * 0.0010 for i in range(12)])
    ts = pd.date_range("2025-01-10", periods=len(closes), freq="5min", tz="UTC")
    m5 = pd.DataFrame(
        {
            "time": ts,
            "open": [c - 0.00005 for c in closes],
            "high": [c + 0.00010 for c in closes],
            "low": [c - 0.00010 for c in closes],
            "close": closes,
            "tick_volume": 100,
            "spread": 1.0,
        }
    )
    evaluation = DynamicExitEngine.evaluate_open_position(
        side="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        current_price=1.0990,
        bars_since_entry=25,
        partial_taken=True,
        spread_pips=1.0,
        spread_limit=3.0,
        exit_plan=DynamicExitPlan(enable_early_exit=True),
        candles=m5,
        best_price=1.1030,
    )
    assert evaluation.decision == "EXIT_EARLY"


def test_trail_on_moderate_regret() -> None:
    closes = [1.1000 + i * 0.0002 for i in range(55)]
    closes.extend([1.1018, 1.1016, 1.1014])
    ts = pd.date_range("2025-01-10", periods=len(closes), freq="5min", tz="UTC")
    m5 = pd.DataFrame(
        {
            "time": ts,
            "open": [c - 0.00005 for c in closes],
            "high": [c + 0.00010 for c in closes],
            "low": [c - 0.00010 for c in closes],
            "close": closes,
            "tick_volume": 100,
            "spread": 1.0,
        }
    )
    evaluation = DynamicExitEngine.evaluate_open_position(
        side="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        current_price=1.1014,
        bars_since_entry=25,
        partial_taken=True,
        spread_pips=1.0,
        spread_limit=3.0,
        exit_plan=DynamicExitPlan(enable_early_exit=True),
        candles=m5,
        best_price=1.1018,
    )
    assert evaluation.decision in {"HOLD", "MOVE_TO_BREAKEVEN"}


def test_exit_holds_during_grace_period() -> None:
    closes = [1.1000 + i * 0.0001 for i in range(30)]
    ts = pd.date_range("2025-01-10", periods=len(closes), freq="5min", tz="UTC")
    m5 = pd.DataFrame(
        {
            "time": ts,
            "open": [c - 0.00005 for c in closes],
            "high": [c + 0.00010 for c in closes],
            "low": [c - 0.00010 for c in closes],
            "close": closes,
            "tick_volume": 100,
            "spread": 1.0,
        }
    )
    evaluation = DynamicExitEngine.evaluate_open_position(
        side="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        current_price=1.1005,
        bars_since_entry=5,
        partial_taken=False,
        spread_pips=1.0,
        spread_limit=3.0,
        exit_plan=DynamicExitPlan(enable_early_exit=True),
        candles=m5,
        best_price=1.1010,
    )
    assert evaluation.decision == "HOLD"


def test_trail_tightens_stop_on_progress() -> None:
    closes = [1.1000 + i * 0.0003 for i in range(60)]
    ts = pd.date_range("2025-01-10", periods=len(closes), freq="5min", tz="UTC")
    m5 = pd.DataFrame(
        {
            "time": ts,
            "open": [c - 0.00005 for c in closes],
            "high": [c + 0.00010 for c in closes],
            "low": [c - 0.00010 for c in closes],
            "close": closes,
            "tick_volume": 100,
            "spread": 1.0,
        }
    )
    evaluation = DynamicExitEngine.evaluate_open_position(
        side="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        current_price=1.1010,
        bars_since_entry=30,
        partial_taken=True,
        spread_pips=1.0,
        spread_limit=3.0,
        exit_plan=DynamicExitPlan(enable_early_exit=True),
        candles=m5,
        best_price=1.1012,
    )
    assert evaluation.decision in {"HOLD", "MOVE_TO_BREAKEVEN"}


def test_unclear_story_skipped(engine: IndividualTradeDoctrineEngine) -> None:
    flat = _m1_frame(bullish=False, n=15)
    plan = engine.build_plan(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        target_liquidity=1.1040,
        opportunity_type="liquidity_sweep",
        regime_label="ranging",
        story_clear=False,
        structure_trend="bullish",
        bias_label="bullish",
        spread_pips=1.0,
        spread_limit=3.0,
        candles={"M1": flat, "M5": flat.iloc[::3]},
        thesis_confidence=40.0,
        thesis_reward_risk=1.0,
    )
    assert plan.readiness.state == "SKIP_WEAK_OPPORTUNITY"
    assert not plan.entry_allowed


def test_unknown_personality_skipped(engine: IndividualTradeDoctrineEngine) -> None:
    plan = engine.build_plan(
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        target_liquidity=1.1040,
        opportunity_type="",
        regime_label="transitional",
        story_clear=False,
        structure_trend="neutral",
        bias_label="neutral",
        spread_pips=1.0,
        spread_limit=3.0,
        candles={"M1": _m1_frame(), "M5": _m1_frame(n=10)},
    )
    assert plan.personality.kind in {"UNKNOWN", "CHOPPY_FRAGILE_SETUP", "RANGE_MEAN_REVERSION"}
    assert not plan.entry_allowed


def test_sell_enters_when_thesis_projects_levels(engine: IndividualTradeDoctrineEngine) -> None:
    m1 = _m1_frame(bullish=True, n=25)
    m5 = _with_entry_timing(m1.iloc[::5].copy().reset_index(drop=True))
    plan = engine.build_plan(
        symbol="EURUSD",
        side="sell",
        entry_price=1.1000,
        stop_loss=1.1020,
        target_liquidity=1.0960,
        opportunity_type="liquidity_sweep",
        regime_label="ranging",
        story_clear=True,
        structure_trend="bearish",
        bias_label="bearish",
        spread_pips=1.0,
        spread_limit=3.0,
        candles={"M1": m1, "M5": m5},
        thesis_confidence=68.0,
        thesis_reward_risk=1.4,
    )
    assert plan.readiness.state == "READY_NOW"
    assert plan.entry_allowed


def test_projection_engine_blocks_weak_reward() -> None:
    from intelligence.individual_trade_doctrine import PERSONALITY_PROFILES

    assessment = ThesisProjectionEngine.assess(
        side="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        target_liquidity=1.1003,
        personality=PERSONALITY_PROFILES["LIQUIDITY_SWEEP_REVERSAL"],
        story_clear=True,
        thesis_confidence=60.0,
        thesis_reward_risk=0.2,
        spread_pips=1.0,
        spread_limit=3.0,
    )
    assert assessment.state == "SKIP_WEAK_OPPORTUNITY"


def test_projection_learning_tightens_losing_bucket(tmp_path) -> None:
    engine = ThesisProjectionLearningEngine(project_root=tmp_path)
    key = engine.bucket_key(
        personality="LIQUIDITY_SWEEP_REVERSAL",
        side="buy",
        in_active_session=True,
    )
    bucket = ThesisProjectionBucketStats(samples=7, wins=2, total_r=-4.0)
    engine.buckets[key] = bucket
    engine._adapt_bucket(bucket)
    assert bucket.samples == 7

    bucket.samples = 8
    engine._adapt_bucket(bucket)
    assert bucket.tp1_r_multiplier < 1.0
    assert bucket.size_multiplier_delta < 0
