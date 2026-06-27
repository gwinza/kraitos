export interface BookmakerOdds {
  bookmaker: string;
  home: number;
  draw?: number;
  away: number;
  over?: number;
  under?: number;
  line?: number;
}

export interface LiveFixture {
  matchId: string;
  sport: string;
  league: string;
  homeTeam: string;
  awayTeam: string;
  kickoff: string;
  bookmakerOdds: BookmakerOdds[];
  sportKey: string;
}

const SPORT_MAP: Record<string, { sport: string; league: string }> = {
  soccer_epl: { sport: "soccer", league: "Premier League" },
  soccer_spain_la_liga: { sport: "soccer", league: "La Liga" },
  soccer_germany_bundesliga: { sport: "soccer", league: "Bundesliga" },
  soccer_italy_serie_a: { sport: "soccer", league: "Serie A" },
  soccer_france_ligue_one: { sport: "soccer", league: "Ligue 1" },
  soccer_uefa_champs_league: { sport: "soccer", league: "Champions League" },
  soccer_efl_champ: { sport: "soccer", league: "EFL Championship" },
  basketball_nba: { sport: "basketball", league: "NBA" },
  basketball_euroleague: { sport: "basketball", league: "Euroleague" },
  americanfootball_nfl: { sport: "american_football", league: "NFL" },
  icehockey_nhl: { sport: "ice_hockey", league: "NHL" },
  baseball_mlb: { sport: "baseball", league: "MLB" },
  cricket_ipl: { sport: "cricket", league: "IPL" },
  cricket_big_bash: { sport: "cricket", league: "Big Bash" },
  rugbyunion_six_nations: { sport: "rugby", league: "Six Nations" },
  mma_mixed_martial_arts: { sport: "mma", league: "UFC/MMA" },
  tennis_atp_french_open: { sport: "tennis", league: "ATP" },
  tennis_atp_wimbledon: { sport: "tennis", league: "ATP" },
  esports_lol: { sport: "esports", league: "LoL Esports" },
  esports_csgo: { sport: "esports", league: "CS2 Esports" },
};

const DEFAULT_SPORT_KEYS = Object.keys(SPORT_MAP);

interface OddsApiEvent {
  id: string;
  home_team: string;
  away_team: string;
  commence_time: string;
  bookmakers: Array<{
    title?: string;
    key?: string;
    markets: Array<{
      key: string;
      outcomes: Array<{ name: string; price: number; point?: number }>;
    }>;
  }>;
}

function parseBookmakers(
  bookmakers: OddsApiEvent["bookmakers"],
  home: string,
  away: string
): BookmakerOdds[] {
  const results: BookmakerOdds[] = [];

  for (const book of bookmakers.slice(0, 12)) {
    let homeOdds: number | undefined;
    let drawOdds: number | undefined;
    let awayOdds: number | undefined;
    let overOdds: number | undefined;
    let underOdds: number | undefined;
    let line: number | undefined;

    for (const market of book.markets ?? []) {
      if (market.key === "h2h") {
        for (const outcome of market.outcomes ?? []) {
          if (outcome.name === home) homeOdds = outcome.price;
          else if (outcome.name === away) awayOdds = outcome.price;
          else if (outcome.name.toLowerCase() === "draw") drawOdds = outcome.price;
        }
      } else if (market.key === "totals") {
        for (const outcome of market.outcomes ?? []) {
          if (outcome.name.toLowerCase() === "over") {
            overOdds = outcome.price;
            line = outcome.point ?? 2.5;
          } else if (outcome.name.toLowerCase() === "under") {
            underOdds = outcome.price;
          }
        }
      }
    }

    if (homeOdds && awayOdds) {
      results.push({
        bookmaker: book.title || book.key || "Unknown",
        home: homeOdds,
        draw: drawOdds,
        away: awayOdds,
        over: overOdds,
        under: underOdds,
        line,
      });
    }
  }

  return results;
}

async function fetchSportOdds(
  apiKey: string,
  sportKey: string
): Promise<LiveFixture[]> {
  const params = new URLSearchParams({
    apiKey,
    regions: "uk,eu,us,au",
    markets: "h2h,totals",
    oddsFormat: "decimal",
  });

  const url = `https://api.the-odds-api.com/v4/sports/${sportKey}/odds?${params.toString()}`;
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Odds API ${sportKey}: ${res.status} ${body.slice(0, 120)}`);
  }

  const events = (await res.json()) as OddsApiEvent[];
  const mapped = SPORT_MAP[sportKey] ?? { sport: "soccer", league: sportKey };

  return events
    .map((event) => {
      const home = event.home_team;
      const away = event.away_team;
      if (!home || !away) return null;

      const bookmakerOdds = parseBookmakers(event.bookmakers ?? [], home, away);
      if (bookmakerOdds.length === 0) return null;

      const eventId = event.id?.slice(0, 12) ?? "unknown";
      return {
        matchId: `live-${sportKey}-${eventId}`,
        sport: mapped.sport,
        league: mapped.league,
        homeTeam: home,
        awayTeam: away,
        kickoff: event.commence_time,
        bookmakerOdds,
        sportKey,
      } satisfies LiveFixture;
    })
    .filter((fixture): fixture is LiveFixture => fixture !== null);
}

export async function fetchLiveFixtures(apiKey: string): Promise<LiveFixture[]> {
  if (!apiKey.trim()) {
    throw new Error("No Odds API key configured");
  }

  const fixtures: LiveFixture[] = [];
  const errors: string[] = [];

  for (const sportKey of DEFAULT_SPORT_KEYS) {
    try {
      const batch = await fetchSportOdds(apiKey, sportKey);
      fixtures.push(...batch);
    } catch (error) {
      errors.push(error instanceof Error ? error.message : String(error));
    }
  }

  if (fixtures.length === 0 && errors.length > 0) {
    throw new Error(errors[0]);
  }

  return fixtures.sort(
    (a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime()
  );
}
