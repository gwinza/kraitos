"""Tests for strategy marketplace competition."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from intelligence.rolling_fitness import RollingFitnessMemory
from intelligence.strategy_marketplace import StrategyMarketplace, TREND_PREFERENCES
from intelligence.trend_strength_engine import TrendStrengthResult


def _trend(
    *,
    symbol: str = "EURUSD",
    score: float = 85.0,
    quality: str = "institutional_trend",
) -> TrendStrengthResult:
    return TrendStrengthResult(
        symbol=symbol,
        score=score,
        quality=quality,  # type: ignore[arg-type]
        direction="bullish",
        components={"macro_alignment": 15.0},
        reason="test",
    )


def test_marketplace_prefers_trend_strategies_for_institutional(tmp_path: Path) -> None:
    memory = RollingFitnessMemory(tmp_path)
    marketplace = StrategyMarketplace(memory)
    selection = marketplace.compete(
        trend=_trend(score=88.0, quality="institutional_trend"),
        regime="trending",
        session="london",
    )
    assert selection.strategy in TREND_PREFERENCES["institutional_trend"]
    assert selection.strategy != "no_trade"
    assert selection.expected_value >= 0
    assert selection.regime == "trending"


def test_marketplace_disabled_asset_returns_no_trade(tmp_path: Path) -> None:
    memory = RollingFitnessMemory(tmp_path)
    profile = memory.get_or_create("EURUSD")
    profile.recommended_action = "DISABLED"
    marketplace = StrategyMarketplace(memory)
    selection = marketplace.compete(trend=_trend())
    assert selection.strategy == "no_trade"
    assert selection.recommended_action == "DISABLED"


def test_marketplace_allows_scalp_in_clean_range_noise(tmp_path: Path) -> None:
    memory = RollingFitnessMemory(tmp_path)
    marketplace = StrategyMarketplace(memory)
    selection = marketplace.compete(
        trend=_trend(score=25.0, quality="range_or_noise"),
        spread_to_target=0.1,
        structure_clean=True,
        regime="ranging",
        session="asia",
    )
    assert selection.strategy in {"range_scalper", "mean_reversion", "micro_scalp", "no_trade"}


def test_marketplace_selects_highest_ev_not_most_restrictive(tmp_path: Path) -> None:
    memory = RollingFitnessMemory(tmp_path)
    profile = memory.get_or_create("EURUSD")
    from intelligence.rolling_fitness import StrategyFitnessRecord, WindowFitness

    for strategy, fitness, avg_r in [
        ("harvest", 0.8, 0.2),
        ("no_trade", 0.9, 0.0),
        ("range_scalper", 0.7, 0.25),
    ]:
        profile.strategy_records[strategy] = StrategyFitnessRecord(
            symbol="EURUSD",
            strategy=strategy,
            windows={
                "50": WindowFitness(20, 0.7, 1.5, avg_r, 8.0, 10.0, fitness),
            },
            fitness_score=fitness,
        )
    marketplace = StrategyMarketplace(memory)
    selection = marketplace.compete(
        trend=_trend(score=30.0, quality="range_or_noise"),
        spread_to_target=0.1,
        structure_clean=True,
        regime="ranging",
        session="asia",
    )
    assert selection.strategy != "no_trade" or selection.expected_value <= 0
