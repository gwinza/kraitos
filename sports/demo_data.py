"""Demo fixtures and odds for Kraitos Sports — works offline without API keys."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sports.models import (
    BookmakerOdds,
    CoachProfile,
    FormSnapshot,
    MatchContext,
    Sport,
    TeamProfile,
    XGSnapshot,
)


def _kickoff(hours_ahead: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours_ahead)


def build_demo_fixtures() -> list[MatchContext]:
    """Rich demo dataset spanning multiple sports and edge scenarios."""
    return [
        _arsenal_liverpool(),
        _lakers_celtics(),
        _djokovic_alcaraz(),
        _lower_league_value(),
        _arbitrage_fixture(),
        _pass_fixture(),
        _cricket_ipl(),
        _nfl_chiefs(),
        _serie_a_milan(),
        _ligue1_psg(),
        _nhl_rangers(),
        _mlb_yankees(),
        _rugby_ireland(),
        _ufc_main_event(),
        _esports_lol(),
    ]


def _arsenal_liverpool() -> MatchContext:
    return MatchContext(
        match_id="epl-001",
        sport=Sport.SOCCER,
        league="Premier League",
        home_team="Arsenal",
        away_team="Liverpool",
        kickoff=_kickoff(26),
        trace_id="trace-epl-001",
        home_profile=TeamProfile(
            name="Arsenal",
            squad_quality=88.5,
            market_value_m=950.0,
            injuries=("Saka", "Timber"),
            suspensions=(),
            full_strength_pct=92.0,
            recent_transfers=("Merino",),
        ),
        away_profile=TeamProfile(
            name="Liverpool",
            squad_quality=91.2,
            market_value_m=980.0,
            injuries=("Alexander-Arnold",),
            suspensions=(),
            full_strength_pct=95.0,
        ),
        home_coach=CoachProfile(
            name="Arteta",
            tactical_style="Possession pressing",
            home_overperformance=0.12,
            away_overperformance=0.04,
            adaptability=0.85,
            historical_overperformance=0.08,
        ),
        away_coach=CoachProfile(
            name="Slot",
            tactical_style="High press transitions",
            home_overperformance=0.10,
            away_overperformance=0.15,
            adaptability=0.90,
            historical_overperformance=0.11,
        ),
        home_form=FormSnapshot(
            last_5="WWDWW",
            last_10="WWWDWWLWDW",
            home_form="WWWDW",
            away_form="WWD",
            momentum="Rising",
            goal_trend="+2.1 xG delta vs season avg",
            trend_label="Improving — sustainable xG backing",
        ),
        away_form=FormSnapshot(
            last_5="WWWLW",
            last_10="WWWWLWWLWW",
            home_form="WWW",
            away_form="WWLW",
            momentum="Stable elite",
            goal_trend="Elite chance creation maintained",
            trend_label="Strong but slight defensive variance",
        ),
        home_xg=XGSnapshot(
            xg=2.1,
            xga=0.9,
            big_chances_created=14,
            big_chances_conceded=4,
            shot_quality=0.14,
            conversion_rate=0.18,
            defensive_efficiency=0.82,
            luck_label="Fair — results match underlying metrics",
        ),
        away_xg=XGSnapshot(
            xg=2.4,
            xga=1.1,
            big_chances_created=16,
            big_chances_conceded=6,
            shot_quality=0.15,
            conversion_rate=0.17,
            defensive_efficiency=0.78,
            luck_label="Slight underperformance vs xG — value potential",
        ),
        bookmaker_odds=(
            BookmakerOdds("Bet365", 2.45, 3.40, 2.90),
            BookmakerOdds("Pinnacle", 2.52, 3.35, 2.85),
            BookmakerOdds("Betfair", 2.48, 3.45, 2.88),
            BookmakerOdds("William Hill", 2.38, 3.50, 3.00),
        ),
        context_factors=(
            "Title race implications — high motivation both sides",
            "Arsenal 4 days rest, Liverpool 3 days rest",
            "Historical rivalry — elevated variance risk",
            "Weather: clear, 12°C — neutral",
        ),
    )


def _lakers_celtics() -> MatchContext:
    return MatchContext(
        match_id="nba-001",
        sport=Sport.BASKETBALL,
        league="NBA",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        kickoff=_kickoff(48),
        trace_id="trace-nba-001",
        home_profile=TeamProfile(
            name="Lakers",
            squad_quality=84.0,
            market_value_m=0.0,
            injuries=("Davis",),
            full_strength_pct=88.0,
        ),
        away_profile=TeamProfile(
            name="Celtics",
            squad_quality=92.5,
            market_value_m=0.0,
            full_strength_pct=100.0,
        ),
        home_form=FormSnapshot(
            last_5="WLWWL",
            last_10="WLWWLWWLLW",
            home_form="LWWL",
            away_form="WLW",
            momentum="Volatile",
            goal_trend="Defensive rating declining",
            trend_label="False winning streak risk on home court",
        ),
        away_form=FormSnapshot(
            last_5="WWWWW",
            last_10="WWWWWWWLWW",
            home_form="WWW",
            away_form="WWW",
            momentum="Elite",
            goal_trend="+8.2 net rating last 10",
            trend_label="Sustainable dominance",
        ),
        bookmaker_odds=(
            BookmakerOdds("DraftKings", 2.20, None, 1.72, over=1.91, under=1.91, line=224.5),
            BookmakerOdds("FanDuel", 2.15, None, 1.75, over=1.88, under=1.94, line=224.5),
            BookmakerOdds("BetMGM", 2.25, None, 1.68, over=1.93, under=1.89, line=225.0),
        ),
        context_factors=(
            "Back-to-back for Lakers",
            "Celtics on 3-game road trip — travel fatigue moderate",
            "Playoff seeding implications",
        ),
    )


def _djokovic_alcaraz() -> MatchContext:
    return MatchContext(
        match_id="atp-001",
        sport=Sport.TENNIS,
        league="ATP Masters 1000",
        home_team="Novak Djokovic",
        away_team="Carlos Alcaraz",
        kickoff=_kickoff(12),
        trace_id="trace-atp-001",
        home_profile=TeamProfile(name="Djokovic", squad_quality=94.0, market_value_m=0.0),
        away_profile=TeamProfile(name="Alcaraz", squad_quality=96.5, market_value_m=0.0),
        home_form=FormSnapshot(
            last_5="WWWLW",
            last_10="WWWWLWWWLW",
            home_form="N/A",
            away_form="N/A",
            momentum="Veteran resilience",
            goal_trend="Break point conversion 42%",
            trend_label="Still elite on hard courts",
        ),
        away_form=FormSnapshot(
            last_5="WWWWW",
            last_10="WWWWWWWWWW",
            home_form="N/A",
            away_form="N/A",
            momentum="Peak form",
            goal_trend="First serve win % 78%",
            trend_label="Peak physical condition",
        ),
        bookmaker_odds=(
            BookmakerOdds("Bet365", 2.10, None, 1.80),
            BookmakerOdds("Pinnacle", 2.15, None, 1.78),
        ),
        context_factors=("Hard court — Djokovic historical edge", "Semi-final — high pressure"),
    )


def _lower_league_value() -> MatchContext:
    return MatchContext(
        match_id="efl-001",
        sport=Sport.SOCCER,
        league="EFL League One",
        home_team="Bolton Wanderers",
        away_team="Peterborough",
        kickoff=_kickoff(72),
        trace_id="trace-efl-001",
        home_profile=TeamProfile(
            name="Bolton",
            squad_quality=62.0,
            market_value_m=12.0,
            full_strength_pct=100.0,
        ),
        away_profile=TeamProfile(
            name="Peterborough",
            squad_quality=58.5,
            market_value_m=9.0,
            injuries=("Fry", "Morton"),
            full_strength_pct=85.0,
        ),
        home_xg=XGSnapshot(
            xg=1.8,
            xga=1.2,
            big_chances_created=9,
            big_chances_conceded=5,
            shot_quality=0.11,
            conversion_rate=0.12,
            defensive_efficiency=0.71,
            luck_label="Underrated — xG significantly exceeds results",
        ),
        away_xg=XGSnapshot(
            xg=1.1,
            xga=1.9,
            big_chances_created=5,
            big_chances_conceded=11,
            shot_quality=0.08,
            conversion_rate=0.10,
            defensive_efficiency=0.55,
            luck_label="Overrated — results exceed underlying quality",
        ),
        bookmaker_odds=(
            BookmakerOdds("Bet365", 2.80, 3.20, 2.50),
            BookmakerOdds("SkyBet", 2.60, 3.30, 2.70),
        ),
        context_factors=("Promotion race — Bolton high motivation", "Peterborough fixture congestion"),
    )


def _arbitrage_fixture() -> MatchContext:
    return MatchContext(
        match_id="bund-001",
        sport=Sport.SOCCER,
        league="Bundesliga",
        home_team="Bayern Munich",
        away_team="Dortmund",
        kickoff=_kickoff(36),
        trace_id="trace-bund-001",
        home_profile=TeamProfile(name="Bayern", squad_quality=93.0, market_value_m=850.0),
        away_profile=TeamProfile(name="Dortmund", squad_quality=86.0, market_value_m=520.0),
        bookmaker_odds=(
            BookmakerOdds("BookA", 1.95, 3.80, 4.20),
            BookmakerOdds("BookB", 2.05, 3.60, 3.90),
            BookmakerOdds("BookC", 1.88, 4.00, 4.50),
        ),
        context_factors=("Der Klassiker — high liquidity",),
    )


def _pass_fixture() -> MatchContext:
    return MatchContext(
        match_id="lal-001",
        sport=Sport.SOCCER,
        league="La Liga",
        home_team="Getafe",
        away_team="Osasuna",
        kickoff=_kickoff(18),
        trace_id="trace-lal-001",
        home_profile=TeamProfile(name="Getafe", squad_quality=65.0, market_value_m=80.0),
        away_profile=TeamProfile(name="Osasuna", squad_quality=66.0, market_value_m=85.0),
        bookmaker_odds=(
            BookmakerOdds("Bet365", 2.70, 2.90, 3.00),
            BookmakerOdds("Pinnacle", 2.72, 2.88, 2.98),
        ),
        context_factors=("Low event match — efficient market pricing",),
    )


def _cricket_ipl() -> MatchContext:
    return MatchContext(
        match_id="ipl-001",
        sport=Sport.CRICKET,
        league="IPL",
        home_team="Mumbai Indians",
        away_team="Chennai Super Kings",
        kickoff=_kickoff(54),
        trace_id="trace-ipl-001",
        home_profile=TeamProfile(name="MI", squad_quality=87.0, market_value_m=0.0),
        away_profile=TeamProfile(name="CSK", squad_quality=85.5, market_value_m=0.0),
        bookmaker_odds=(
            BookmakerOdds("Bet365", 1.85, None, 2.05),
            BookmakerOdds("Betway", 1.90, None, 1.95),
        ),
        context_factors=("Evening dew factor — batting second advantage", "Playoff implications"),
    )


def _nfl_chiefs() -> MatchContext:
    return MatchContext(
        match_id="nfl-001",
        sport=Sport.AMERICAN_FOOTBALL,
        league="NFL",
        home_team="Kansas City Chiefs",
        away_team="Buffalo Bills",
        kickoff=_kickoff(96),
        trace_id="trace-nfl-001",
        home_profile=TeamProfile(name="Chiefs", squad_quality=94.0, market_value_m=0.0),
        away_profile=TeamProfile(name="Bills", squad_quality=91.0, market_value_m=0.0),
        bookmaker_odds=(
            BookmakerOdds("DraftKings", 1.75, None, 2.15, over=1.87, under=1.95, line=48.5),
            BookmakerOdds("FanDuel", 1.78, None, 2.10, over=1.90, under=1.92, line=48.5),
        ),
        context_factors=("Divisional rivalry", "Chiefs strong home record in playoffs"),
    )


def _serie_a_milan() -> MatchContext:
    return MatchContext(
        match_id="serie-001",
        sport=Sport.SOCCER,
        league="Serie A",
        home_team="AC Milan",
        away_team="Inter Milan",
        kickoff=_kickoff(44),
        trace_id="trace-serie-001",
        home_profile=TeamProfile(name="AC Milan", squad_quality=86.0, market_value_m=620.0),
        away_profile=TeamProfile(name="Inter", squad_quality=89.0, market_value_m=680.0),
        bookmaker_odds=(
            BookmakerOdds("Bet365", 2.90, 3.20, 2.55),
            BookmakerOdds("Sisal", 2.85, 3.25, 2.60),
        ),
        context_factors=("Derby della Madonnina — high variance", "Champions League race"),
    )


def _ligue1_psg() -> MatchContext:
    return MatchContext(
        match_id="ligue-001",
        sport=Sport.SOCCER,
        league="Ligue 1",
        home_team="PSG",
        away_team="Marseille",
        kickoff=_kickoff(30),
        trace_id="trace-ligue-001",
        home_profile=TeamProfile(name="PSG", squad_quality=90.0, market_value_m=900.0),
        away_profile=TeamProfile(name="Marseille", squad_quality=78.0, market_value_m=280.0),
        bookmaker_odds=(
            BookmakerOdds("Bet365", 1.55, 4.50, 5.50),
            BookmakerOdds("Unibet", 1.52, 4.60, 5.80),
        ),
        context_factors=("Le Classique — intense rivalry",),
    )


def _nhl_rangers() -> MatchContext:
    return MatchContext(
        match_id="nhl-001",
        sport=Sport.ICE_HOCKEY,
        league="NHL",
        home_team="NY Rangers",
        away_team="Boston Bruins",
        kickoff=_kickoff(40),
        trace_id="trace-nhl-001",
        home_profile=TeamProfile(name="Rangers", squad_quality=82.0, market_value_m=0.0),
        away_profile=TeamProfile(name="Bruins", squad_quality=85.0, market_value_m=0.0),
        bookmaker_odds=(
            BookmakerOdds("DraftKings", 2.10, None, 1.80, over=1.91, under=1.91, line=5.5),
            BookmakerOdds("FanDuel", 2.05, None, 1.85, over=1.88, under=1.94, line=5.5),
        ),
        context_factors=("Original Six rivalry", "Playoff positioning"),
    )


def _mlb_yankees() -> MatchContext:
    return MatchContext(
        match_id="mlb-001",
        sport=Sport.BASEBALL,
        league="MLB",
        home_team="NY Yankees",
        away_team="Boston Red Sox",
        kickoff=_kickoff(52),
        trace_id="trace-mlb-001",
        home_profile=TeamProfile(name="Yankees", squad_quality=84.0, market_value_m=0.0),
        away_profile=TeamProfile(name="Red Sox", squad_quality=76.0, market_value_m=0.0),
        bookmaker_odds=(
            BookmakerOdds("DraftKings", 1.70, None, 2.20, over=1.87, under=1.95, line=8.5),
            BookmakerOdds("BetMGM", 1.72, None, 2.15, over=1.90, under=1.92, line=8.5),
        ),
        context_factors=("Yankees-Red Sox rivalry", "Divisional standings impact"),
    )


def _rugby_ireland() -> MatchContext:
    return MatchContext(
        match_id="rugby-001",
        sport=Sport.RUGBY,
        league="Six Nations",
        home_team="Ireland",
        away_team="France",
        kickoff=_kickoff(120),
        trace_id="trace-rugby-001",
        home_profile=TeamProfile(name="Ireland", squad_quality=91.0, market_value_m=0.0),
        away_profile=TeamProfile(name="France", squad_quality=90.0, market_value_m=0.0),
        bookmaker_odds=(
            BookmakerOdds("Bet365", 1.95, None, 1.95),
            BookmakerOdds("Paddy Power", 2.00, None, 1.90),
        ),
        context_factors=("Grand Slam implications", "Home crowd advantage significant"),
    )


def _ufc_main_event() -> MatchContext:
    return MatchContext(
        match_id="ufc-001",
        sport=Sport.MMA,
        league="UFC",
        home_team="Alex Pereira",
        away_team="Israel Adesanya",
        kickoff=_kickoff(68),
        trace_id="trace-ufc-001",
        home_profile=TeamProfile(name="Pereira", squad_quality=88.0, market_value_m=0.0),
        away_profile=TeamProfile(name="Adesanya", squad_quality=87.0, market_value_m=0.0),
        bookmaker_odds=(
            BookmakerOdds("Bet365", 1.75, None, 2.15),
            BookmakerOdds("DraftKings", 1.80, None, 2.05),
        ),
        context_factors=("Title fight — trilogy", "High finish probability"),
    )


def _esports_lol() -> MatchContext:
    return MatchContext(
        match_id="lol-001",
        sport=Sport.ESPORTS,
        league="LoL LEC",
        home_team="G2 Esports",
        away_team="Fnatic",
        kickoff=_kickoff(14),
        trace_id="trace-lol-001",
        home_profile=TeamProfile(name="G2", squad_quality=85.0, market_value_m=0.0),
        away_profile=TeamProfile(name="Fnatic", squad_quality=80.0, market_value_m=0.0),
        bookmaker_odds=(
            BookmakerOdds("Betway", 1.65, None, 2.25),
            BookmakerOdds("Unikrn", 1.70, None, 2.15),
        ),
        context_factors=("Playoff bracket implications", "Patch meta shift — model uncertainty"),
    )
