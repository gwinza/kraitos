"""Tests for Opportunity Hunter Council — observers only."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from council.opportunity_hunter_council import (
    CouncilExpansionConfig,
    OpportunityHunterCouncil,
)
from intelligence.market_story_engine import MarketStoryEngine, STORY_TIMEFRAMES
from intelligence.story_forecast_engine import StoryForecastEngine
from strategies.models import (
    MarketContext,
    MultiTimeframeBiasResult,
    RegimeResult,
    StructureEvent,
    SwingPoint,
)


def _candles(closes: list[float], minutes: int = 60) -> pd.DataFrame:
    n = len(closes)
    times = pd.date_range("2024-01-01", periods=n, freq=f"{minutes}min", tz="UTC")
    highs = [c + 0.0005 for c in closes]
    lows = [c - 0.0005 for c in closes]
    return pd.DataFrame({
        "time": times,
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": np.linspace(100, 200, n),
        "spread": [1.0] * n,
    })


def _structure() -> MarketContext:
    swings_h = (SwingPoint(5, None, 1.1050, "high"), SwingPoint(15, None, 1.1080, "high"))
    swings_l = (SwingPoint(8, None, 1.1020, "low"), SwingPoint(18, None, 1.1040, "low"))
    bos = StructureEvent(
        kind="bos_bullish",
        bar_index=18,
        time=None,
        price=1.1080,
        reference_price=1.1050,
        description="Bullish BOS",
    )
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend="bullish",
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=swings_h,
        swing_lows=swings_l,
        structure_events=(bos,),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=bos,
        last_choch=None,
    )


def _bias() -> MultiTimeframeBiasResult:
    return MultiTimeframeBiasResult(
        bias="bullish",
        confidence=0.75,
        explanation="test",
        layers=(),
    )


def _regime() -> RegimeResult:
    return RegimeResult(regime="trending", confidence=0.8, reason="test")


def _build_story_stack(tmp_path: Path):
    closes = [1.10 + i * 0.0002 for i in range(40)]
    candles = {
        tf: _candles(closes, minutes={"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "H8": 480}[tf])
        for tf in STORY_TIMEFRAMES
    }
    structure = _structure()
    story = MarketStoryEngine(tmp_path).build(
        symbol="EURUSD",
        candles=candles,
        structure=structure,
        bias=_bias(),
        regime=_regime(),
        evaluation_moment=datetime(2024, 6, 10, 14, 0, tzinfo=timezone.utc),
    )
    forecast = StoryForecastEngine(tmp_path).forecast(
        symbol="EURUSD",
        market_story=story,
        candles=candles,
        structure=structure,
        bias=_bias(),
        regime=_regime(),
    )
    return story, forecast, candles, structure


def _observe(tmp_path: Path, *, expansion: bool = True):
    story, forecast, candles, structure = _build_story_stack(tmp_path)
    council = OpportunityHunterCouncil(
        tmp_path,
        expansion_config=CouncilExpansionConfig(enabled=expansion),
    )
    consensus = council.observe(
        symbol="EURUSD",
        market_story=story,
        story_forecast=forecast,
        structure=structure,
        bias=_bias(),
        regime=_regime(),
        evaluation_moment=datetime(2024, 6, 10, 14, 0, tzinfo=timezone.utc),
        spread_pips=0.5,
    )
    return consensus, story


def test_council_observe_produces_notes(tmp_path: Path):
    consensus, _ = _observe(tmp_path)
    assert len(consensus.member_opinions) == 6
    assert 0 <= consensus.consensus_confidence <= 100
    assert consensus.consensus_narrative
    assert consensus.observer_only is True
    assert consensus.story_notes


def test_council_does_not_gate_on_votes(tmp_path: Path):
    """Votes are observational — allow follows story clarity, not vote count."""
    consensus, story = _observe(tmp_path)
    if story.story_clear:
        assert consensus.allow_opportunity
    assert consensus.votes_for + consensus.votes_against == 6


def test_observer_notes_include_story(tmp_path: Path):
    consensus, story = _observe(tmp_path)
    assert story.macro_story in consensus.story_notes or "Macro" in consensus.story_notes


def test_debate_alias_calls_observe(tmp_path: Path):
    story, forecast, _, structure = _build_story_stack(tmp_path)
    council = OpportunityHunterCouncil(tmp_path)
    via_debate = council.debate(
        symbol="EURUSD",
        market_story=story,
        story_forecast=forecast,
        structure=structure,
        bias=_bias(),
        regime=_regime(),
        spread_pips=0.5,
    )
    assert via_debate.observer_only is True
    assert len(via_debate.member_opinions) == 6


def test_council_report_writer(tmp_path: Path):
    story, forecast, _, structure = _build_story_stack(tmp_path)
    council = OpportunityHunterCouncil(tmp_path)
    council.observe(
        symbol="EURUSD",
        market_story=story,
        story_forecast=forecast,
        structure=structure,
        bias=_bias(),
        regime=_regime(),
        spread_pips=0.5,
    )
    path = council.maybe_write_reports()
    assert path is not None
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Opportunity Hunter Council" in content
    assert "EURUSD" in content


def test_micro_harvest_is_observational_flag(tmp_path: Path):
    consensus, _ = _observe(tmp_path)
    if consensus.micro_harvest:
        assert consensus.price_action_reason
        assert consensus.volume_reason
