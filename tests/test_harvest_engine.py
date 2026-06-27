"""Tests for the harvest engine."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.offline

from strategies import HarvestContext, HarvestEngine, HarvestEngineError
from strategies.models import (
    MarketContext,
    MultiTimeframeBiasResult,
    RegimeResult,
    StructureEvent,
    SwingPoint,
    TimeframeBiasDetail,
)


def _swing(kind: str, price: float, index: int = 10) -> SwingPoint:
    return SwingPoint(
        bar_index=index,
        time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        price=price,
        kind=kind,  # type: ignore[arg-type]
    )


def _bias(direction: str, confidence: float = 0.75) -> MultiTimeframeBiasResult:
    layers = (
        TimeframeBiasDetail("H8", direction, 0.6, "macro"),  # type: ignore[arg-type]
        TimeframeBiasDetail("H4", direction, 0.6, "macro"),  # type: ignore[arg-type]
        TimeframeBiasDetail("H1", direction, 0.6, "structure"),  # type: ignore[arg-type]
        TimeframeBiasDetail("M15", direction, 0.6, "setup"),  # type: ignore[arg-type]
        TimeframeBiasDetail("M5", direction, 0.6, "setup"),  # type: ignore[arg-type]
        TimeframeBiasDetail("M1", direction, 0.6, "precision_entry"),  # type: ignore[arg-type]
    )
    return MultiTimeframeBiasResult(
        bias=direction,  # type: ignore[arg-type]
        confidence=confidence,
        explanation="test bias",
        layers=layers,
    )


def _structure(
    trend: str = "bullish",
    *,
    bos: StructureEvent | None = None,
) -> MarketContext:
    highs = (_swing("high", 1.11, 8), _swing("high", 1.12, 20))
    lows = (_swing("low", 1.09, 5), _swing("low", 1.10, 15))
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend=trend,  # type: ignore[arg-type]
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=highs,
        swing_lows=lows,
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=bos,
        last_choch=None,
    )


def _regime(name: str = "trending", confidence: float = 0.7) -> RegimeResult:
    return RegimeResult(regime=name, confidence=confidence, reason="test")  # type: ignore[arg-type]


def _context(**kwargs) -> HarvestContext:
    defaults = {
        "symbol": "EURUSD",
        "bias": _bias("bullish"),
        "structure": _structure(),
        "regime": _regime(),
        "current_spread": 1.5,
        "spread_limit": 2.0,
        "in_active_session": True,
        "correlation_support": True,
        "fundamental_support": True,
        "news_risk_active": False,
    }
    defaults.update(kwargs)
    return HarvestContext(**defaults)


def test_blocks_when_mandatory_bias_missing():
    decision = HarvestEngine().evaluate(
        _context(bias=_bias("neutral", confidence=0.8))
    )

    assert decision.allowed is False
    assert decision.mode == "none"
    assert decision.target_pips == 0.0
    assert "directional_bias" in decision.reason


def test_blocks_when_liquidity_insufficient():
    decision = HarvestEngine().evaluate(
        _context(regime=_regime("low_liquidity"))
    )

    assert decision.allowed is False
    assert "sufficient_liquidity" in decision.reason


def test_conditional_harvest_with_two_secondary_conditions():
    bearish_precision = _bias("bullish")
    layers = tuple(
        TimeframeBiasDetail(
            layer.timeframe,
            "bearish" if layer.role == "precision_entry" else layer.bias,
            layer.score,
            layer.role,
        )
        for layer in bearish_precision.layers
    )
    bias = MultiTimeframeBiasResult(
        bias="bullish",
        confidence=0.75,
        explanation="test",
        layers=layers,
    )
    structure = replace(_structure(), higher_highs=False, last_bos=None)

    decision = HarvestEngine().evaluate(
        _context(
            bias=bias,
            structure=structure,
            regime=_regime("volatile"),
            in_active_session=True,
            correlation_support=False,
            fundamental_support=False,
            current_spread=1.5,
        )
    )

    assert decision.allowed is True
    assert decision.mode == "conditional"
    assert 1.0 <= decision.target_pips <= 10.0
    assert "Conditional harvest" in decision.reason


def test_full_harvest_with_three_or_more_secondary_conditions():
    bos = StructureEvent(
        kind="bos_bullish",
        bar_index=30,
        time=datetime(2025, 1, 2, tzinfo=timezone.utc),
        price=1.13,
        reference_price=1.12,
        description="bullish bos",
    )
    decision = HarvestEngine().evaluate(
        _context(
            structure=_structure(bos=bos),
            in_active_session=True,
            correlation_support=True,
            fundamental_support=True,
            current_spread=1.2,
        )
    )

    assert decision.allowed is True
    assert decision.mode == "full"
    assert 5.0 <= decision.target_pips <= 10.0
    assert "Full harvest" in decision.reason


def test_blocks_when_no_secondary_conditions():
    decision = HarvestEngine().evaluate(
        _context(
            bias=_bias("neutral", confidence=0.30),
            structure=replace(
                _structure("neutral"),
                trend="neutral",
                higher_highs=False,
                higher_lows=False,
                lower_highs=False,
                lower_lows=False,
            ),
            regime=_regime("volatile"),
            in_active_session=False,
            correlation_support=False,
            fundamental_support=False,
            current_spread=3.0,
        )
    )

    assert decision.allowed is False
    assert decision.mode == "none"


def test_conditional_harvest_with_one_secondary():
    decision = HarvestEngine().evaluate(
        _context(
            bias=_bias("bearish"),
            structure=replace(
                _structure("bearish"),
                trend="bearish",
                lower_highs=True,
                lower_lows=True,
            ),
            regime=_regime("volatile"),
            in_active_session=False,
            correlation_support=False,
            fundamental_support=False,
            current_spread=3.0,
        )
    )

    assert decision.allowed is True
    assert decision.mode == "conditional"
    assert decision.target_pips <= 5.0


def test_rejects_invalid_spread_limit():
    with pytest.raises(HarvestEngineError, match="spread_limit"):
        HarvestEngine().evaluate(_context(spread_limit=0))
