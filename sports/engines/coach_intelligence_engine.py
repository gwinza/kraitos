"""Coach intelligence engine — tactical and historical overperformance."""

from __future__ import annotations

from sports.models import MatchContext


class CoachIntelligenceEngine:
    """Evaluate coaches who consistently outperform expectations."""

    def analyze(self, context: MatchContext) -> str:
        lines: list[str] = []

        for side, coach, is_home in (
            ("Home", context.home_coach, True),
            ("Away", context.away_coach, False),
        ):
            if not coach:
                continue
            venue_perf = coach.home_overperformance if is_home else coach.away_overperformance
            lines.append(
                f"{coach.name} ({side}): {coach.tactical_style}. "
                f"Venue overperformance: {venue_perf:+.0%}. "
                f"Historical edge: {coach.historical_overperformance:+.0%}. "
                f"Adaptability: {coach.adaptability:.0%}."
            )

        if context.home_coach and context.away_coach:
            home_edge = (
                context.home_coach.home_overperformance
                + context.home_coach.historical_overperformance
            )
            away_edge = (
                context.away_coach.away_overperformance
                + context.away_coach.historical_overperformance
            )
            if home_edge > away_edge + 0.05:
                lines.append(
                    f"Coach edge favours {context.home_team} — "
                    f"{context.home_coach.name} consistently extracts home value."
                )
            elif away_edge > home_edge + 0.05:
                lines.append(
                    f"Coach edge favours {context.away_team} — "
                    f"{context.away_coach.name} excels in away setups."
                )
            else:
                lines.append("Coach matchup: Neutral — neither coach shows clear overperformance edge.")

        return "\n".join(lines) if lines else "Coach data unavailable for this fixture."

    def coach_adjustment(self, context: MatchContext) -> float:
        """Return probability adjustment favouring home team (-1 to +1 scale)."""
        if not context.home_coach or not context.away_coach:
            return 0.0
        home = (
            context.home_coach.home_overperformance
            + context.home_coach.historical_overperformance * 0.5
        )
        away = (
            context.away_coach.away_overperformance
            + context.away_coach.historical_overperformance * 0.5
        )
        return max(-0.08, min(0.08, (home - away) * 0.3))
