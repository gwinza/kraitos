"""Tests for Trader Memory Engine — remember, inform, never suppress."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from intelligence.evidence_synthesis_engine import EvidenceSynthesisEngine
from intelligence.indicator_interpretation_engine import FORBIDDEN_OUTPUT
from intelligence.trader_memory_engine import (
    TRADER_MEMORY_DNA,
    TraderMemoryEngine,
)


def _psych(dominant: str = "confidence") -> dict:
    return {
        "dominant_emotion": dominant,
        "conviction_level": "moderate",
        "participation_quality": "mixed",
        "confidence_shift": "stable",
        "emotional_extremes": (dominant,),
    }


def _record(
    engine: TraderMemoryEngine,
    *,
    trade_id: str,
    symbol: str = "EURUSD",
    story: str,
    outcome: str,
    r: float,
    emotion: str = "confidence",
    macro: str = "bullish_campaign",
) -> None:
    engine.record_trade(
        trade_id=trade_id,
        symbol=symbol,
        evidence_summary="Trend acceleration with volume sponsorship",
        psychological_state=_psych(emotion),
        story_explanation=story,
        forecast="Continuation after pullback",
        outcome=outcome,
        evolution_path=(
            f"novel:{macro}",
            "chapter:continuation",
            "paragraph:buyers_defending",
            "evolution:continuation_likely",
        ),
        r_multiple=r,
        pips=r * 10,
        macro_story=macro,
        dominant_emotion=emotion,
    )


def test_dna_exported():
    assert "Experienced traders remember" in TRADER_MEMORY_DNA
    assert "never suppresses" in TRADER_MEMORY_DNA
    assert "informs interpretation" in TRADER_MEMORY_DNA


def test_record_trade_stores_all_fields(tmp_path: Path):
    engine = TraderMemoryEngine(tmp_path)
    record = engine.record_trade(
        trade_id="t-001",
        symbol="EURUSD",
        evidence_summary="Structure bullish, momentum rising",
        psychological_state=_psych("greed"),
        story_explanation="Bullish campaign continuation on H1",
        forecast="Pullback then resume higher",
        outcome="win",
        evolution_path=("novel:bullish_campaign", "chapter:continuation"),
        r_multiple=1.2,
        pips=12.0,
        macro_story="bullish_campaign",
        dominant_emotion="greed",
    )
    assert record.trade_id == "t-001"
    assert record.symbol == "EURUSD"
    assert record.evidence_summary
    assert record.psychological_state["dominant_emotion"] == "greed"
    assert record.story_explanation
    assert record.forecast
    assert record.outcome == "win"
    assert len(record.evolution_path) == 2
    assert record.succeeded is True


def test_persistence_roundtrip(tmp_path: Path):
    engine = TraderMemoryEngine(tmp_path)
    _record(
        engine,
        trade_id="t-persist",
        story="Trend continuation with institutional sponsorship",
        outcome="win",
        r=0.8,
    )
    reloaded = TraderMemoryEngine(tmp_path)
    assert len(reloaded._records) == 1
    assert reloaded._records[0].trade_id == "t-persist"
    data = json.loads((tmp_path / "logs" / "trader_memory.json").read_text(encoding="utf-8"))
    assert len(data["trades"]) == 1


def test_recall_finds_similar_symbol_stories(tmp_path: Path):
    engine = TraderMemoryEngine(tmp_path)
    _record(
        engine,
        trade_id="t-win",
        story="Bullish campaign continuation after H1 pullback",
        outcome="win",
        r=1.0,
    )
    _record(
        engine,
        trade_id="t-loss",
        story="Bullish campaign exhaustion at resistance",
        outcome="loss",
        r=-0.7,
        emotion="exhaustion",
    )
    insight = engine.recall(
        symbol="EURUSD",
        story_explanation="Bullish campaign continuation developing on H1",
        psychological_state=_psych("confidence"),
        evolution_path=("novel:bullish_campaign", "chapter:continuation"),
        macro_story="bullish_campaign",
    )
    assert insight.similar_count >= 1
    assert insight.interpretation_contribution
    assert "informs" in insight.interpretation_contribution.lower()


def test_success_and_failure_narratives_tracked(tmp_path: Path):
    engine = TraderMemoryEngine(tmp_path)
    _record(engine, trade_id="w1", story="London pullback harvest continuation", outcome="win", r=0.9)
    _record(engine, trade_id="w2", story="London pullback harvest continuation repeat", outcome="win", r=0.6)
    _record(engine, trade_id="l1", story="London pullback harvest failed at liquidity", outcome="loss", r=-1.0)
    insight = engine.recall(
        symbol="EURUSD",
        story_explanation="London pullback harvest setup forming",
        psychological_state=_psych(),
        macro_story="bullish_campaign",
    )
    assert insight.success_rate > 0.0
    assert insight.failure_rate > 0.0
    assert insight.narrative_success_notes or insight.narrative_failure_notes


def test_no_forbidden_suppression_language(tmp_path: Path):
    engine = TraderMemoryEngine(tmp_path)
    _record(engine, trade_id="t1", story="Trend story", outcome="win", r=0.5)
    insight = engine.recall(
        symbol="EURUSD",
        story_explanation="Similar trend story",
        psychological_state=_psych(),
    )
    blob = " ".join([
        insight.interpretation_contribution,
        insight.asset_behaviour_summary,
        *insight.opportunity_expansion,
    ]).lower()
    for word in FORBIDDEN_OUTPUT:
        assert word not in blob.split(), f"Forbidden word '{word}' in recall output"


def test_enrich_informs_not_blocks(tmp_path: Path):
    engine = TraderMemoryEngine(tmp_path)
    _record(engine, trade_id="t1", story="Compression breakout attempt", outcome="loss", r=-0.5)
    insight = engine.recall(
        symbol="GBPUSD",
        story_explanation="Fresh compression breakout — no history",
        psychological_state=_psych("hesitation"),
    )
    assert insight.similar_count == 0
    assert "fresh interpretation" in insight.interpretation_contribution.lower()
    assert insight.opportunity_expansion


def test_asset_history_summary(tmp_path: Path):
    engine = TraderMemoryEngine(tmp_path)
    _record(engine, trade_id="a1", story="EUR trend", outcome="win", r=1.0)
    _record(engine, trade_id="a2", story="EUR pullback", outcome="loss", r=-0.5)
    summary = engine.asset_history_summary("EURUSD")
    assert "EURUSD" in summary
    assert "remembered trades" in summary


def test_integration_feeds_evidence_without_blocking(tmp_path: Path):
    engine = TraderMemoryEngine(tmp_path)
    _record(
        engine,
        trade_id="ev1",
        story="Evidence synthesis trending continuation",
        outcome="win",
        r=0.7,
    )
    insight = engine.recall(
        symbol="EURUSD",
        story_explanation="Evidence synthesis trending continuation on H1",
        psychological_state=_psych(),
        macro_story="bullish_campaign",
    )
    pieces = insight.to_evidence_pieces()
    assert pieces
    assert all(p.category == "trader_memory" for p in pieces)

    import numpy as np
    import pandas as pd

    from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult, SwingPoint

    closes = [1.10 + i * 0.0002 for i in range(50)]
    candles = {
        tf: pd.DataFrame({
            "time": pd.date_range("2024-01-01", periods=50, freq=f"{m}min", tz="UTC"),
            "open": [c - 0.0001 for c in closes],
            "high": [c + 0.0008 for c in closes],
            "low": [c - 0.0008 for c in closes],
            "close": closes,
            "tick_volume": np.linspace(100, 200, 50),
            "spread": [1.0] * 50,
        })
        for tf, m in {"H8": 480, "H4": 240, "H1": 60, "M15": 15, "M5": 5, "M1": 1}.items()
    }
    structure = MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend="bullish",
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=(SwingPoint(5, None, 1.105, "high"),),
        swing_lows=(SwingPoint(8, None, 1.102, "low"),),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )
    bias = MultiTimeframeBiasResult("bullish", 0.75, "test", ())
    regime = RegimeResult("trending", 0.8, "test")

    synth = EvidenceSynthesisEngine(tmp_path)
    summary = synth.synthesise(
        "EURUSD",
        candles,
        structure=structure,
        bias=bias,
        regime=regime,
        trader_memory_recall=insight,
    )
    assert summary.story_clear or summary.unclear_reason in {"insufficient", "incoherent", "random", ""}


def test_update_outcome(tmp_path: Path):
    engine = TraderMemoryEngine(tmp_path)
    engine.record_trade(
        trade_id="pending-1",
        symbol="EURUSD",
        evidence_summary="Setup forming",
        psychological_state=_psych(),
        story_explanation="Pending story",
        forecast="Await move",
        outcome="pending",
        evolution_path=("novel:compression",),
    )
    updated = engine.update_outcome("pending-1", outcome="win", r_multiple=0.5)
    assert updated is not None
    assert updated.succeeded is True


def test_reports_written(tmp_path: Path):
    engine = TraderMemoryEngine(tmp_path)
    _record(engine, trade_id="r1", story="Report test narrative success", outcome="win", r=0.4)
    _record(engine, trade_id="r2", story="Report test narrative failure", outcome="loss", r=-0.3)
    paths = engine.write_all_reports()
    assert paths[0] is not None and paths[0].exists()
    assert paths[1] is not None and paths[1].exists()
