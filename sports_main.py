"""Kraitos Sports CLI — scan matches and print intelligence reports."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brains.sports_brain import SportsBrain
from sports.models import Sport


@click.command()
@click.option("--sport", default=None, help="Filter by sport (e.g. soccer)")
@click.option("--league", default=None, help="Filter by league name")
@click.option("--match-id", default=None, help="Analyse single match")
@click.option("--lower-leagues", is_flag=True, help="European 3rd/4th tier only")
@click.option("--tier-min", default=3, help="Minimum league tier")
@click.option("--tier-max", default=4, help="Maximum league tier")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def main(
    sport: str | None,
    league: str | None,
    match_id: str | None,
    lower_leagues: bool,
    tier_min: int,
    tier_max: int,
    as_json: bool,
) -> None:
    """Kraitos Sports — finds edges, not winners."""
    brain = SportsBrain()
    sport_enum = Sport(sport) if sport else None

    if match_id:
        ctx = brain.fixtures.get_match(match_id)
        if not ctx:
            click.echo(f"Match not found: {match_id}", err=True)
            sys.exit(1)
        analyses = [brain.evaluate(ctx)]
    elif lower_leagues:
        analyses = brain.scan_lower_leagues(tier_min=tier_min, tier_max=tier_max)
    else:
        analyses = brain.scan_and_analyze(sport=sport_enum, league=league)

    if as_json:
        click.echo(json.dumps([a.to_dict() for a in analyses], indent=2))
        return

    click.echo(f"\n{'='*60}")
    click.echo("  KRAITOS SPORTS — Kraitos finds edges, not winners.")
    click.echo(f"{'='*60}\n")

    for a in analyses:
        click.echo(f"Match: {a.match_label}")
        click.echo(f"League: {a.league}")
        click.echo(f"Kick-off: {a.kickoff.isoformat()}")
        click.echo(f"Decision: {a.decision.value}")
        click.echo(f"Edge Score: {a.edge_score}/100 | Confidence: {a.confidence}/100")
        click.echo(f"Grade: {a.grade.value} | Risk: {a.risk_level.value}")
        if a.value_bet:
            click.echo(f"EV: {a.value_bet.ev_pct:+.1f}% | Fair: {a.value_bet.fair_odds:.2f} | Market: {a.value_bet.market_odds:.2f}")
        if a.arbitrage and a.arbitrage.detected:
            click.echo(f"Arbitrage: {a.arbitrage.profit_pct:.2f}% profit")
        if a.prediction:
            click.echo(f"Prediction: {a.prediction} ({a.prediction_confidence:.0f}% confidence)")
            click.echo(f"Why: {a.prediction_reasoning[:200]}...")
        click.echo(f"\nReasoning: {a.reasoning_summary}\n")
        click.echo("-" * 60)


if __name__ == "__main__":
    main()
