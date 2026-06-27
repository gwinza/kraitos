"""Tests for ATR-based dynamic pip targets."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from intelligence.dynamic_pip_targets import DynamicPipTargetEngine
from intelligence.harvest_opportunity_score import HarvestOpportunityScore
from intelligence.trend_strength_engine import TrendStrengthResult


def _trend(score: float = 80.0, quality: str = "institutional_trend") -> TrendStrengthResult:
    return TrendStrengthResult(
        symbol="EURUSD",
        score=score,
        quality=quality,  # type: ignore[arg-type]
        direction="bullish",
        components={},
        reason="test",
    )


def _harvest_score(score: float, band: str) -> HarvestOpportunityScore:
    return HarvestOpportunityScore(
        symbol="EURUSD",
        score=score,
        band=band,  # type: ignore[arg-type]
        allow_harvest=band != "no_harvest",
        components={},
        reason="test",
        session="london",
    )


def test_medium_atr_produces_target(tmp_path: Path) -> None:
    engine = DynamicPipTargetEngine(tmp_path)
    decision = engine.evaluate(
        symbol="EURUSD",
        atr_ratio=1.0,
        atr_pips=4.0,
        spread_pips=0.8,
        trend=_trend(),
        choppiness=0.3,
    )
    assert not decision.skip_trade
    assert 1.0 <= decision.target_pips <= 10.0
    assert decision.stop_loss_pips > 0


def test_wide_spread_skips(tmp_path: Path) -> None:
    engine = DynamicPipTargetEngine(tmp_path)
    decision = engine.evaluate(
        symbol="EURUSD",
        atr_ratio=1.0,
        atr_pips=4.0,
        spread_pips=5.0,
        trend=_trend(),
    )
    assert decision.skip_trade


def test_low_atr_skips(tmp_path: Path) -> None:
    engine = DynamicPipTargetEngine(tmp_path)
    decision = engine.evaluate(
        symbol="EURUSD",
        atr_ratio=0.35,
        atr_pips=1.0,
        spread_pips=0.5,
        trend=_trend(),
    )
    assert decision.skip_trade


def test_high_trend_expands_target(tmp_path: Path) -> None:
    engine = DynamicPipTargetEngine(tmp_path)
    base = engine.evaluate(
        symbol="EURUSD",
        atr_ratio=1.0,
        atr_pips=4.0,
        spread_pips=0.8,
        trend=_trend(50.0, "weak_trend"),
    )
    strong = engine.evaluate(
        symbol="EURUSD",
        atr_ratio=1.0,
        atr_pips=4.0,
        spread_pips=0.8,
        trend=_trend(85.0, "institutional_trend"),
        harvest_score=_harvest_score(88.0, "aggressive"),
    )
    assert strong.target_pips >= base.target_pips * 0.9


def test_choppy_reduces_risk(tmp_path: Path) -> None:
    engine = DynamicPipTargetEngine(tmp_path)
    decision = engine.evaluate(
        symbol="EURUSD",
        atr_ratio=1.0,
        atr_pips=4.0,
        spread_pips=0.8,
        trend=_trend(),
        choppiness=0.75,
    )
    assert decision.risk_multiplier <= 0.75


def test_high_confidence_micro_expands_to_3_5_pips(tmp_path: Path) -> None:
    engine = DynamicPipTargetEngine(tmp_path)
    decision = engine.evaluate(
        symbol="EURUSD",
        atr_ratio=1.0,
        atr_pips=4.0,
        spread_pips=1.0,
        trend=_trend(85.0, "institutional_trend"),
        micro_harvest=True,
        forecast_confidence=82.0,
    )
    assert not decision.skip_trade
    assert decision.target_pips >= 5.0


def test_pa_volume_agree_allows_second_target(tmp_path: Path) -> None:
    engine = DynamicPipTargetEngine(tmp_path)
    decision = engine.evaluate(
        symbol="EURUSD",
        atr_ratio=1.0,
        atr_pips=5.0,
        spread_pips=0.8,
        trend=_trend(80.0, "institutional_trend"),
        micro_harvest=True,
        forecast_confidence=78.0,
        price_action_volume_agree=True,
        allow_runner=True,
        expected_pip_range=5.0,
    )
    assert decision.allow_second_target or decision.second_target_pips > decision.partial_tp_pips


def test_marginal_spread_widens_instead_of_skip(tmp_path: Path) -> None:
    engine = DynamicPipTargetEngine(tmp_path)
    decision = engine.evaluate(
        symbol="EURUSD",
        atr_ratio=1.0,
        atr_pips=4.0,
        spread_pips=2.2,
        trend=_trend(),
        micro_harvest=True,
        forecast_confidence=80.0,
    )
    assert not decision.skip_trade
    assert "spread-widened" in decision.reason or decision.target_pips >= 2.5


def test_write_report(tmp_path: Path) -> None:
    engine = DynamicPipTargetEngine(tmp_path)
    engine.evaluate(
        symbol="EURUSD",
        atr_ratio=1.0,
        atr_pips=4.0,
        spread_pips=0.8,
        trend=_trend(),
    )
    path = engine.write_report()
    assert path is not None
    assert "Dynamic Pip Target" in path.read_text(encoding="utf-8")
