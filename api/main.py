"""FastAPI backend for Kraitos Sports mobile app."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from brains.sports_brain import SportsBrain
from sports.models import Sport

app = FastAPI(
    title="Kraitos Sports API",
    description="Elite AI Sports Intelligence — Kraitos finds edges, not winners.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_brain: SportsBrain | None = None


def get_brain() -> SportsBrain:
    global _brain
    if _brain is None:
        _brain = SportsBrain(project_root=Path(__file__).resolve().parents[1])
    return _brain


@app.get("/")
def root():
    brain = get_brain()
    return {
        "name": "Kraitos Sports",
        "philosophy": SportsBrain.PHILOSOPHY,
        "golden_rule": "Data → Probability → Value → Risk → Decision",
        "human_in_the_loop": True,
        "data_source": brain.fixtures.data_source(),
    }


@app.get("/health")
def health():
    brain = get_brain()
    return {
        "status": "ok",
        "stats": {
            "matches_scanned": brain.stats.matches_scanned,
            "edges_found": brain.stats.edges_found,
            "arbitrage_found": brain.stats.arbitrage_found,
            "passes": brain.stats.passes,
        },
        "data_source": brain.fixtures.data_source(),
    }


@app.post("/refresh")
def refresh_fixtures():
    brain = get_brain()
    count = brain.refresh_fixtures()
    return {"refreshed": count, "data_source": brain.fixtures.data_source()}


@app.get("/odds/status")
def odds_status():
    return get_brain().fixtures.data_source()


@app.get("/leagues/lower")
def list_lower_leagues():
    return {"leagues": get_brain().fixtures.list_lower_leagues()}


@app.get("/analyze/lower-leagues")
def analyze_lower_leagues(
    tier_min: int = Query(default=3, ge=3, le=6),
    tier_max: int = Query(default=4, ge=3, le=6),
):
    """European 3rd/4th tier predictions with full reasoning."""
    brain = get_brain()
    analyses = brain.scan_lower_leagues(tier_min=tier_min, tier_max=tier_max)
    return {
        "philosophy": SportsBrain.PHILOSOPHY,
        "focus": "European lower leagues (3rd & 4th tier)",
        "count": len(analyses),
        "predictions": [a.to_dict() for a in analyses],
    }


@app.get("/sports")
def list_sports():
    return {"sports": get_brain().fixtures.list_sports()}


@app.get("/leagues")
def list_leagues():
    return {"leagues": get_brain().fixtures.list_leagues()}


@app.get("/fixtures")
def scan_fixtures(
    sport: str | None = None,
    league: str | None = None,
    hours_ahead: int = Query(default=168, ge=1, le=720),
):
    brain = get_brain()
    sport_enum = Sport(sport) if sport else None
    fixtures = brain.fixtures.scan_upcoming(
        sport=sport_enum, league=league, hours_ahead=hours_ahead
    )
    return {
        "count": len(fixtures),
        "data_source": brain.fixtures.data_source(),
        "fixtures": [
            {
                "match_id": f.match_id,
                "sport": f.sport.value,
                "league": f.league,
                "home_team": f.home_team,
                "away_team": f.away_team,
                "kickoff": f.kickoff.isoformat(),
            }
            for f in fixtures
        ],
    }


@app.get("/analyze")
def analyze_all(
    sport: str | None = None,
    league: str | None = None,
):
    brain = get_brain()
    sport_enum = Sport(sport) if sport else None
    analyses, alerts = brain.scan_with_alerts(sport=sport_enum, league=league)
    return {
        "philosophy": SportsBrain.PHILOSOPHY,
        "count": len(analyses),
        "new_alerts": [a.to_dict() for a in alerts],
        "opportunities": [a.to_dict() for a in analyses],
    }


@app.get("/alerts")
def get_alerts(
    sport: str | None = None,
    league: str | None = None,
):
    """Return only new/upgraded edge alerts for push notifications."""
    brain = get_brain()
    sport_enum = Sport(sport) if sport else None
    _, alerts = brain.scan_with_alerts(sport=sport_enum, league=league)
    return {
        "count": len(alerts),
        "alerts": [a.to_dict() for a in alerts],
    }


@app.get("/analyze/{match_id}")
def analyze_match(match_id: str):
    brain = get_brain()
    context = brain.fixtures.get_match(match_id)
    if not context:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")
    analysis = brain.evaluate(context)
    return analysis.to_dict()


@app.post("/feedback/{match_id}")
def record_feedback(match_id: str, won: bool = False, missed: bool = False):
    brain = get_brain()
    brain.rl.record_outcome(
        match_id=match_id,
        won=won,
        missed=missed,
        engine_contributions={
            "team_strength": 0.2,
            "xg": 0.3,
            "form": 0.15,
            "market": 0.15,
            "monte_carlo": 0.2,
        },
    )
    return {"status": "recorded", "weights": brain.rl.get_weights().__dict__}
