"""Tests for Kraitos V5 Market Mind architecture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from intelligence.market_mind_departments import MacroDepartment, NarratorDepartment
from intelligence.market_mind_engine import MarketMindEngine
from intelligence.market_mind_models import MARKET_MIND_PHILOSOPHY, V5_DEPARTMENTS
from intelligence.market_mind_reports import MarketMindReportWriter, market_mind_journal_fields
from intelligence.market_storyteller_engine import LiveStoryEngine
from intelligence.picture_models import LiveMarketStory, MarketPicture
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


def test_v5_departments_include_macro_and_narrator():
    assert "macro" in V5_DEPARTMENTS
    assert "narrator" in V5_DEPARTMENTS
    assert len(V5_DEPARTMENTS) >= 16


def test_macro_department_contributes_observation():
    dept = MacroDepartment().analyze(_candidate())
    assert dept.department == "macro"
    assert dept.observation
    assert dept.evidence


def test_narrator_department_contributes_story_evidence():
    story = LiveStoryEngine().build(_candidate())
    dept = NarratorDepartment().analyze(story=story)
    assert dept.department == "narrator"
    assert "market is" in dept.observation.lower()
    assert len(dept.evidence) >= 2


def test_market_mind_full_cycle(tmp_path: Path):
    engine = MarketMindEngine(tmp_path)
    decision = engine.evaluate(_candidate())
    assert decision.symbol == "EURUSD"
    assert decision.mind_state in {"coherent", "updating", "conflicted", "forming"}
    assert decision.cognitive is not None
    assert decision.picture.departments
    dept_names = {d.department for d in decision.picture.departments}
    assert "macro" in dept_names
    assert "narrator" in dept_names
    assert decision.narration.full_narration
    assert decision.thesis.selected_strategy != ""


def test_market_mind_as_storyteller_backward_compat(tmp_path: Path):
    decision = MarketMindEngine(tmp_path).evaluate(_candidate())
    legacy = decision.as_storyteller()
    assert legacy.symbol == decision.symbol
    assert legacy.picture.clarity == decision.picture.clarity
    assert legacy.thesis.side == decision.thesis.side


def test_market_mind_journal_and_report(tmp_path: Path):
    decision = MarketMindEngine(tmp_path).evaluate(_candidate())
    fields = market_mind_journal_fields(decision)
    assert fields["mind_state"]
    assert fields["market_mind_snapshot"]
    assert fields["picture_clarity"]

    writer = MarketMindReportWriter(tmp_path)
    writer.record("EURUSD", decision)
    path = writer.write_report()
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "Market Mind Report" in text
    assert MARKET_MIND_PHILOSOPHY[:40] in text
    assert "macro" in text.lower() or "EURUSD" in text


def test_market_mind_snapshot_is_v5_json(tmp_path: Path):
    decision = MarketMindEngine(tmp_path).evaluate(_candidate())
    payload = json.loads(market_mind_journal_fields(decision)["market_mind_snapshot"])
    assert payload["version"] == "v5"
    assert "cognitive" in payload
    assert payload["philosophy"] == MARKET_MIND_PHILOSOPHY
