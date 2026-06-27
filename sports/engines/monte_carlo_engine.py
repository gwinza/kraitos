"""Monte Carlo simulation engine — probabilistic match outcomes."""

from __future__ import annotations

import numpy as np

from sports.models import MatchContext, MonteCarloResult, Sport


class MonteCarloEngine:
    """Run thousands of simulations for outcome distributions."""

    SIMULATIONS = 10000

    def analyze(
        self,
        context: MatchContext,
        *,
        home_base: float,
        draw_base: float,
        away_base: float,
    ) -> MonteCarloResult:
        rng = np.random.default_rng(hash(context.match_id) % (2**32))

        if context.sport in (Sport.TENNIS, Sport.MMA, Sport.BASKETBALL, Sport.CRICKET):
            return self._two_way_simulation(rng, home_base, away_base)

        return self._three_way_simulation(rng, home_base, draw_base, away_base)

    def _three_way_simulation(
        self,
        rng: np.random.Generator,
        home_base: float,
        draw_base: float,
        away_base: float,
    ) -> MonteCarloResult:
        total = home_base + draw_base + away_base
        home_p, draw_p, away_p = home_base / total, draw_base / total, away_base / total

        home_lambda = max(0.3, home_p * 2.8)
        away_lambda = max(0.3, away_p * 2.8)

        home_goals = rng.poisson(home_lambda, self.SIMULATIONS)
        away_goals = rng.poisson(away_lambda, self.SIMULATIONS)

        home_wins = np.mean(home_goals > away_goals)
        draws = np.mean(home_goals == away_goals)
        away_wins = np.mean(home_goals < away_goals)
        over_25 = np.mean(home_goals + away_goals > 2.5)
        btts = np.mean((home_goals > 0) & (away_goals > 0))

        scores: dict[str, int] = {}
        for h, a in zip(home_goals[:2000], away_goals[:2000]):
            key = f"{h}-{a}"
            scores[key] = scores.get(key, 0) + 1
        top_scores = tuple(
            sorted(
                ((k, v / 2000) for k, v in scores.items()),
                key=lambda x: x[1],
                reverse=True,
            )[:5]
        )

        return MonteCarloResult(
            home_win=float(home_wins),
            draw=float(draws),
            away_win=float(away_wins),
            over_25=float(over_25),
            btts=float(btts),
            top_scores=top_scores,
            simulations=self.SIMULATIONS,
        )

    def _two_way_simulation(
        self,
        rng: np.random.Generator,
        home_base: float,
        away_base: float,
    ) -> MonteCarloResult:
        total = home_base + away_base
        home_p = home_base / total
        outcomes = rng.random(self.SIMULATIONS) < home_p
        home_wins = float(np.mean(outcomes))
        away_wins = 1.0 - home_wins

        return MonteCarloResult(
            home_win=home_wins,
            draw=0.0,
            away_win=away_wins,
            over_25=0.5,
            btts=0.0,
            top_scores=(),
            simulations=self.SIMULATIONS,
        )
