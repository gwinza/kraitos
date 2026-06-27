"""Deep match intelligence — hidden contextual factors."""

from __future__ import annotations

from sports.models import MatchContext, Sport


class DeepMatchIntelligenceEngine:
    """Evaluate motivation, fixture congestion, rivalries, and pressure."""

    SPORT_HOME_ADVANTAGE = {
        Sport.SOCCER: 0.08,
        Sport.BASKETBALL: 0.05,
        Sport.TENNIS: 0.0,
        Sport.RUGBY: 0.06,
        Sport.CRICKET: 0.04,
        Sport.BASEBALL: 0.04,
        Sport.AMERICAN_FOOTBALL: 0.06,
        Sport.ICE_HOCKEY: 0.05,
        Sport.MMA: 0.0,
        Sport.ESPORTS: 0.02,
    }

    def analyze(self, context: MatchContext) -> tuple[str, tuple[str, ...]]:
        factors = list(context.context_factors)
        lines = [f"• {f}" for f in factors]

        motivation_keywords = ("title", "relegation", "promotion", "playoff", "qualification")
        high_stakes = any(
            any(kw in f.lower() for kw in motivation_keywords) for f in factors
        )
        if high_stakes:
            lines.append("High-stakes context — motivation asymmetry possible.")
        else:
            lines.append("Standard motivation levels — rely on quantitative edges.")

        congestion = any("congestion" in f.lower() or "back-to-back" in f.lower() for f in factors)
        if congestion:
            lines.append("Fixture congestion flagged — fatigue may suppress favourites.")

        rivalry = any("rivalry" in f.lower() or "derby" in f.lower() or "klassiker" in f.lower() for f in factors)
        if rivalry:
            lines.append("Rivalry match — elevated variance; reduce stake sizing.")

        weather = next((f for f in factors if "weather" in f.lower() or "dew" in f.lower()), None)
        if weather:
            lines.append(f"Environmental factor: {weather}")

        return "\n".join(lines), tuple(factors)

    def home_advantage(self, context: MatchContext) -> float:
        return self.SPORT_HOME_ADVANTAGE.get(context.sport, 0.05)

    def context_risk_penalty(self, context: MatchContext) -> float:
        penalty = 0.0
        for factor in context.context_factors:
            lower = factor.lower()
            if any(k in lower for k in ("rivalry", "derby", "variance")):
                penalty += 5.0
            if any(k in lower for k in ("congestion", "fatigue", "back-to-back")):
                penalty += 3.0
        return min(20.0, penalty)
