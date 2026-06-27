"""Portfolio intelligence engine — exposure and bankroll management."""

from __future__ import annotations

from dataclasses import dataclass, field

from sports.models import MatchAnalysis


@dataclass
class PortfolioState:
    daily_exposure_pct: float = 0.0
    sport_exposure: dict[str, float] = field(default_factory=dict)
    league_exposure: dict[str, float] = field(default_factory=dict)
    open_positions: int = 0
    daily_limit_pct: float = 10.0
    sport_limit_pct: float = 5.0
    league_limit_pct: float = 3.0
    max_open: int = 8


class PortfolioIntelligenceEngine:
    """Treat betting as portfolio management — control concentration risk."""

    def analyze(
        self,
        analysis: MatchAnalysis,
        portfolio: PortfolioState | None = None,
    ) -> str:
        state = portfolio or PortfolioState()
        lines: list[str] = []

        if analysis.decision.value == "Pass":
            return "Portfolio: No action — capital preserved."

        sport_key = analysis.sport.value
        league_key = analysis.league
        sport_exp = state.sport_exposure.get(sport_key, 0.0)
        league_exp = state.league_exposure.get(league_key, 0.0)

        suggested_stake = self._suggested_stake(analysis)
        lines.append(f"Suggested stake: {suggested_stake:.1f}% of bankroll (Kelly-adjusted).")

        if state.daily_exposure_pct + suggested_stake > state.daily_limit_pct:
            lines.append(
                f"⚠ Daily limit breach risk: {state.daily_exposure_pct:.1f}% + "
                f"{suggested_stake:.1f}% > {state.daily_limit_pct}% limit."
            )

        if sport_exp + suggested_stake > state.sport_limit_pct:
            lines.append(f"⚠ {sport_key} concentration limit approached.")

        if league_exp + suggested_stake > state.league_limit_pct:
            lines.append(f"⚠ {league_key} league exposure limit approached.")

        if state.open_positions >= state.max_open:
            lines.append(f"⚠ Max open positions ({state.max_open}) reached.")

        if analysis.risk_level.value == "High":
            lines.append("High risk — halve suggested stake.")

        lines.append("Correlation: Avoid stacking correlated legs in same match window.")
        return "\n".join(lines)

    def _suggested_stake(self, analysis: MatchAnalysis) -> float:
        if analysis.edge_score < 50:
            return 0.0
        base = min(2.5, analysis.edge_score / 40)
        if analysis.grade.value in ("A+", "A"):
            base *= 1.2
        if analysis.risk_level.value == "High":
            base *= 0.5
        elif analysis.risk_level.value == "Low":
            base *= 1.1
        return round(base, 2)

    def filter_opportunities(
        self,
        analyses: list[MatchAnalysis],
        portfolio: PortfolioState | None = None,
    ) -> list[MatchAnalysis]:
        """Remove opportunities that breach portfolio limits."""
        state = portfolio or PortfolioState()
        approved: list[MatchAnalysis] = []
        for analysis in analyses:
            if analysis.decision.value == "Pass":
                approved.append(analysis)
                continue
            stake = self._suggested_stake(analysis)
            if state.daily_exposure_pct + stake <= state.daily_limit_pct:
                approved.append(analysis)
            else:
                analysis.decision = analysis.decision  # keep but note in portfolio
                analysis.portfolio_notes = "Portfolio limit — downgrade to watchlist."
        return approved
