"""European lower-league classification — third and fourth tier."""

from __future__ import annotations

# (country, league name, tier)
EUROPEAN_LOWER_LEAGUES: tuple[tuple[str, str, int], ...] = (
    ("England", "EFL League One", 3),
    ("England", "EFL League Two", 4),
    ("England", "National League", 5),
    ("England", "National League North", 6),
    ("England", "National League South", 6),
    ("Spain", "Segunda Federación", 4),
    ("Spain", "Tercera Federación", 5),
    ("Germany", "3. Liga", 3),
    ("Germany", "Regionalliga", 4),
    ("Italy", "Serie C", 3),
    ("Italy", "Serie D", 4),
    ("France", "National", 3),
    ("France", "National 2", 4),
    ("Netherlands", "Tweede Divisie", 3),
    ("Netherlands", "Derde Divisie", 4),
    ("Portugal", "Liga 3", 3),
    ("Portugal", "Campeonato de Portugal", 4),
    ("Belgium", "Challenger Pro League", 2),
    ("Belgium", "First Amateur Division", 3),
    ("Scotland", "League One", 3),
    ("Scotland", "League Two", 4),
    ("Poland", "II Liga", 3),
    ("Turkey", "TFF Second League", 3),
    ("Turkey", "TFF Third League", 4),
)

TIER_3_4_KEYWORDS = (
    "league one",
    "league two",
    "national league",
    "segunda federación",
    "tercera",
    "3. liga",
    "regionalliga",
    "serie c",
    "serie d",
    "national 2",
    "tweede divisie",
    "derde divisie",
    "liga 3",
    "campeonato de portugal",
    "amateur",
    "ii liga",
    "second league",
    "third league",
)


def league_tier(league: str) -> int | None:
    """Return tier (3–6) if lower-league, else None for top flights."""
    lower = league.lower()
    for _country, name, tier in EUROPEAN_LOWER_LEAGUES:
        if name.lower() in lower or lower in name.lower():
            return tier
    for kw in TIER_3_4_KEYWORDS:
        if kw in lower:
            return 4 if "two" in kw or "2" in kw or "d" == kw[-1] else 3
    return None


def is_lower_league(league: str) -> bool:
    tier = league_tier(league)
    return tier is not None and tier >= 3


def is_target_tier(league: str, min_tier: int = 3, max_tier: int = 4) -> bool:
    tier = league_tier(league)
    return tier is not None and min_tier <= tier <= max_tier


def list_lower_leagues() -> list[dict]:
    return [
        {"country": c, "league": name, "tier": t}
        for c, name, t in EUROPEAN_LOWER_LEAGUES
        if 3 <= t <= 4
    ]
