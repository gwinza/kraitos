"""Advanced xG engine — luck, overrated, and underrated team detection."""

from __future__ import annotations

from sports.models import MatchContext


class XGEngine:
    """Analyse expected goals metrics for true performance quality."""

    def analyze(self, context: MatchContext) -> str:
        lines: list[str] = []

        for label, xg in (
            (context.home_team, context.home_xg),
            (context.away_team, context.away_xg),
        ):
            if not xg:
                continue
            lines.append(
                f"{label}: xG {xg.xg:.1f} | xGA {xg.xga:.1f} | "
                f"Big chances {xg.big_chances_created}/{xg.big_chances_conceded}. "
                f"Shot quality {xg.shot_quality:.2f} | Conversion {xg.conversion_rate:.0%}. "
                f"Defensive efficiency {xg.defensive_efficiency:.0%}. "
                f"Verdict: {xg.luck_label}"
            )

        if context.home_xg and context.away_xg:
            home_net = context.home_xg.xg - context.home_xg.xga
            away_net = context.away_xg.xg - context.away_xg.xga
            if "Underrated" in context.home_xg.luck_label:
                lines.append(f"Value signal: {context.home_team} underlying metrics exceed market perception.")
            if "Overrated" in context.away_xg.luck_label:
                lines.append(f"Fade signal: {context.away_team} results exceed sustainable xG profile.")
            if home_net > away_net + 0.5:
                lines.append("xG edge: Home side creating significantly better chances.")
            elif away_net > home_net + 0.5:
                lines.append("xG edge: Away side superior chance quality.")

        return "\n".join(lines) if lines else "xG data unavailable for this fixture."

    def xg_probability_adjustment(self, context: MatchContext) -> tuple[float, float, float]:
        """Return (home, draw, away) probability adjustments from xG."""
        if not context.home_xg or not context.away_xg:
            return (0.0, 0.0, 0.0)

        home_net = context.home_xg.xg - context.home_xg.xga
        away_net = context.away_xg.xg - context.away_xg.xga
        diff = home_net - away_net

        home_adj = max(-0.1, min(0.1, diff * 0.04))
        away_adj = -home_adj * 0.7
        draw_adj = -home_adj * 0.3
        return (home_adj, draw_adj, away_adj)
