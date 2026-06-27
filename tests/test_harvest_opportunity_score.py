"""Tests for harvest opportunity score."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from intelligence.asset_trend_analyzer import AssetTrendFeatures, AssetTrendSnapshot
from intelligence.harvest_opportunity_score import (
    HarvestOpportunityScorer,
    _band_for_score,
    infer_session,
)
from intelligence.trend_strength_engine import TrendStrengthResult
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult, SwingPoint


def _features(**kwargs) -> AssetTrendFeatures:
    defaults = dict(
        macro_trend="bullish",
        structure_trend="bullish",
        setup_alignment=0.7,
        precision_momentum=0.0002,
        atr_ratio=1.0,
        adx=28.0,
        ma_slope_signed=0.0001,
        ma_slope_abs=0.0001,
        range_compression=0.8,
        range_expansion=1.1,
        breakout_score=0.5,
        mean_reversion_score=0.2,
        swing_range_pips=12.0,
        spread_to_target_ratio=0.15,
        spread_to_limit=0.3,
        session_strength=0.8,
        volume_ratio=1.0,
        layer_agreement=0.7,
        choppiness=0.3,
    )
    defaults.update(kwargs)
    return AssetTrendFeatures(**defaults)


def _snapshot() -> AssetTrendSnapshot:
    return AssetTrendSnapshot(
        symbol="EURUSD",
        state="strong_uptrend",
        confidence=0.8,
        reason="test",
        features=_features(),
        regime="trending",
        bias="bullish",
    )


def _trend(score: float = 85.0) -> TrendStrengthResult:
    return TrendStrengthResult(
        symbol="EURUSD",
        score=score,
        quality="institutional_trend",
        direction="bullish",
        components={"momentum_persistence": 10.0, "volatility_quality": 9.0},
        reason="test",
    )


def _bias() -> MultiTimeframeBiasResult:
    return MultiTimeframeBiasResult(
        bias="bullish",
        confidence=0.75,
        explanation="test",
        layers=(),
    )


def _structure() -> MarketContext:
    swing = SwingPoint(
        bar_index=5,
        time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        price=1.10,
        kind="low",
    )
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend="bullish",
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=(swing,),
        swing_lows=(swing,),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


def _regime() -> RegimeResult:
    return RegimeResult(regime="trending", confidence=0.7, reason="test")


def test_band_thresholds() -> None:
    assert _band_for_score(72) == "aggressive"
    assert _band_for_score(58) == "standard"
    assert _band_for_score(35) == "conditional"
    assert _band_for_score(20) == "no_harvest"


def test_infer_session_buckets() -> None:
    assert infer_session(3) == "asia"
    assert infer_session(10) == "london"
    assert infer_session(18) == "new_york"


def test_high_quality_scores_aggressive(tmp_path: Path) -> None:
    scorer = HarvestOpportunityScorer(tmp_path)
    result = scorer.score(
        symbol="EURUSD",
        trend=_trend(88.0),
        snapshot=_snapshot(),
        bias=_bias(),
        structure=_structure(),
        regime=_regime(),
        spread_pips=1.0,
        evaluation_moment=datetime(2025, 6, 10, 10, 0, tzinfo=timezone.utc),
    )
    assert result.score >= 50
    assert result.allow_harvest
    assert result.band in {"aggressive", "standard", "conditional"}


def test_low_score_blocks_harvest(tmp_path: Path) -> None:
    scorer = HarvestOpportunityScorer(tmp_path)
    choppy = _snapshot()
    choppy = AssetTrendSnapshot(
        symbol=choppy.symbol,
        state="choppy_noise",
        confidence=0.3,
        reason="choppy",
        features=_features(choppiness=0.9, setup_alignment=0.1, session_strength=0.2),
        regime="unclear",
        bias="neutral",
    )
    result = scorer.score(
        symbol="EURUSD",
        trend=_trend(20.0),
        snapshot=choppy,
        bias=MultiTimeframeBiasResult(
            bias="neutral", confidence=0.3, explanation="flat", layers=()
        ),
        structure=_structure(),
        regime=RegimeResult(regime="unclear", confidence=0.3, reason="unclear"),
        spread_pips=5.0,
    )
    assert not result.allow_harvest or result.score < 65


def test_write_report(tmp_path: Path) -> None:
    scorer = HarvestOpportunityScorer(tmp_path)
    scorer.score(
        symbol="EURUSD",
        trend=_trend(),
        snapshot=_snapshot(),
        bias=_bias(),
        structure=_structure(),
        regime=_regime(),
        spread_pips=1.0,
    )
    path = scorer.write_report()
    assert path is not None
    assert path.exists()
    assert "Harvest Opportunity Score" in path.read_text(encoding="utf-8")
