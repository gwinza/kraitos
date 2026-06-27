"""Tests for adaptive conviction engine."""

from __future__ import annotations

import pandas as pd
import pytest

from strategies.conviction_engine import ConvictionEngine
from strategies.models import (
    MarketContext,
    MicroScalpSignal,
    MultiTimeframeBiasResult,
    SwingPoint,
    TimeframeBiasDetail,
)


def _bias(*, bullish_h4: bool = True, confidence: float = 0.6) -> MultiTimeframeBiasResult:
    layers = [
        TimeframeBiasDetail("H4", "bullish" if bullish_h4 else "bearish", 0.55, "macro"),
        TimeframeBiasDetail("H8", "bullish", 0.50, "macro"),
    ]
    return MultiTimeframeBiasResult(
        bias="bullish",
        confidence=confidence,
        explanation="test",
        layers=tuple(layers),
    )


def _structure(trend: str = "bullish") -> MarketContext:
    swing = SwingPoint(
        bar_index=1,
        time=pd.Timestamp("2025-01-10", tz="UTC"),
        price=1.10,
        kind="low",
    )
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend=trend,  # type: ignore[arg-type]
        higher_highs=trend == "bullish",
        higher_lows=trend == "bullish",
        lower_highs=trend == "bearish",
        lower_lows=trend == "bearish",
        swing_highs=(swing,),
        swing_lows=(swing,),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )


def _m5_consolidation() -> pd.DataFrame:
    closes = [1.1000 + i * 0.0001 for i in range(20)]
    closes[-3:] = [1.1020, 1.10201, 1.10202]
    rows = []
    for i, close in enumerate(closes):
        rows.append(
            {
                "time": pd.Timestamp("2025-01-10", tz="UTC") + pd.Timedelta(minutes=5 * i),
                "open": close,
                "high": close + 0.00005,
                "low": close - 0.00005,
                "close": close,
                "tick_volume": 100,
                "spread": 1.0,
            }
        )
    return pd.DataFrame(rows)


def test_attack_mode_high_conviction() -> None:
    m5 = _m5_consolidation()
    assessment = ConvictionEngine().evaluate(
        side="buy",
        bias=_bias(),
        structure=_structure(),
        story="Liquidity sweep reclaim",
        story_clear=True,
        opportunity_type="liquidity_sweep",
        opportunity_score=0.85,
        candles={"M5": m5},
        momentum=MicroScalpSignal(action="buy", reason="M1 impulse", target_pips=5.0),
        invalidation_level=1.0980,
        expected_r=1.5,
        structure_quality=0.75,
    )
    assert assessment.conviction_score >= 61
    assert assessment.participation_mode in {"normal", "aggressive", "probe"}
    assert assessment.invalidators
    assert assessment.evidence


def test_uncertain_becomes_probe_not_hard_reject() -> None:
    assessment = ConvictionEngine().evaluate(
        side="buy",
        bias=_bias(bullish_h4=False, confidence=0.3),
        structure=_structure(trend="bearish"),
        story="Unclear chop",
        story_clear=False,
        expected_r=0.8,
        structure_quality=0.65,
    )
    assert assessment.participation_mode in {"probe", "watchlist", "avoid"}
    assert assessment.conviction_score >= 0


def test_attack_timing_allows_immediate_entry() -> None:
    from strategies.conviction_engine import ConvictionAssessment

    m5 = _m5_consolidation()
    assessment = ConvictionAssessment(
        conviction_score=85.0,
        conviction_class="elite",
        participation_mode="aggressive",
        story="Elite sweep",
        invalidators=("H1 swing low breaks",),
        evidence=("H4 aligned",),
        timing_mode="immediate",
    )
    allowed, detail = ConvictionEngine.entry_timing_allowed(
        assessment, side="buy", candles=m5
    )
    assert allowed
    assert "attack" in detail.lower()
