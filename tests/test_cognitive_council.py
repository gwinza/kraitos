"""Tests for Kraitos V3 Cognitive Council Architecture."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.offline

from council.chief_intelligence_officer import ChiefIntelligenceOfficer
from council.cognitive_brain import CognitiveBrain
from council.cognitive_bus import CognitiveBus
from council.cognitive_context import MarketCognitiveContext
from council.cognitive_learning import CognitiveLearningLoop
from council.cognitive_models import CouncilObservation
from council.specialists import (
    ALL_SPECIALIST_COUNCILS,
    ExecutionCouncil,
    RiskCouncil,
    StoryCouncil,
    TrendCouncil,
)
from strategies.models import (
    MarketContext,
    MultiTimeframeBiasResult,
    RegimeResult,
    SwingPoint,
    TimeframeBiasDetail,
)
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


def test_all_twelve_specialist_councils_present():
    names = {council.name for council in ALL_SPECIALIST_COUNCILS}
    expected = {
        "story", "trend", "structure", "liquidity", "volume", "volatility",
        "order_flow", "session", "psychology", "memory", "risk", "execution",
    }
    assert names == expected


def test_cognitive_bus_produces_deliberation_messages():
    observations = (
        CouncilObservation(
            council="trend",
            headline="I remain bullish.",
            reasoning="MTF bias bullish",
            direction="bullish",
            confidence=72.0,
            success_probability=0.68,
        ),
        CouncilObservation(
            council="liquidity",
            headline="A stop hunt has just completed below support.",
            reasoning="Sweep detected",
            direction="bullish",
            confidence=68.0,
            success_probability=0.65,
        ),
        CouncilObservation(
            council="volume",
            headline="Volume is weak.",
            reasoning="Participation thin",
            direction="neutral",
            confidence=42.0,
            success_probability=0.40,
        ),
    )
    messages = CognitiveBus().deliberate(observations, rounds=2)
    assert len(messages) >= 6
    assert any("stop hunt" in m.message.lower() or "volume" in m.message.lower() for m in messages)


def test_cio_maps_confidence_to_allocation_tiers():
    context = MarketCognitiveContext.from_candidate(
        _candidate(),
        evaluation_moment=datetime(2025, 1, 14, 10, tzinfo=timezone.utc),
        session_label="london",
    )
    observations = tuple(c.analyze(context) for c in (StoryCouncil(), TrendCouncil(), ExecutionCouncil()))
    high_conf = tuple(
        replace(o, confidence=96.0, success_probability=0.88) for o in observations
    )
    decision = ChiefIntelligenceOfficer().reason(context, high_conf, ())
    assert decision.execution.mode == "full"
    assert decision.execution.allocation_multiplier == 1.0

    low_conf = tuple(replace(o, confidence=55.0, success_probability=0.45) for o in observations)
    low_decision = ChiefIntelligenceOfficer().reason(context, low_conf, ())
    assert low_decision.execution.mode in {"observe", "wait"}
    assert low_decision.execution.allocation_multiplier <= 0.12


def test_risk_council_hard_veto_on_wide_spread():
    context = MarketCognitiveContext.from_candidate(
        _candidate(spread_pips=5.0, spread_limit=2.0),
        session_label="london",
    )
    risk_obs = RiskCouncil().analyze(context)
    decision = ChiefIntelligenceOfficer().reason(context, (risk_obs,), ())
    assert decision.hard_vetoes
    assert not decision.can_trade


def test_cognitive_brain_deliberates_on_candidate():
    brain = CognitiveBrain(None)
    decision = brain.deliberate(
        _candidate(),
        evaluation_moment=datetime(2025, 1, 14, 10, tzinfo=timezone.utc),
    )
    assert decision.symbol == "EURUSD"
    assert len(decision.council_observations) == 12
    assert decision.thesis.market_understanding.what_is_happening
    assert decision.summary.startswith("CIO:")


def test_cognitive_report_writer(tmp_path):
    from council.cognitive_reports import CognitiveReportWriter

    brain = CognitiveBrain(tmp_path)
    decision = brain.deliberate(
        _candidate(),
        evaluation_moment=datetime(2025, 1, 14, 10, tzinfo=timezone.utc),
    )
    writer = CognitiveReportWriter(tmp_path)
    writer.record("EURUSD", decision)
    path = writer.write_report()
    assert path is not None
    content = path.read_text(encoding="utf-8")
    assert "Cognitive Council Report" in content
    assert "EURUSD" in content
    assert "CIO summary" in content


def test_cio_decision_roundtrip_snapshot():
    from council.cognitive_models import CIODecision

    brain = CognitiveBrain(None)
    original = brain.deliberate(_candidate())
    import json

    snapshot = json.dumps(original.to_dict())
    restored = CIODecision.from_snapshot_json(snapshot, symbol="EURUSD")
    assert restored is not None
    assert restored.symbol == "EURUSD"
    assert restored.thesis.confidence == pytest.approx(original.thesis.confidence, rel=0.01)


def test_cognitive_learning_updates_memory(tmp_path):
    from council.council_memory import CouncilMemory

    memory = CouncilMemory(tmp_path)
    loop = CognitiveLearningLoop(memory)
    brain = CognitiveBrain(tmp_path)
    candidate = _candidate()
    decision = brain.deliberate(candidate)
    review = loop.review_trade(
        decision=decision,
        won=False,
        r_multiple=-1.0,
        side="sell",
    )
    assert review is not None
    assert review.symbol == "EURUSD"
    assert (tmp_path / "logs" / "council_memory.json").exists()
