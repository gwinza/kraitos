"""Tests for Kraitos Sports intelligence pipeline."""

from __future__ import annotations

import pytest

from brains.sports_brain import SportsBrain
from sports.demo_data import build_demo_fixtures
from sports.engines import ArbitrageEngine, ValueBettingEngine
from sports.models import Decision, Sport


@pytest.fixture
def brain():
    return SportsBrain()


def test_scan_finds_fixtures(brain):
    analyses = brain.scan_and_analyze()
    assert len(analyses) >= 5


def test_philosophy(brain):
    assert "finds edges" in brain.PHILOSOPHY.lower()


def test_arbitrage_detected_on_demo():
    fixture = next(f for f in build_demo_fixtures() if f.match_id == "bund-001")
    result = ArbitrageEngine().analyze(fixture)
    assert result.detected is True
    assert result.profit_pct > 0


def test_pass_on_efficient_market(brain):
    analysis = brain.evaluate(next(f for f in build_demo_fixtures() if f.match_id == "lal-001"))
    assert analysis.decision == Decision.PASS


def test_output_format(brain):
    analysis = brain.scan_and_analyze()[0]
    d = analysis.to_dict()
    required = [
        "match", "league", "kickoff_time", "decision", "edge_score",
        "confidence", "reasoning_summary", "team_strength_analysis",
        "multi_agent_council_summary", "red_team_concerns", "philosophy",
    ]
    for key in required:
        assert key in d


def test_value_engine_positive_ev():
    fixture = next(f for f in build_demo_fixtures() if f.match_id == "efl-001")
    engine = ValueBettingEngine()
    results = engine.analyze(fixture, home_prob=0.55, draw_prob=0.25, away_prob=0.20)
    assert len(results) > 0


def test_sports_filter(brain):
    soccer = brain.scan_and_analyze(sport=Sport.SOCCER)
    assert all(a.sport == Sport.SOCCER for a in soccer)


def test_extended_demo_coverage():
    from sports.demo_data import build_demo_fixtures

    fixtures = build_demo_fixtures()
    sports = {f.sport for f in fixtures}
    assert Sport.RUGBY in sports
    assert Sport.ESPORTS in sports
    assert len(fixtures) >= 14

    from sports.demo_lower_leagues import build_lower_league_fixtures

    lower = build_lower_league_fixtures()
    assert len(lower) >= 10


def test_odds_provider_offline():
    from sports.odds_provider import OddsApiProvider

    provider = OddsApiProvider(api_key="")
    assert provider.enabled is False
    assert provider.fetch_fixtures() == []


def test_fixtures_data_source():
    from sports.fixtures_service import FixturesService

    svc = FixturesService()
    src = svc.data_source()
    assert src["total_fixtures"] >= 22
    assert "odds_api" in src


def test_edge_alerts(brain):
    analyses, alerts = brain.scan_with_alerts()
    assert len(analyses) >= 5
    assert isinstance(alerts, list)


def test_lower_league_predictions(brain):
    analyses = brain.scan_lower_leagues(tier_min=3, tier_max=4)
    assert len(analyses) >= 8
    with_prediction = [a for a in analyses if a.prediction]
    assert len(with_prediction) >= 5
    sample = with_prediction[0]
    assert sample.prediction_reasoning
    assert sample.prediction_detail
    assert "reasons" in sample.prediction_detail
    assert sample.is_lower_league is True
    assert sample.league_tier in (3, 4)


def test_lower_league_engine_direct():
    from sports.demo_lower_leagues import build_lower_league_fixtures
    from sports.engines.lower_league_prediction_engine import LowerLeaguePredictionEngine

    ctx = build_lower_league_fixtures()[0]
    engine = LowerLeaguePredictionEngine()
    pred = engine.predict(
        ctx,
        home_prob=0.5,
        draw_prob=0.25,
        away_prob=0.25,
        monte_carlo=None,
        value_bet=None,
        team_strength_text="",
        xg_text="",
        form_text="",
    )
    assert pred is not None
    assert pred.outcome
    assert len(pred.reasons) >= 2
    assert pred.summary


def test_ranking_order(brain):
    analyses = brain.scan_and_analyze()
    edges = [a for a in analyses if a.decision != Decision.PASS]
    passes = [a for a in analyses if a.decision == Decision.PASS]
    if edges and passes:
        assert edges[0].edge_score >= passes[-1].edge_score
