"""Value betting engine — fair probability vs market implied probability."""

from __future__ import annotations

from sports.models import BetMarket, BookmakerOdds, MatchContext, ValueBetResult


class ValueBettingEngine:
    """Calculate true probabilities and compare with market odds."""

    MIN_EV_PCT = 3.0

    def analyze(
        self,
        context: MatchContext,
        *,
        home_prob: float,
        draw_prob: float,
        away_prob: float,
    ) -> list[ValueBetResult]:
        if not context.bookmaker_odds:
            return []

        reference = self._best_odds(context.bookmaker_odds)
        results: list[ValueBetResult] = []

        if reference.draw is not None:
            results.extend(
                self._evaluate_outcome(
                    selection=f"{context.home_team} Win",
                    fair_prob=home_prob,
                    market_odds=reference.home,
                    market=BetMarket.MATCH_WINNER,
                )
            )
            results.extend(
                self._evaluate_outcome(
                    selection="Draw",
                    fair_prob=draw_prob,
                    market_odds=reference.draw,
                    market=BetMarket.MATCH_WINNER,
                )
            )
            results.extend(
                self._evaluate_outcome(
                    selection=f"{context.away_team} Win",
                    fair_prob=away_prob,
                    market_odds=reference.away or 1.0,
                    market=BetMarket.MATCH_WINNER,
                )
            )
        else:
            results.extend(
                self._evaluate_outcome(
                    selection=f"{context.home_team} Win",
                    fair_prob=home_prob,
                    market_odds=reference.home,
                    market=BetMarket.MATCH_WINNER,
                )
            )
            results.extend(
                self._evaluate_outcome(
                    selection=f"{context.away_team} Win",
                    fair_prob=away_prob,
                    market_odds=reference.away or 1.0,
                    market=BetMarket.MATCH_WINNER,
                )
            )

        if reference.over and reference.line:
            over_prob = self._estimate_over_prob(home_prob, draw_prob, away_prob)
            results.extend(
                self._evaluate_outcome(
                    selection=f"Over {reference.line}",
                    fair_prob=over_prob,
                    market_odds=reference.over,
                    market=BetMarket.OVER_UNDER,
                )
            )

        return sorted(results, key=lambda r: r.ev_pct, reverse=True)

    def best_value(self, results: list[ValueBetResult]) -> ValueBetResult | None:
        positive = [r for r in results if r.positive_ev]
        return positive[0] if positive else None

    def _best_odds(self, odds_list: tuple[BookmakerOdds, ...]) -> BookmakerOdds:
        return BookmakerOdds(
            bookmaker="Market Best",
            home=max(o.home for o in odds_list),
            draw=max((o.draw for o in odds_list if o.draw), default=None),
            away=max((o.away for o in odds_list if o.away), default=None),
            over=max((o.over for o in odds_list if o.over), default=None),
            under=max((o.under for o in odds_list if o.under), default=None),
            line=next((o.line for o in odds_list if o.line), None),
        )

    def _evaluate_outcome(
        self,
        *,
        selection: str,
        fair_prob: float,
        market_odds: float,
        market: BetMarket,
    ) -> list[ValueBetResult]:
        if market_odds <= 1.0 or fair_prob <= 0:
            return []

        market_prob = 1 / market_odds
        fair_odds = 1 / fair_prob if fair_prob > 0 else 999.0
        ev_pct = ((fair_prob * market_odds) - 1) * 100
        edge = fair_prob - market_prob
        value_score = min(100.0, max(0.0, edge * 200 + ev_pct * 2))
        confidence = min(100.0, 40 + abs(edge) * 120 + (ev_pct * 1.5))

        return [
            ValueBetResult(
                fair_odds=fair_odds,
                market_odds=market_odds,
                fair_probability=fair_prob,
                market_probability=market_prob,
                ev_pct=ev_pct,
                value_score=value_score,
                confidence=confidence,
                market=market,
                selection=selection,
                positive_ev=ev_pct >= self.MIN_EV_PCT,
            )
        ]

    def _estimate_over_prob(
        self, home_prob: float, draw_prob: float, away_prob: float
    ) -> float:
        attack_strength = home_prob * 0.55 + away_prob * 0.55 + draw_prob * 0.25
        return min(0.85, max(0.15, attack_strength * 0.9 + 0.15))
