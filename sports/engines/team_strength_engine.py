"""Team strength engine — true squad quality beyond league position."""

from __future__ import annotations

from sports.models import MatchContext


class TeamStrengthEngine:
    """Analyse squad quality, injuries, depth, and full-strength status."""

    def analyze(self, context: MatchContext) -> str:
        lines: list[str] = []

        for side, profile in (
            ("Home", context.home_profile),
            ("Away", context.away_profile),
        ):
            if not profile:
                lines.append(f"{side}: Profile unavailable.")
                continue

            injury_penalty = len(profile.injuries) * 3 + len(profile.suspensions) * 4
            adjusted = profile.squad_quality * (profile.full_strength_pct / 100)
            adjusted -= injury_penalty

            status = "Full strength" if profile.full_strength_pct >= 95 else "Depleted"
            if profile.injuries:
                status = f"Injuries: {', '.join(profile.injuries)}"
            if profile.suspensions:
                status += f" | Suspensions: {', '.join(profile.suspensions)}"

            mv = (
                f" | Market value: €{profile.market_value_m:.0f}M"
                if profile.market_value_m
                else ""
            )
            lines.append(
                f"{profile.name}: True strength {adjusted:.1f}/100 ({status}){mv}"
            )

        home_adj = self._score(context.home_profile)
        away_adj = self._score(context.away_profile)
        delta = home_adj - away_adj

        if abs(delta) < 3:
            lines.append("Assessment: Closely matched on true strength — market may overreact to table position.")
        elif delta > 8:
            lines.append(f"Assessment: {context.home_team} materially stronger when adjusted for availability.")
        elif delta < -8:
            lines.append(f"Assessment: {context.away_team} materially stronger — home advantage may not compensate.")
        else:
            leader = context.home_team if delta > 0 else context.away_team
            lines.append(f"Assessment: Slight edge to {leader} on adjusted squad quality.")

        return "\n".join(lines)

    def strength_delta(self, context: MatchContext) -> float:
        return self._score(context.home_profile) - self._score(context.away_profile)

    def _score(self, profile) -> float:
        if not profile:
            return 50.0
        penalty = len(profile.injuries) * 3 + len(profile.suspensions) * 4
        return profile.squad_quality * (profile.full_strength_pct / 100) - penalty
