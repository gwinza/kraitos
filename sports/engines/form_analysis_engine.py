"""Form analysis engine — momentum, trends, and false streak detection."""

from __future__ import annotations

from sports.models import MatchContext


class FormAnalysisEngine:
    """Track recent form and identify sustainable vs unsustainable runs."""

    def analyze(self, context: MatchContext) -> str:
        lines: list[str] = []

        for label, form in (
            (context.home_team, context.home_form),
            (context.away_team, context.away_form),
        ):
            if not form:
                continue
            lines.append(
                f"{label}: L5={form.last_5} | L10={form.last_10} | "
                f"Home={form.home_form} | Away={form.away_form}. "
                f"Momentum: {form.momentum}. {form.trend_label}"
            )
            lines.append(f"  Goal trend: {form.goal_trend}")

        if context.home_form and context.away_form:
            home_wins = context.home_form.last_5.count("W")
            away_wins = context.away_form.last_5.count("W")
            if "False" in context.home_form.trend_label:
                lines.append(f"⚠ {context.home_team} form may be misleading — investigate xG backing.")
            if "False" in context.away_form.trend_label:
                lines.append(f"⚠ {context.away_team} form may be misleading — results exceed underlying metrics.")
            if home_wins >= 4 and away_wins <= 1:
                lines.append("Form divergence: Strong home momentum vs struggling away side.")
            elif away_wins >= 4 and home_wins <= 1:
                lines.append("Form divergence: Away side in superior recent form.")

        return "\n".join(lines) if lines else "Form data unavailable."

    def form_adjustment(self, context: MatchContext) -> float:
        if not context.home_form or not context.away_form:
            return 0.0
        home_score = context.home_form.last_5.count("W") * 0.02
        away_score = context.away_form.last_5.count("W") * 0.02
        if "False" in context.home_form.trend_label:
            home_score *= 0.5
        if "False" in context.away_form.trend_label:
            away_score *= 0.5
        return max(-0.06, min(0.06, home_score - away_score))
