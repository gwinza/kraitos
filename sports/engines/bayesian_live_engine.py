"""Bayesian live betting engine — dynamic in-play probability updates."""

from __future__ import annotations

from sports.models import MatchContext, ValueBetResult


class BayesianLiveEngine:
    """Update probabilities during live matches using match events."""

    def analyze(
        self,
        context: MatchContext,
        *,
        pre_home: float,
        pre_draw: float,
        pre_away: float,
    ) -> tuple[float, float, float, str]:
        if not context.is_live:
            return pre_home, pre_draw, pre_away, "Pre-match probabilities — live engine standby."

        stats = context.live_stats
        home = pre_home
        draw = pre_draw
        away = pre_away
        notes: list[str] = ["Live Bayesian update active."]

        possession = stats.get("possession", 50)
        home += (possession - 50) * 0.001
        away -= (possession - 50) * 0.001
        notes.append(f"Possession {possession}% — adjusted win rates.")

        xg_home = stats.get("xg_home", 0.0)
        xg_away = stats.get("xg_away", 0.0)
        xg_diff = xg_home - xg_away
        home += xg_diff * 0.05
        away -= xg_diff * 0.05
        notes.append(f"xG live: {xg_home:.1f} - {xg_away:.1f}.")

        if stats.get("red_card_home"):
            home -= 0.15
            away += 0.10
            draw += 0.05
            notes.append("Red card (home) — significant probability shift.")
        if stats.get("red_card_away"):
            away -= 0.15
            home += 0.10
            draw += 0.05
            notes.append("Red card (away) — significant probability shift.")

        score_home = stats.get("score_home", 0)
        score_away = stats.get("score_away", 0)
        if score_home > score_away:
            home += 0.08
            away -= 0.06
        elif score_away > score_home:
            away += 0.08
            home -= 0.06

        total = home + draw + away
        if total <= 0:
            return pre_home, pre_draw, pre_away, "Normalization failed — using pre-match."

        return (
            max(0.01, home / total),
            max(0.01, draw / total),
            max(0.01, away / total),
            " ".join(notes),
        )

    def live_value_check(
        self,
        context: MatchContext,
        live_probs: tuple[float, float, float],
        market_odds: tuple[float, float | None, float],
    ) -> ValueBetResult | None:
        from sports.engines.value_betting_engine import ValueBettingEngine
        from sports.models import BetMarket

        home_p, draw_p, away_p = live_probs
        home_odds, draw_odds, away_odds = market_odds

        engine = ValueBettingEngine()
        best_ev = -999.0
        best: ValueBetResult | None = None

        for prob, odds, selection in (
            (home_p, home_odds, f"{context.home_team} Live"),
            (away_p, away_odds, f"{context.away_team} Live"),
        ):
            if odds <= 1:
                continue
            ev = (prob * odds - 1) * 100
            if ev > best_ev and ev >= engine.MIN_EV_PCT:
                best_ev = ev
                best = ValueBetResult(
                    fair_odds=1 / prob,
                    market_odds=odds,
                    fair_probability=prob,
                    market_probability=1 / odds,
                    ev_pct=ev,
                    value_score=min(100, ev * 3),
                    confidence=60,
                    market=BetMarket.LIVE,
                    selection=selection,
                    positive_ev=True,
                )
        return best
