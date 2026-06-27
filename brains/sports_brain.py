"""Sports Brain — orchestrates all Kraitos Sports intelligence engines."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import uuid

from sports.engines import (
    ArbitrageEngine,
    BayesianLiveEngine,
    CoachIntelligenceEngine,
    DeepMatchIntelligenceEngine,
    ExplainabilityEngine,
    FormAnalysisEngine,
    LowerLeaguePredictionEngine,
    MarketIntelligenceEngine,
    MonteCarloEngine,
    MultiAgentCouncil,
    OpportunityRanker,
    PortfolioIntelligenceEngine,
    RedTeamEngine,
    ReinforcementHarvester,
    TeamStrengthEngine,
    ValueBettingEngine,
    XGEngine,
)
from sports.alerts import EdgeAlert, EdgeAlertService
from sports.lower_leagues import is_lower_league, league_tier
from sports.fixtures_service import FixturesService
from sports.models import (
    Decision,
    MatchAnalysis,
    MatchContext,
    OpportunityGrade,
    Sport,
    SportsBrainStats,
)


class SportsBrain:
    """
    Kraitos Sports intelligence orchestrator.

    Philosophy: Kraitos does not pick winners. Kraitos finds edges.
    Golden Rule: Data → Probability → Value → Risk → Decision
    """

    PHILOSOPHY = "Kraitos does not pick winners. Kraitos finds edges."

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[1]
        self.fixtures = FixturesService()
        self.arbitrage = ArbitrageEngine()
        self.value = ValueBettingEngine()
        self.team_strength = TeamStrengthEngine()
        self.coach = CoachIntelligenceEngine()
        self.form = FormAnalysisEngine()
        self.xg = XGEngine()
        self.market = MarketIntelligenceEngine()
        self.context_engine = DeepMatchIntelligenceEngine()
        self.monte_carlo = MonteCarloEngine()
        self.live = BayesianLiveEngine()
        self.rl = ReinforcementHarvester(self.project_root)
        self.council = MultiAgentCouncil()
        self.red_team = RedTeamEngine()
        self.portfolio = PortfolioIntelligenceEngine()
        self.explain = ExplainabilityEngine()
        self.lower_league = LowerLeaguePredictionEngine()
        self.ranker = OpportunityRanker()
        self.stats = SportsBrainStats()
        self.alerts = EdgeAlertService(self.project_root)

    def refresh_fixtures(self) -> int:
        """Reload live odds + demo fixtures."""
        return self.fixtures.refresh()

    def scan_with_alerts(
        self,
        *,
        sport: Sport | None = None,
        league: str | None = None,
    ) -> tuple[list[MatchAnalysis], list[EdgeAlert]]:
        analyses = self.scan_and_analyze(sport=sport, league=league)
        alerts = self.alerts.process(analyses)
        return analyses, alerts

    def scan_lower_leagues(
        self,
        *,
        tier_min: int = 3,
        tier_max: int = 4,
    ) -> list[MatchAnalysis]:
        """Analyse European 3rd/4th tier fixtures with prediction explanations."""
        fixtures = self.fixtures.scan_lower_league(tier_min=tier_min, tier_max=tier_max)
        analyses = [self.evaluate(ctx) for ctx in fixtures]
        return self.ranker.sort_analyses(analyses)

    def scan_and_analyze(
        self,
        *,
        sport: Sport | None = None,
        league: str | None = None,
    ) -> list[MatchAnalysis]:
        """Continuous match scanner — analyse all upcoming fixtures."""
        fixtures = self.fixtures.scan_upcoming(sport=sport, league=league)
        analyses = [self.evaluate(ctx) for ctx in fixtures]
        return self.ranker.sort_analyses(analyses)

    def evaluate(self, context: MatchContext) -> MatchAnalysis:
        """Full intelligence pipeline for one match."""
        self.stats.matches_scanned += 1
        weights = self.rl.get_weights()

        team_text = self.team_strength.analyze(context)
        coach_text = self.coach.analyze(context)
        form_text = self.form.analyze(context)
        xg_text = self.xg.analyze(context)
        market_text = self.market.analyze(context)
        context_text, context_factors = self.context_engine.analyze(context)

        home_p, draw_p, away_p = self._base_probabilities(context, weights)

        if context.is_live:
            home_p, draw_p, away_p, live_note = self.live.analyze(
                context, pre_home=home_p, pre_draw=draw_p, pre_away=away_p
            )
            market_text = f"{market_text}\n{live_note}"

        mc = self.monte_carlo.analyze(
            context, home_base=home_p, draw_base=draw_p, away_base=away_p
        )
        home_p = home_p * 0.4 + mc.home_win * 0.6
        draw_p = draw_p * 0.4 + mc.draw * 0.6
        away_p = away_p * 0.4 + mc.away_win * 0.6
        total = home_p + draw_p + away_p
        home_p, draw_p, away_p = home_p / total, draw_p / total, away_p / total

        value_results = self.value.analyze(
            context, home_prob=home_p, draw_prob=draw_p, away_prob=away_p
        )
        best_value = self.value.best_value(value_results)
        arb = self.arbitrage.analyze(context)

        context_risk = self.context_engine.context_risk_penalty(context)
        preliminary_edge = (
            (best_value.value_score if best_value else 0)
            + (arb.profit_pct * 5 if arb.detected else 0)
        )

        council = self.council.analyze(
            context,
            team_strength=team_text,
            coach_analysis=coach_text,
            form_analysis=form_text,
            xg_analysis=xg_text,
            market_intelligence=market_text,
            context_summary=context_text,
            value_bet=best_value,
            arbitrage=arb,
            edge_score=preliminary_edge,
            risk_penalty=context_risk,
        )

        analysis = MatchAnalysis(
            match_id=context.match_id,
            sport=context.sport,
            league=context.league,
            home_team=context.home_team,
            away_team=context.away_team,
            kickoff=context.kickoff,
            trace_id=context.trace_id or str(uuid.uuid4())[:8],
            recommended_market=best_value.market if best_value else None,
            value_bet=best_value,
            arbitrage=arb,
            team_strength=team_text,
            coach_analysis=coach_text,
            form_analysis=form_text,
            xg_analysis=xg_text,
            market_intelligence=market_text,
            context_factors=context_factors,
            monte_carlo=mc,
            council=council,
        )

        analysis = self.ranker.rank(
            analysis,
            value_bet=best_value,
            arbitrage=arb,
            council_confidence=council.confidence,
            context_risk=context_risk,
        )

        red = self.red_team.analyze(
            context,
            value_bet=best_value,
            arbitrage=arb,
            edge_score=analysis.edge_score,
            confidence=analysis.confidence,
            council_edge=council.edge_detected,
        )
        analysis.red_team = red

        if not red.approved and analysis.decision not in (Decision.ARBITRAGE,):
            analysis.decision = Decision.PASS
            analysis.pass_reason = "PASS — Capital Preservation Mode Activated."
            analysis.grade = OpportunityGrade.PASS

        analysis.is_lower_league = is_lower_league(context.league)
        analysis.league_tier = league_tier(context.league)
        if analysis.is_lower_league:
            prediction = self.lower_league.predict(
                context,
                home_prob=home_p,
                draw_prob=draw_p,
                away_prob=away_p,
                monte_carlo=mc,
                value_bet=best_value,
                team_strength_text=team_text,
                xg_text=xg_text,
                form_text=form_text,
            )
            if prediction:
                analysis.prediction = prediction.outcome
                analysis.prediction_confidence = prediction.confidence
                analysis.prediction_reasoning = prediction.summary
                analysis.prediction_detail = prediction.to_dict()

        analysis.reasoning_summary = self._build_reasoning(
            analysis, best_value, arb, context
        )
        analysis.explainability = self.explain.build(analysis)
        analysis.portfolio_notes = self.portfolio.analyze(analysis)

        if analysis.decision == Decision.PASS:
            self.stats.passes += 1
        elif analysis.decision == Decision.ARBITRAGE:
            self.stats.arbitrage_found += 1
            self.stats.edges_found += 1
        elif analysis.decision in (Decision.VALUE_BET, Decision.WATCHLIST):
            self.stats.edges_found += 1

        self._write_report(analysis)
        return analysis

    def _base_probabilities(
        self, context: MatchContext, weights
    ) -> tuple[float, float, float]:
        home_adv = self.context_engine.home_advantage(context)
        strength_delta = self.team_strength.strength_delta(context) / 100
        coach_adj = self.coach.coach_adjustment(context) * weights.coach
        form_adj = self.form.form_adjustment(context) * weights.form
        xg_adj = self.xg.xg_probability_adjustment(context)
        xg_home = xg_adj[0] * weights.xg

        home = 0.33 + home_adv + strength_delta * 0.3 + coach_adj + form_adj + xg_home
        away = 0.33 - strength_delta * 0.3 - coach_adj - form_adj + xg_adj[2] * weights.xg
        draw = max(0.15, 1.0 - home - away) if context.sport == Sport.SOCCER else 0.0

        if context.sport != Sport.SOCCER:
            total = home + away
            home, away = home / total, away / total
            draw = 0.0
        else:
            total = home + draw + away
            home, draw, away = home / total, draw / total, away / total

        return home, draw, away

    def _build_reasoning(self, analysis, best_value, arb, context=None) -> str:
        base = ""
        if analysis.decision == Decision.PASS:
            base = (
                f"{analysis.pass_reason} After analysing team strength, form, xG, "
                f"market intelligence, Monte Carlo simulations, and council consensus, "
                f"no edge clear enough to risk capital."
            )
        elif analysis.decision == Decision.ARBITRAGE:
            base = (
                f"Cross-bookmaker arbitrage detected with {arb.profit_pct:.2f}% margin. "
                f"Stake allocation covers all outcomes profitably. "
                f"Execute {arb.execution_speed.lower()} before line correction."
            )
        elif best_value:
            base = (
                f"Kraitos model estimates {best_value.fair_probability:.0%} true probability "
                f"vs market implied {best_value.market_probability:.0%} on {best_value.selection}. "
                f"Expected value {best_value.ev_pct:+.1f}%. Edge score {analysis.edge_score:.0f}/100. "
                f"Red team: {analysis.red_team.summary if analysis.red_team else 'N/A'}"
            )
        else:
            base = "Watchlist — marginal signal detected. Monitor for line movement."

        if analysis.prediction_reasoning:
            base = f"{analysis.prediction_reasoning}\n\nBetting decision: {base}"
        return base

    def _write_report(self, analysis: MatchAnalysis) -> None:
        report_dir = self.project_root / "logs"
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / f"sports_{analysis.match_id}.md"
        lines = [
            f"# Kraitos Sports — {analysis.match_label}",
            "",
            f"**Philosophy:** {self.PHILOSOPHY}",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            "",
            f"## Decision: {analysis.decision.value}",
            f"**Edge Score:** {analysis.edge_score}/100 | **Confidence:** {analysis.confidence}/100",
            f"**Grade:** {analysis.grade.value} | **Risk:** {analysis.risk_level.value}",
            "",
            "## Reasoning",
            analysis.reasoning_summary,
            "",
        ]
        if analysis.prediction:
            lines.extend([
                "## Prediction",
                f"**Outcome:** {analysis.prediction} ({analysis.prediction_confidence:.0f}% confidence)",
                "",
                analysis.prediction_reasoning,
                "",
            ])
        lines.extend([
            "## Team Strength",
            analysis.team_strength,
            "",
            "## Council",
            analysis.council.consensus if analysis.council else "N/A",
        ])
        path.write_text("\n".join(lines), encoding="utf-8")
