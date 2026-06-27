"""Live odds provider — The Odds API with offline demo fallback."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sports.models import BookmakerOdds, MatchContext, Sport

# The Odds API sport keys → Kraitos sport + league label
SPORT_MAP: dict[str, tuple[Sport, str]] = {
    "soccer_epl": (Sport.SOCCER, "Premier League"),
    "soccer_spain_la_liga": (Sport.SOCCER, "La Liga"),
    "soccer_germany_bundesliga": (Sport.SOCCER, "Bundesliga"),
    "soccer_italy_serie_a": (Sport.SOCCER, "Serie A"),
    "soccer_france_ligue_one": (Sport.SOCCER, "Ligue 1"),
    "soccer_uefa_champs_league": (Sport.SOCCER, "Champions League"),
    "soccer_efl_champ": (Sport.SOCCER, "EFL Championship"),
    "basketball_nba": (Sport.BASKETBALL, "NBA"),
    "basketball_euroleague": (Sport.BASKETBALL, "Euroleague"),
    "americanfootball_nfl": (Sport.AMERICAN_FOOTBALL, "NFL"),
    "icehockey_nhl": (Sport.ICE_HOCKEY, "NHL"),
    "baseball_mlb": (Sport.BASEBALL, "MLB"),
    "cricket_ipl": (Sport.CRICKET, "IPL"),
    "cricket_big_bash": (Sport.CRICKET, "Big Bash"),
    "rugbyunion_six_nations": (Sport.RUGBY, "Six Nations"),
    "mma_mixed_martial_arts": (Sport.MMA, "UFC/MMA"),
    "tennis_atp_french_open": (Sport.TENNIS, "ATP"),
    "tennis_atp_wimbledon": (Sport.TENNIS, "ATP"),
    "esports_lol": (Sport.ESPORTS, "LoL Esports"),
    "esports_csgo": (Sport.ESPORTS, "CS2 Esports"),
}

DEFAULT_SPORT_KEYS = tuple(SPORT_MAP.keys())


class OddsApiProvider:
    """Fetch live fixtures and odds from The Odds API (https://the-odds-api.com)."""

    BASE_URL = "https://api.the-odds-api.com/v4"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("THE_ODDS_API_KEY") or os.getenv("ODDS_API_KEY") or ""
        self.last_error: str | None = None
        self.requests_remaining: int | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key.strip())

    def fetch_fixtures(
        self,
        *,
        sport_keys: tuple[str, ...] | None = None,
        regions: str = "uk,eu,us,au",
        markets: str = "h2h,totals",
    ) -> list[MatchContext]:
        if not self.enabled:
            self.last_error = "No API key — set THE_ODDS_API_KEY in .env"
            return []

        keys = sport_keys or DEFAULT_SPORT_KEYS
        fixtures: list[MatchContext] = []

        for sport_key in keys:
            try:
                events = self._fetch_sport_odds(sport_key, regions=regions, markets=markets)
                sport, league = SPORT_MAP.get(sport_key, (Sport.SOCCER, sport_key))
                for event in events:
                    ctx = self._event_to_context(event, sport, league, sport_key)
                    if ctx:
                        fixtures.append(ctx)
            except (HTTPError, URLError, json.JSONDecodeError, KeyError) as exc:
                self.last_error = f"{sport_key}: {exc}"
                continue

        return fixtures

    def _fetch_sport_odds(
        self, sport_key: str, *, regions: str, markets: str
    ) -> list[dict[str, Any]]:
        params = urlencode(
            {
                "apiKey": self.api_key,
                "regions": regions,
                "markets": markets,
                "oddsFormat": "decimal",
            }
        )
        url = f"{self.BASE_URL}/sports/{sport_key}/odds?{params}"
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=15) as resp:
            remaining = resp.headers.get("x-requests-remaining")
            if remaining:
                self.requests_remaining = int(remaining)
            return json.loads(resp.read().decode("utf-8"))

    def _event_to_context(
        self,
        event: dict[str, Any],
        sport: Sport,
        league: str,
        sport_key: str,
    ) -> MatchContext | None:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        if not home or not away:
            return None

        commence = event.get("commence_time", "")
        try:
            kickoff = datetime.fromisoformat(commence.replace("Z", "+00:00"))
        except ValueError:
            kickoff = datetime.now(timezone.utc)

        event_id = event.get("id", str(uuid.uuid4())[:8])
        match_id = f"live-{sport_key}-{event_id[:12]}"

        bookmaker_odds = self._parse_bookmakers(event.get("bookmakers", []), home, away)
        if not bookmaker_odds:
            return None

        return MatchContext(
            match_id=match_id,
            sport=sport,
            league=league,
            home_team=home,
            away_team=away,
            kickoff=kickoff,
            trace_id=f"trace-{match_id}",
            bookmaker_odds=tuple(bookmaker_odds),
            context_factors=(f"Live odds via The Odds API ({sport_key})",),
        )

    def _parse_bookmakers(
        self,
        bookmakers: list[dict[str, Any]],
        home: str,
        away: str,
    ) -> list[BookmakerOdds]:
        results: list[BookmakerOdds] = []
        for bk in bookmakers[:12]:
            name = bk.get("title") or bk.get("key", "Unknown")
            home_odds = draw_odds = away_odds = None
            over_odds = under_odds = None
            line = None

            for market in bk.get("markets", []):
                key = market.get("key", "")
                outcomes = market.get("outcomes", [])
                if key == "h2h":
                    for o in outcomes:
                        label = o.get("name", "")
                        price = float(o.get("price", 0))
                        if label == home:
                            home_odds = price
                        elif label == away:
                            away_odds = price
                        elif label.lower() == "draw":
                            draw_odds = price
                elif key == "totals":
                    for o in outcomes:
                        if o.get("name", "").lower() == "over":
                            over_odds = float(o.get("price", 0))
                            line = float(o.get("point", 2.5))
                        elif o.get("name", "").lower() == "under":
                            under_odds = float(o.get("price", 0))

            if home_odds and away_odds:
                results.append(
                    BookmakerOdds(
                        bookmaker=name,
                        home=home_odds,
                        draw=draw_odds,
                        away=away_odds,
                        over=over_odds,
                        under=under_odds,
                        line=line,
                    )
                )
        return results

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "last_error": self.last_error,
            "requests_remaining": self.requests_remaining,
            "supported_sport_keys": list(DEFAULT_SPORT_KEYS),
        }
