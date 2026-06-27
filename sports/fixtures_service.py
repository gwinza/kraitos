"""Match scanner — discovers upcoming events across leagues and sports."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sports.demo_data import build_demo_fixtures
from sports.demo_lower_leagues import build_lower_league_fixtures
from sports.enrichment import enrich_match
from sports.models import MatchContext, Sport
from sports.odds_provider import OddsApiProvider


class FixturesService:
    """Scans upcoming matches — live The Odds API + demo fallback."""

    SUPPORTED_SPORTS = tuple(Sport)

    def __init__(self) -> None:
        use_live = os.getenv("SPORTS_USE_LIVE_ODDS", "true").lower() in ("1", "true", "yes")
        self.odds_provider = OddsApiProvider()
        self._demo: list[MatchContext] = build_demo_fixtures() + build_lower_league_fixtures()
        self._fixtures: list[MatchContext] = []
        self._live_mode = False
        self.refresh(use_live=use_live)

    def refresh(self, *, use_live: bool = True) -> int:
        """Reload fixtures from live API and/or demo data."""
        merged: dict[str, MatchContext] = {f.match_id: f for f in self._demo}

        if use_live and self.odds_provider.enabled:
            live = self.odds_provider.fetch_fixtures()
            for ctx in live:
                enriched = enrich_match(ctx)
                merged[enriched.match_id] = enriched
            self._live_mode = len(live) > 0

        self._fixtures = sorted(merged.values(), key=lambda f: f.kickoff)
        return len(self._fixtures)

    def scan_upcoming(
        self,
        *,
        sport: Sport | None = None,
        league: str | None = None,
        hours_ahead: int = 168,
    ) -> list[MatchContext]:
        now = datetime.now(timezone.utc)
        results: list[MatchContext] = []
        for fixture in self._fixtures:
            delta = (fixture.kickoff - now).total_seconds() / 3600
            if delta < -2 or delta > hours_ahead:
                continue
            if sport and fixture.sport != sport:
                continue
            if league and league.lower() not in fixture.league.lower():
                continue
            results.append(fixture)
        return sorted(results, key=lambda f: f.kickoff)

    def get_match(self, match_id: str) -> MatchContext | None:
        for fixture in self._fixtures:
            if fixture.match_id == match_id:
                return fixture
        return None

    def list_leagues(self) -> list[str]:
        return sorted({f.league for f in self._fixtures})

    def list_sports(self) -> list[str]:
        return sorted({f.sport.value for f in self._fixtures})

    def list_lower_leagues(self) -> list[dict]:
        from sports.lower_leagues import list_lower_leagues

        return list_lower_leagues()

    def scan_lower_league(
        self,
        *,
        tier_min: int = 3,
        tier_max: int = 4,
        hours_ahead: int = 168,
    ) -> list[MatchContext]:
        from sports.lower_leagues import is_target_tier

        return [
            f
            for f in self.scan_upcoming(hours_ahead=hours_ahead)
            if is_target_tier(f.league, tier_min, tier_max)
        ]

    def data_source(self) -> dict:
        return {
            "live_mode": self._live_mode,
            "total_fixtures": len(self._fixtures),
            "demo_fixtures": len(self._demo),
            "odds_api": self.odds_provider.status(),
        }
