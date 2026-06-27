"""Tests for Kraitos V4 Market Storyteller / Picture Theory architecture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from council.cognitive_models import CouncilObservation
from intelligence.narrator_engine import NarratorEngine
from intelligence.picture_fusion_engine import PictureFusionEngine
from intelligence.picture_models import (
    DepartmentContribution,
    LiveMarketStory,
    MarketPicture,
)
from intelligence.picture_reports import PictureTheoryReportWriter, storyteller_journal_fields
from intelligence.strategy_playbook import PROFESSIONAL_STRATEGY_PLAYBOOK
from intelligence.strategy_selection_engine import StrategySelectionEngine
from learning.picture_review import PictureReviewEngine
from strategies.models import RegimeResult
from tests.test_entry_engine import _bias, _structure


def _candidate(**kwargs):
    from brains.models import TradeCandidate

    candidate = TradeCandidate(
        symbol=kwargs.get("symbol", "EURUSD"),
        trace_id=kwargs.get("trace_id", "test-trace"),
        bid=kwargs.get("bid", 1.1000),
        ask=kwargs.get("ask", 1.1002),
        spread_pips=kwargs.get("spread_pips", 1.5),
        spread_limit=kwargs.get("spread_limit", 3.0),
    )
    candidate.bias = kwargs.get("bias", _bias("bearish"))
    candidate.structure = kwargs.get("structure", _structure("bearish"))
    candidate.regime = kwargs.get(
        "regime",
        RegimeResult(regime="trending", confidence=0.7, reason="ok"),  # type: ignore[arg-type]
    )
    candidate.pair_allowed = kwargs.get("pair_allowed", True)
    candidate.news_allowed = kwargs.get("news_allowed", True)
    return candidate


def _departments_bullish_sweep() -> tuple[DepartmentContribution, ...]:
    return (
        DepartmentContribution(
            department="trend",
            observation="Higher timeframe remains bullish with momentum building",
            evidence=("MTF bias aligned bullish",),
            confidence=78.0,
        ),
        DepartmentContribution(
            department="structure",
            observation="Price reclaimed support after liquidity sweep below",
            evidence=("Sweep and reclaim pattern",),
            confidence=72.0,
        ),
        DepartmentContribution(
            department="liquidity",
            observation="Stop hunt completed below support — retail shorts likely trapped",
            evidence=("Equal lows swept",),
            confidence=80.0,
        ),
        DepartmentContribution(
            department="volatility",
            observation="Volatility expanding after compression",
            evidence=("ATR rising from base",),
            confidence=65.0,
        ),
    )


def test_professional_strategy_playbook_has_eighteen_strategies():
    assert len(PROFESSIONAL_STRATEGY_PLAYBOOK) >= 16
    ids = {item.strategy_id for item in PROFESSIONAL_STRATEGY_PLAYBOOK}
    assert "liquidity_sweep_reversal" in ids
    assert "trend_continuation" in ids
    assert "wyckoff_accumulation" in ids


def test_picture_fusion_builds_coherent_bullish_picture():
    fusion = PictureFusionEngine()
    picture = fusion.fuse(
        symbol="EURUSD",
        departments=_departments_bullish_sweep(),
        regime_label="trending",
    )
    assert picture.dominant_side == "bullish"
    assert picture.clarity in {"clear", "incomplete"}
    assert picture.confidence >= 50
    assert picture.key_evidence
    assert not picture.professional_thesis_supported or picture.coherent_story


def test_picture_fusion_detects_trend_structure_contradiction():
    fusion = PictureFusionEngine()
    departments = (
        DepartmentContribution(
            department="trend",
            observation="Bearish momentum dominates",
            confidence=70.0,
        ),
        DepartmentContribution(
            department="structure",
            observation="Bullish higher-low framework intact",
            confidence=68.0,
        ),
    )
    picture = fusion.fuse(symbol="GBPUSD", departments=departments, regime_label="transitional")
    assert any("mismatch" in item for item in picture.contradictions)


def test_narrator_writes_full_market_story():
    fusion = PictureFusionEngine()
    departments = _departments_bullish_sweep()
    picture = fusion.fuse(symbol="EURUSD", departments=departments, regime_label="trending")
    story = LiveMarketStory(
        symbol="EURUSD",
        what_is_happening="Price swept liquidity below support and reclaimed",
        why_it_is_happening="Institutional accumulation after stop hunt",
        who_is_in_control="Bulls after reclaim",
        who_is_trapped="Retail shorts below sweep",
        liquidity_location="Below prior session low",
        market_objective="Continuation higher",
        next_likely_chapter="Expansion toward prior high",
        narrative="Bullish sweep and reclaim narrative",
        confidence=75.0,
    )
    narration = NarratorEngine().narrate(story=story, picture=picture, departments=departments)
    assert "The market is currently" in narration.opening
    assert "Confidence is" in narration.confidence_statement
    assert "invalidated" in narration.invalidation.lower()
    assert len(narration.full_narration) > 100


def test_strategy_selection_ranks_liquidity_sweep_on_sweep_narrative():
    fusion = PictureFusionEngine()
    departments = _departments_bullish_sweep()
    picture = fusion.fuse(symbol="EURUSD", departments=departments, regime_label="trending")
    story = LiveMarketStory(
        symbol="EURUSD",
        what_is_happening="Liquidity sweep below support with reclaim",
        why_it_is_happening="Stop hunt",
        who_is_in_control="Bulls",
        who_is_trapped="Shorts",
        liquidity_location="Below support",
        market_objective="Continuation",
        next_likely_chapter="Break higher",
        narrative="Liquidity sweep reversal after compression",
        confidence=70.0,
    )
    rankings = StrategySelectionEngine().rank(picture=picture, story=story)
    assert len(rankings) >= 10
    top_ids = {item.strategy_id for item in rankings[:3]}
    assert top_ids & {"liquidity_sweep_reversal", "liquidity_sweep_continuation", "breakout"}


def test_market_storyteller_full_cycle(tmp_path: Path):
    from intelligence.market_storyteller_engine import MarketStorytellerEngine

    engine = MarketStorytellerEngine(tmp_path)
    candidate = _candidate()
    decision = engine.evaluate(candidate)
    assert decision.symbol == "EURUSD"
    assert decision.story.narrative
    assert decision.picture.departments
    assert decision.narration.full_narration
    assert decision.strategy_rankings
    assert decision.thesis.selected_strategy != ""
    assert decision.participation in {"trade", "wait", "probe", "scale_in", "stand_aside"}


def test_storyteller_reuses_cognitive_decision(tmp_path: Path):
    from council.cognitive_brain import CognitiveBrain
    from intelligence.market_storyteller_engine import MarketStorytellerEngine

    candidate = _candidate()
    cognitive = CognitiveBrain(tmp_path).deliberate(candidate)
    engine = MarketStorytellerEngine(tmp_path)
    decision = engine.evaluate(candidate, cognitive=cognitive)
    assert len(decision.picture.departments) >= len(cognitive.council_observations)


def test_storyteller_journal_fields_and_snapshot_roundtrip(tmp_path: Path):
    from intelligence.market_storyteller_engine import MarketStorytellerEngine

    decision = MarketStorytellerEngine(tmp_path).evaluate(_candidate())
    fields = storyteller_journal_fields(decision)
    assert fields["picture_clarity"]
    assert fields["selected_strategy"]
    assert fields["storyteller_snapshot"]

    restored = PictureReviewEngine.decision_from_snapshot(fields["storyteller_snapshot"])
    assert restored is not None
    assert restored.symbol == decision.symbol
    assert restored.thesis.selected_strategy == decision.thesis.selected_strategy


def test_picture_theory_report_writer(tmp_path: Path):
    from intelligence.market_storyteller_engine import MarketStorytellerEngine

    engine = MarketStorytellerEngine(tmp_path)
    decision = engine.evaluate(_candidate(symbol="EURUSD"))
    writer = PictureTheoryReportWriter(tmp_path)
    writer.record("EURUSD", decision)
    path = writer.write_report()
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "Market Storyteller Report" in text
    assert "EURUSD" in text
    assert "Strategy ranking" in text


def test_picture_review_after_trade(tmp_path: Path):
    from intelligence.market_storyteller_engine import MarketStorytellerEngine

    decision = MarketStorytellerEngine(tmp_path).evaluate(_candidate())
    outcome = PictureReviewEngine(tmp_path).review_trade(
        decision=decision,
        won=True,
        r_multiple=1.2,
        side="sell",
        exit_reason="take_profit",
    )
    assert outcome is not None
    assert outcome.symbol == "EURUSD"
    review_path = tmp_path / "logs" / "json" / "picture_reviews.jsonl"
    assert review_path.exists()
    row = json.loads(review_path.read_text(encoding="utf-8").strip())
    assert row["outcome"]["symbol"] == "EURUSD"


def test_contribution_from_council_maps_observation():
    obs = CouncilObservation(
        council="trend",
        headline="I remain bullish on higher timeframe structure.",
        reasoning="MTF alignment supports continuation",
        direction="bullish",
        confidence=74.0,
        success_probability=0.7,
        evidence=("Higher highs forming",),
    )
    dept = PictureFusionEngine.contribution_from_council(obs)
    assert dept.department == "trend"
    assert dept.observation == obs.headline
    assert dept.evidence == obs.evidence
