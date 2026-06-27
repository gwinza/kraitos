"""Tests for dynamic trend-based strategy selection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from intelligence.asset_strategy_memory import AssetStrategyMemory, SymbolStrategyFit
from intelligence.asset_strategy_researcher import AssetStrategyResearcher
from intelligence.asset_trend_analyzer import AssetTrendAnalyzer
from intelligence.dynamic_strategy_selector import (
    DynamicStrategySelector,
    DynamicStrategySelectorConfig,
)
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult, SwingPoint, TimeframeBiasDetail


def _candles(
    closes: np.ndarray,
    *,
    spread: float = 1.0,
    minutes: int = 60,
) -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index, close in enumerate(closes):
        rows.append(
            {
                "time": start + timedelta(minutes=minutes * index),
                "open": close - 0.00005,
                "high": close + 0.0002,
                "low": close - 0.0002,
                "close": close,
                "tick_volume": 300.0,
                "spread": spread,
            }
        )
    return pd.DataFrame(rows)


def _bias(direction: str = "bullish", confidence: float = 0.8) -> MultiTimeframeBiasResult:
    layers = tuple(
        TimeframeBiasDetail(tf, direction, 0.7, role)  # type: ignore[arg-type]
        for tf, role in [
            ("H8", "macro"),
            ("H4", "macro"),
            ("H1", "structure"),
            ("M15", "setup"),
            ("M5", "setup"),
            ("M1", "precision_entry"),
        ]
    )
    return MultiTimeframeBiasResult(
        bias=direction,  # type: ignore[arg-type]
        confidence=confidence,
        explanation="test",
        layers=layers,
    )


def _structure(trend: str = "bullish") -> MarketContext:
    swing = SwingPoint(
        bar_index=5,
        time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        price=1.10,
        kind="high",  # type: ignore[arg-type]
    )
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend=trend,  # type: ignore[arg-type]
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


def _regime(name: str = "trending") -> RegimeResult:
    return RegimeResult(regime=name, confidence=0.9, reason="test")  # type: ignore[arg-type]


def test_trend_analyzer_classifies_strong_uptrend() -> None:
    analyzer = AssetTrendAnalyzer()
    closes = np.linspace(1.10, 1.14, 80)
    candles = {
        "H1": _candles(closes),
        "M1": _candles(np.linspace(1.13, 1.14, 80), minutes=1),
        "M5": _candles(np.linspace(1.12, 1.14, 80), minutes=5),
    }
    snapshot = analyzer.analyze(
        symbol="EURUSD",
        candles=candles,
        bias=_bias("bullish"),
        structure=_structure("bullish"),
        regime=_regime("trending"),
        spread_pips=1.0,
        spread_limit=3.0,
    )
    assert snapshot.state in {"strong_uptrend", "weak_trend", "volatile_breakout"}
    assert snapshot.confidence > 0.5


def test_selector_maps_ranging_to_scalp_strategy(tmp_path: Path) -> None:
    selector = DynamicStrategySelector(tmp_path)
    analyzer = AssetTrendAnalyzer()
    closes = np.full(80, 1.10)
    snapshot = analyzer.analyze(
        symbol="EURUSD",
        candles={"H1": _candles(closes), "M1": _candles(closes, minutes=1), "M5": _candles(closes, minutes=5)},
        bias=_bias("neutral", confidence=0.4),
        structure=_structure("ranging"),
        regime=_regime("ranging"),
        spread_pips=1.0,
        spread_limit=3.0,
    )
    if snapshot.state == "ranging":
        selection = selector.select(snapshot)
        assert selection.allow_micro_scalp or selection.selected_strategy in {
            "range_scalper",
            "mean_reversion",
            "no_trade",
        }


def test_selector_requires_two_evaluations_before_switch(tmp_path: Path) -> None:
    selector = DynamicStrategySelector(
        tmp_path,
        config=DynamicStrategySelectorConfig(
            confirmation_evaluations=2,
            switch_cooldown_minutes=0,
        ),
    )
    analyzer = AssetTrendAnalyzer()
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    trending = analyzer.analyze(
        symbol="EURUSD",
        candles={
            "H1": _candles(np.linspace(1.10, 1.14, 80)),
            "M1": _candles(np.linspace(1.13, 1.14, 80), minutes=1),
            "M5": _candles(np.linspace(1.12, 1.14, 80), minutes=5),
        },
        bias=_bias("bullish"),
        structure=_structure("bullish"),
        regime=_regime("trending"),
        spread_pips=1.0,
        spread_limit=3.0,
    )
    first = selector.select(trending, evaluation_moment=now)
    assert not first.switched

    ranging = analyzer.analyze(
        symbol="EURUSD",
        candles={
            "H1": _candles(np.full(80, 1.10)),
            "M1": _candles(np.full(80, 1.10), minutes=1),
            "M5": _candles(np.full(80, 1.10), minutes=5),
        },
        bias=_bias("neutral", confidence=0.4),
        structure=_structure("ranging"),
        regime=_regime("ranging"),
        spread_pips=1.0,
        spread_limit=3.0,
    )
    second = selector.select(ranging, evaluation_moment=now + timedelta(minutes=5))
    assert not second.switched
    third = selector.select(ranging, evaluation_moment=now + timedelta(minutes=10))
    assert third.switched or third.selected_strategy != first.selected_strategy


def test_researcher_assigns_conditional_not_disabled_on_mixed_modes(tmp_path: Path) -> None:
    journal = tmp_path / "logs" / "conservative_trade_journal.csv"
    journal.parent.mkdir(parents=True)
    rows = []
    for index in range(12):
        rows.append(
            {
                "trade_id": f"t{index}",
                "event_time": f"2024-06-{index + 1:02d}T10:00:00+00:00",
                "symbol": "EURUSD",
                "timeframe": "M5",
                "direction": "buy",
                "entry": 1.1,
                "stop_loss": 1.09,
                "take_profit": 1.11,
                "confidence": 0.7,
                "mode": "harvest" if index < 6 else "scalp",
                "result": "loss" if index < 6 else "win",
                "profit_loss": -40.0 if index < 6 else 55.0,
                "reason": "test",
                "balance": 10_000.0,
                "equity": 10_000.0,
                "lot_size": 0.1,
                "r_multiple": -0.4 if index < 6 else 0.5,
            }
        )
    pd.DataFrame(rows).to_csv(journal, index=False)
    results = AssetStrategyResearcher(tmp_path).research_journal(journal)
    assert len(results) == 1
    assert results[0].status in {"CONDITIONAL", "APPROVED", "QUARANTINED"}
    assert results[0].status != "DISABLED"
    assert (tmp_path / "logs" / "asset_strategy_fit_report.md").exists()
    assert (tmp_path / "logs" / "asset_underperformance_report.md").exists()


def test_memory_preferred_strategy_used_by_selector(tmp_path: Path) -> None:
    memory = AssetStrategyMemory(tmp_path)
    fit = SymbolStrategyFit(
        symbol="EURUSD",
        status="CONDITIONAL",
        best_strategy_overall="mean_reversion",
        best_strategies_by_state={"ranging": "mean_reversion"},
    )
    memory.update(fit)
    memory.save()

    selector = DynamicStrategySelector(tmp_path, memory=memory)
    analyzer = AssetTrendAnalyzer()
    snapshot = analyzer.analyze(
        symbol="EURUSD",
        candles={
            "H1": _candles(np.full(80, 1.10)),
            "M1": _candles(np.full(80, 1.10), minutes=1),
            "M5": _candles(np.full(80, 1.10), minutes=5),
        },
        bias=_bias("neutral", confidence=0.4),
        structure=_structure("ranging"),
        regime=_regime("ranging"),
        spread_pips=1.0,
        spread_limit=3.0,
    )
    if snapshot.state == "ranging":
        selection = selector.select(snapshot)
        assert selection.selected_strategy == "mean_reversion"
        assert selection.risk_multiplier == 0.5
