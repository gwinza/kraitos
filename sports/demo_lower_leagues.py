"""Demo fixtures — European third and fourth tier teams."""

from __future__ import annotations

from sports.demo_data import _kickoff
from sports.models import (
    BookmakerOdds,
    CoachProfile,
    FormSnapshot,
    MatchContext,
    Sport,
    TeamProfile,
    XGSnapshot,
)


def build_lower_league_fixtures() -> list[MatchContext]:
    return [
        _eng_league_two(),
        _eng_national_league(),
        _ger_regionalliga(),
        _ita_serie_c(),
        _esp_segunda_federacion(),
        _fra_national_2(),
        _ned_tweede_divisie(),
        _por_liga3(),
        _sco_league_two(),
        _pol_ii_liga(),
    ]


def _eng_league_two() -> MatchContext:
    return MatchContext(
        match_id="eng-l2-001",
        sport=Sport.SOCCER,
        league="EFL League Two",
        home_team="Wrexham",
        away_team="Notts County",
        kickoff=_kickoff(20),
        trace_id="trace-eng-l2-001",
        home_profile=TeamProfile(
            name="Wrexham",
            squad_quality=64.0,
            market_value_m=8.5,
            full_strength_pct=100.0,
            recent_transfers=("Fletcher",),
        ),
        away_profile=TeamProfile(
            name="Notts County",
            squad_quality=61.0,
            market_value_m=6.2,
            injuries=("Rodrigues",),
            full_strength_pct=92.0,
        ),
        home_coach=CoachProfile(
            name="Parkinson",
            tactical_style="Direct, set-piece heavy",
            home_overperformance=0.18,
            away_overperformance=0.06,
            adaptability=0.72,
            historical_overperformance=0.14,
        ),
        away_coach=CoachProfile(
            name="Burch",
            tactical_style="Possession in lower block",
            home_overperformance=0.08,
            away_overperformance=0.11,
            adaptability=0.65,
            historical_overperformance=0.05,
        ),
        home_form=FormSnapshot(
            last_5="WDWWL",
            last_10="WDWWLWDWLW",
            home_form="WWW",
            away_form="WL",
            momentum="Strong home run",
            goal_trend="1.9 xG at home last 5",
            trend_label="Home fortress — sustainable chance creation",
        ),
        away_form=FormSnapshot(
            last_5="LWDWL",
            last_10="LWDWLLWDWL",
            home_form="LW",
            away_form="DWL",
            momentum="Inconsistent away",
            goal_trend="0.8 xG away last 5",
            trend_label="Away form fragile — struggles to create",
        ),
        home_xg=XGSnapshot(
            xg=1.7, xga=1.0, big_chances_created=8, big_chances_conceded=4,
            shot_quality=0.10, conversion_rate=0.14, defensive_efficiency=0.74,
            luck_label="Underrated — results lag xG at home",
        ),
        away_xg=XGSnapshot(
            xg=1.0, xga=1.6, big_chances_created=4, big_chances_conceded=9,
            shot_quality=0.07, conversion_rate=0.09, defensive_efficiency=0.58,
            luck_label="Overrated away — results flatter than metrics",
        ),
        bookmaker_odds=(
            BookmakerOdds("Bet365", 2.15, 3.30, 3.40),
            BookmakerOdds("SkyBet", 2.05, 3.40, 3.55),
        ),
        context_factors=(
            "Promotion race — both teams within 6 points of automatic spots",
            "Wrexham sell-out home crowd — significant home edge in L2",
            "Notts County 280-mile round trip midweek",
        ),
    )


def _eng_national_league() -> MatchContext:
    return MatchContext(
        match_id="eng-nl-001",
        sport=Sport.SOCCER,
        league="National League",
        home_team="Chesterfield",
        away_team="Barnet",
        kickoff=_kickoff(28),
        trace_id="trace-eng-nl-001",
        home_profile=TeamProfile(
            name="Chesterfield", squad_quality=58.0, market_value_m=3.5, full_strength_pct=100.0,
        ),
        away_profile=TeamProfile(
            name="Barnet", squad_quality=56.5, market_value_m=3.0,
            suspensions=("Sweeney",), full_strength_pct=90.0,
        ),
        home_form=FormSnapshot(
            last_5="WWWLW", last_10="WWWLWWLLWW", home_form="WWWL",
            away_form="WW", momentum="Promotion push", goal_trend="+1.4 xG delta",
            trend_label="Improving — table position catching underlying metrics",
        ),
        away_form=FormSnapshot(
            last_5="DLLWD", last_10="DLLWDLLWDL", home_form="DL",
            away_form="LWD", momentum="Recovering", goal_trend="Defensive leaks on road",
            trend_label="Away defence conceding 1.8 xGA per match",
        ),
        home_xg=XGSnapshot(
            xg=1.5, xga=1.1, big_chances_created=7, big_chances_conceded=5,
            shot_quality=0.09, conversion_rate=0.11, defensive_efficiency=0.68,
            luck_label="Fair at home",
        ),
        away_xg=XGSnapshot(
            xg=0.9, xga=1.7, big_chances_created=3, big_chances_conceded=10,
            shot_quality=0.06, conversion_rate=0.08, defensive_efficiency=0.52,
            luck_label="Away xGA concerning",
        ),
        bookmaker_odds=(
            BookmakerOdds("Bet365", 2.25, 3.25, 3.10),
            BookmakerOdds("BetVictor", 2.20, 3.30, 3.20),
        ),
        context_factors=("National League title race", "Barnet missing key centre-back"),
    )


def _ger_regionalliga() -> MatchContext:
    return MatchContext(
        match_id="ger-reg-001",
        sport=Sport.SOCCER,
        league="Regionalliga West",
        home_team="FC Viktoria Köln",
        away_team="Wuppertaler SV",
        kickoff=_kickoff(34),
        trace_id="trace-ger-reg-001",
        home_profile=TeamProfile(
            name="Viktoria Köln", squad_quality=55.0, market_value_m=2.8, full_strength_pct=95.0,
        ),
        away_profile=TeamProfile(
            name="Wuppertaler", squad_quality=50.0, market_value_m=1.5,
            injuries=("Hoxha", "Baku"), full_strength_pct=82.0,
        ),
        home_form=FormSnapshot(
            last_5="WWWDW", last_10="WWWDWWLWDW", home_form="WWWD",
            away_form="WW", momentum="Promotion favourite", goal_trend="2.0 xG at home",
            trend_label="Dominant home xG — market slow to adjust",
        ),
        away_form=FormSnapshot(
            last_5="LLDLW", last_10="LLDLWLLDLW", home_form="LL",
            away_form="DLW", momentum="Relegation scrap", goal_trend="0.6 xG away",
            trend_label="False draw streak — lucky points on road",
        ),
        home_xg=XGSnapshot(
            xg=1.9, xga=0.8, big_chances_created=10, big_chances_conceded=3,
            shot_quality=0.12, conversion_rate=0.13, defensive_efficiency=0.78,
            luck_label="Underrated — best xG diff in division",
        ),
        away_xg=XGSnapshot(
            xg=0.7, xga=1.8, big_chances_created=2, big_chances_conceded=12,
            shot_quality=0.05, conversion_rate=0.07, defensive_efficiency=0.48,
            luck_label="Lucky away results unsustainable",
        ),
        bookmaker_odds=(
            BookmakerOdds("Tipico", 1.85, 3.60, 4.00),
            BookmakerOdds("Bet365", 1.90, 3.50, 3.80),
        ),
        context_factors=(
            "Regionalliga markets thin — 0.15+ odds spreads common",
            "Wuppertaler squad depleted by injuries",
        ),
    )


def _ita_serie_c() -> MatchContext:
    return MatchContext(
        match_id="ita-sc-001",
        sport=Sport.SOCCER,
        league="Serie C Group B",
        home_team="Padova",
        away_team="Triestina",
        kickoff=_kickoff(42),
        trace_id="trace-ita-sc-001",
        home_profile=TeamProfile(
            name="Padova", squad_quality=59.0, market_value_m=4.0, full_strength_pct=100.0,
        ),
        away_profile=TeamProfile(
            name="Triestina", squad_quality=52.0, market_value_m=2.0, full_strength_pct=88.0,
        ),
        home_coach=CoachProfile(
            name="Bianco", tactical_style="3-5-2 pressing",
            home_overperformance=0.15, away_overperformance=0.03,
            adaptability=0.70, historical_overperformance=0.10,
        ),
        home_form=FormSnapshot(
            last_5="DWWWW", last_10="DWWWWWDWWW", home_form="DWWW",
            away_form="W", momentum="Title charge", goal_trend="1.6 xG per match",
            trend_label="Sustainable winning run backed by chance quality",
        ),
        away_form=FormSnapshot(
            last_5="LLWDL", last_10="LLWDLLLWDL", home_form="LW",
            away_form="WDL", momentum="Declining", goal_trend="0.9 xG",
            trend_label="Mid-table complacency — defensive drift",
        ),
        home_xg=XGSnapshot(
            xg=1.6, xga=0.9, big_chances_created=8, big_chances_conceded=4,
            shot_quality=0.11, conversion_rate=0.12, defensive_efficiency=0.72,
            luck_label="Fair",
        ),
        away_xg=XGSnapshot(
            xg=0.9, xga=1.5, big_chances_created=4, big_chances_conceded=8,
            shot_quality=0.07, conversion_rate=0.09, defensive_efficiency=0.55,
            luck_label="Overrated",
        ),
        bookmaker_odds=(
            BookmakerOdds("Sisal", 1.75, 3.40, 4.50),
            BookmakerOdds("Snai", 1.80, 3.35, 4.30),
        ),
        context_factors=("Serie C promotion playoff race", "Padova unbeaten in 8 at home"),
    )


def _esp_segunda_federacion() -> MatchContext:
    return MatchContext(
        match_id="esp-sf-001",
        sport=Sport.SOCCER,
        league="Segunda Federación",
        home_team="Racing Ferrol",
        away_team="Zamora CF",
        kickoff=_kickoff(38),
        trace_id="trace-esp-sf-001",
        home_profile=TeamProfile(
            name="Racing Ferrol", squad_quality=54.0, market_value_m=2.5, full_strength_pct=100.0,
        ),
        away_profile=TeamProfile(
            name="Zamora", squad_quality=48.0, market_value_m=1.2,
            injuries=("Vázquez",), full_strength_pct=85.0,
        ),
        home_form=FormSnapshot(
            last_5="WWLWW", last_10="WWLWWWLWWL", home_form="WWLWW",
            away_form="L", momentum="Galician derby form", goal_trend="1.4 xG home",
            trend_label="Strong at Estadio A Malata",
        ),
        away_form=FormSnapshot(
            last_5="LDLLW", last_10="LDLLWLDLLW", home_form="LD",
            away_form="LLW", momentum="Struggling", goal_trend="0.7 xG away",
            trend_label="Long away trips hurting performance",
        ),
        home_xg=XGSnapshot(
            xg=1.4, xga=1.0, big_chances_created=6, big_chances_conceded=5,
            shot_quality=0.09, conversion_rate=0.11, defensive_efficiency=0.66,
            luck_label="Fair home metrics",
        ),
        away_xg=XGSnapshot(
            xg=0.7, xga=1.6, big_chances_created=3, big_chances_conceded=9,
            shot_quality=0.06, conversion_rate=0.08, defensive_efficiency=0.50,
            luck_label="Unders creating — market overvalues away double chance",
        ),
        bookmaker_odds=(
            BookmakerOdds("Codere", 1.95, 3.20, 3.80),
            BookmakerOdds("Bet365", 2.00, 3.15, 3.70),
        ),
        context_factors=("400km travel for Zamora", "Galician regional rivalry"),
    )


def _fra_national_2() -> MatchContext:
    return MatchContext(
        match_id="fra-n2-001",
        sport=Sport.SOCCER,
        league="National 2 Group A",
        home_team="Versailles",
        away_team="Chambly",
        kickoff=_kickoff(46),
        trace_id="trace-fra-n2-001",
        home_profile=TeamProfile(
            name="Versailles", squad_quality=51.0, market_value_m=1.8, full_strength_pct=100.0,
        ),
        away_profile=TeamProfile(
            name="Chambly", squad_quality=49.0, market_value_m=1.4, full_strength_pct=95.0,
        ),
        home_form=FormSnapshot(
            last_5="WDWDW", last_10="WDWDWWDWDW", home_form="WDWDW",
            away_form="W", momentum="Stable", goal_trend="Low-event profile",
            trend_label="Tight matches — draw probability elevated",
        ),
        away_form=FormSnapshot(
            last_5="DWDLD", last_10="DWDLDWDWLD", home_form="DW",
            away_form="DLD", momentum="Draw specialists", goal_trend="0.9 xG both ends",
            trend_label="Half of away games end level",
        ),
        home_xg=XGSnapshot(
            xg=1.1, xga=1.0, big_chances_created=4, big_chances_conceded=4,
            shot_quality=0.08, conversion_rate=0.10, defensive_efficiency=0.65,
            luck_label="Low variance team",
        ),
        away_xg=XGSnapshot(
            xg=0.9, xga=1.1, big_chances_created=3, big_chances_conceded=5,
            shot_quality=0.07, conversion_rate=0.09, defensive_efficiency=0.62,
            luck_label="Fair",
        ),
        bookmaker_odds=(
            BookmakerOdds("Winamax", 2.40, 2.90, 3.00),
            BookmakerOdds("Betclic", 2.35, 2.95, 3.05),
        ),
        context_factors=("National 2 — efficient draw pricing often wrong", "Local derby Paris basin"),
    )


def _ned_tweede_divisie() -> MatchContext:
    return MatchContext(
        match_id="ned-td-001",
        sport=Sport.SOCCER,
        league="Tweede Divisie",
        home_team="RKAV Volendam",
        away_team="Jong Ajax",
        kickoff=_kickoff(24),
        trace_id="trace-ned-td-001",
        home_profile=TeamProfile(
            name="Volendam", squad_quality=53.0, market_value_m=2.0, full_strength_pct=100.0,
        ),
        away_profile=TeamProfile(
            name="Jong Ajax", squad_quality=57.0, market_value_m=0.0,
            injuries=("Youth call-ups",), full_strength_pct=75.0,
        ),
        home_form=FormSnapshot(
            last_5="LWWDL", last_10="LWWDLWWLDL", home_form="LWW",
            away_form="DL", momentum="Volatile", goal_trend="Open games",
            trend_label="High variance — goals markets preferred over winner",
        ),
        away_form=FormSnapshot(
            last_5="WLLWD", last_10="WLLWDWLLWD", home_form="WL",
            away_form="LWD", momentum="Youth inconsistency", goal_trend="1.8 xG but 1.7 xGA",
            trend_label="Jong Ajax — talent edge but defensive fragility",
        ),
        home_xg=XGSnapshot(
            xg=1.3, xga=1.4, big_chances_created=6, big_chances_conceded=7,
            shot_quality=0.08, conversion_rate=0.10, defensive_efficiency=0.58,
            luck_label="Entertainment value — not defensive",
        ),
        away_xg=XGSnapshot(
            xg=1.6, xga=1.5, big_chances_created=8, big_chances_conceded=8,
            shot_quality=0.10, conversion_rate=0.11, defensive_efficiency=0.54,
            luck_label="Open tactical profile",
        ),
        bookmaker_odds=(
            BookmakerOdds("Unibet", 2.60, 3.50, 2.45),
            BookmakerOdds("Toto", 2.55, 3.45, 2.50),
        ),
        context_factors=(
            "Jong Ajax missing 4 players to first team",
            "Tweede Divisie — market overreacts to brand name",
        ),
    )


def _por_liga3() -> MatchContext:
    return MatchContext(
        match_id="por-l3-001",
        sport=Sport.SOCCER,
        league="Liga 3",
        home_team="Fafe",
        away_team="São João Ver",
        kickoff=_kickoff(50),
        trace_id="trace-por-l3-001",
        home_profile=TeamProfile(
            name="Fafe", squad_quality=50.0, market_value_m=1.0, full_strength_pct=100.0,
        ),
        away_profile=TeamProfile(
            name="São João Ver", squad_quality=47.0, market_value_m=0.8, full_strength_pct=92.0,
        ),
        home_form=FormSnapshot(
            last_5="WWLWW", last_10="WWLWWWLWWL", home_form="WWLWW",
            away_form="L", momentum="Home specialists", goal_trend="1.5 xG home",
            trend_label="Nearly unbeaten at home this season",
        ),
        away_form=FormSnapshot(
            last_5="LLLLD", last_10="LLLLDLLLLD", home_form="LL",
            away_form="LLLD", momentum="Freefall", goal_trend="0.5 xG away",
            trend_label="Worst away record in group",
        ),
        bookmaker_odds=(
            BookmakerOdds("Betano", 1.70, 3.50, 4.80),
            BookmakerOdds("Bet365", 1.75, 3.45, 4.60),
        ),
        context_factors=("Liga 3 promotion group", "São João Ver winless in 9 away"),
    )


def _sco_league_two() -> MatchContext:
    return MatchContext(
        match_id="sco-l2-001",
        sport=Sport.SOCCER,
        league="Scottish League Two",
        home_team="Spartans",
        away_team="East Fife",
        kickoff=_kickoff(32),
        trace_id="trace-sco-l2-001",
        home_profile=TeamProfile(
            name="Spartans", squad_quality=46.0, market_value_m=0.5, full_strength_pct=100.0,
        ),
        away_profile=TeamProfile(
            name="East Fife", squad_quality=48.0, market_value_m=0.6, full_strength_pct=100.0,
        ),
        home_form=FormSnapshot(
            last_5="DWDWW", last_10="DWDWWDWDWW", home_form="DWDWW",
            away_form="D", momentum="Part-time squad peaking", goal_trend="1.2 xG",
            trend_label="Synthetic xG model — sparse data caveat",
        ),
        away_form=FormSnapshot(
            last_5="WDLWL", last_10="WDLWLDWLWL", home_form="WD",
            away_form="LWL", momentum="Mid-table", goal_trend="1.0 xG",
            trend_label="Balanced — no clear edge on form alone",
        ),
        home_xg=XGSnapshot(
            xg=1.2, xga=1.1, big_chances_created=4, big_chances_conceded=4,
            shot_quality=0.07, conversion_rate=0.09, defensive_efficiency=0.60,
            luck_label="Limited data — confidence reduced",
        ),
        away_xg=XGSnapshot(
            xg=1.0, xga=1.2, big_chances_created=3, big_chances_conceded=5,
            shot_quality=0.06, conversion_rate=0.08, defensive_efficiency=0.57,
            luck_label="Limited data",
        ),
        bookmaker_odds=(
            BookmakerOdds("Bet365", 2.50, 3.10, 2.75),
            BookmakerOdds("William Hill", 2.45, 3.15, 2.80),
        ),
        context_factors=(
            "Scottish L2 — part-time players, weather variance",
            "Sparse market — PASS unless clear model edge",
        ),
    )


def _pol_ii_liga() -> MatchContext:
    return MatchContext(
        match_id="pol-2-001",
        sport=Sport.SOCCER,
        league="II Liga",
        home_team="Warta Poznań",
        away_team="GKS Jastrzębie",
        kickoff=_kickoff(56),
        trace_id="trace-pol-2-001",
        home_profile=TeamProfile(
            name="Warta", squad_quality=56.0, market_value_m=2.5, full_strength_pct=100.0,
        ),
        away_profile=TeamProfile(
            name="Jastrzębie", squad_quality=50.0, market_value_m=1.2,
            suspensions=("Kowalski",), full_strength_pct=88.0,
        ),
        home_form=FormSnapshot(
            last_5="WWWWW", last_10="WWWWWWWWWW", home_form="WWWWW",
            away_form="W", momentum="Dominant", goal_trend="2.1 xG",
            trend_label="Promotion favourites — market may already price correctly",
        ),
        away_form=FormSnapshot(
            last_5="LLWLL", last_10="LLWLLLLWLL", home_form="LL",
            away_form="WLL", momentum="Relegation zone", goal_trend="0.8 xGA away",
            trend_label="Defensive collapse on road",
        ),
        home_xg=XGSnapshot(
            xg=1.8, xga=0.7, big_chances_created=9, big_chances_conceded=3,
            shot_quality=0.11, conversion_rate=0.15, defensive_efficiency=0.80,
            luck_label="Elite for division",
        ),
        away_xg=XGSnapshot(
            xg=0.8, xga=1.9, big_chances_created=3, big_chances_conceded=11,
            shot_quality=0.06, conversion_rate=0.07, defensive_efficiency=0.45,
            luck_label="Overrated when away",
        ),
        bookmaker_odds=(
            BookmakerOdds("STS", 1.55, 3.80, 5.50),
            BookmakerOdds("Betclic", 1.60, 3.70, 5.20),
        ),
        context_factors=("II Liga promotion", "Jastrzębie missing defensive anchor"),
    )
