"""Lower-league prediction engine — outcomes with transparent reasoning."""

from __future__ import annotations

from dataclasses import dataclass, field

from sports.lower_leagues import is_lower_league, league_tier
from sports.models import MatchContext, MonteCarloResult, ValueBetResult


@dataclass
class PredictionReason:
    """Single factor contributing to the prediction."""

    factor: str
    impact: str  # e.g. "Strongly favours home", "Supports draw"
    detail: str
    weight: float  # 0–1 relative importance

    def to_dict(self) -> dict:
        return {
            "factor": self.factor,
            "impact": self.impact,
            "detail": self.detail,
            "weight": round(self.weight, 2),
        }


@dataclass
class LowerLeaguePrediction:
    """Structured prediction with full explanation — not just a pick."""

    outcome: str
    outcome_probability: float
    confidence: float
    market_view: str
    model_view: str
    divergence: str
    summary: str
    reasons: tuple[PredictionReason, ...] = ()
    caveats: tuple[str, ...] = ()
    alternative_outcomes: tuple[tuple[str, float], ...] = ()

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "outcome_probability": round(self.outcome_probability, 3),
            "confidence": round(self.confidence, 1),
            "market_view": self.market_view,
            "model_view": self.model_view,
            "divergence": self.divergence,
            "summary": self.summary,
            "reasons": [r.to_dict() for r in self.reasons],
            "caveats": list(self.caveats),
            "alternative_outcomes": [
                {"outcome": o, "probability": round(p, 3)}
                for o, p in self.alternative_outcomes
            ],
        }


class LowerLeaguePredictionEngine:
    """
    Predict match outcomes for European 3rd/4th tier teams.

    Kraitos explains WHY — every prediction links to evidence, not table position alone.
    """

    TIER_DATA_PENALTY = {3: 5.0, 4: 10.0, 5: 15.0, 6: 20.0}

    def applies_to(self, context: MatchContext) -> bool:
        return is_lower_league(context.league)

    def predict(
        self,
        context: MatchContext,
        *,
        home_prob: float,
        draw_prob: float,
        away_prob: float,
        monte_carlo: MonteCarloResult | None,
        value_bet: ValueBetResult | None,
        team_strength_text: str,
        xg_text: str,
        form_text: str,
    ) -> LowerLeaguePrediction | None:
        if not self.applies_to(context):
            return None

        tier = league_tier(context.league) or 4
        reasons: list[PredictionReason] = []

        probs = {
            f"{context.home_team} Win": home_prob,
            "Draw": draw_prob,
            f"{context.away_team} Win": away_prob,
        }
        if monte_carlo:
            probs = {
                f"{context.home_team} Win": (home_prob + monte_carlo.home_win) / 2,
                "Draw": (draw_prob + monte_carlo.draw) / 2,
                f"{context.away_team} Win": (away_prob + monte_carlo.away_win) / 2,
            }

        outcome = max(probs, key=probs.get)
        outcome_prob = probs[outcome]

        reasons.extend(self._strength_reasons(context))
        reasons.extend(self._xg_reasons(context))
        reasons.extend(self._form_reasons(context))
        reasons.extend(self._context_reasons(context))
        reasons.extend(self._coach_reasons(context))

        if value_bet and value_bet.positive_ev:
            reasons.append(
                PredictionReason(
                    factor="Market mispricing",
                    impact=f"Value on {value_bet.selection}",
                    detail=(
                        f"Market implies {value_bet.market_probability:.0%} but model "
                        f"estimates {value_bet.fair_probability:.0%} ({value_bet.ev_pct:+.1f}% EV)."
                    ),
                    weight=0.25,
                )
            )

        market_implied = self._market_favourite(context)
        model_favourite = outcome
        divergence = self._divergence_note(market_implied, model_favourite, context)

        confidence = self._confidence(outcome_prob, tier, len(reasons))
        caveats = self._caveats(context, tier)

        alts = sorted(
            ((k, v) for k, v in probs.items() if k != outcome),
            key=lambda x: x[1],
            reverse=True,
        )

        summary = self._build_summary(
            context, outcome, outcome_prob, reasons, market_implied, divergence
        )

        return LowerLeaguePrediction(
            outcome=outcome,
            outcome_probability=outcome_prob,
            confidence=confidence,
            market_view=f"Market favourite: {market_implied}",
            model_view=f"Kraitos model: {outcome} ({outcome_prob:.0%})",
            divergence=divergence,
            summary=summary,
            reasons=tuple(sorted(reasons, key=lambda r: r.weight, reverse=True)[:8]),
            caveats=tuple(caveats),
            alternative_outcomes=tuple(alts),
        )

    def _strength_reasons(self, ctx: MatchContext) -> list[PredictionReason]:
        reasons: list[PredictionReason] = []
        if not ctx.home_profile or not ctx.away_profile:
            return reasons

        home = ctx.home_profile.squad_quality * (ctx.home_profile.full_strength_pct / 100)
        away = ctx.away_profile.squad_quality * (ctx.away_profile.full_strength_pct / 100)
        home -= len(ctx.home_profile.injuries) * 3 + len(ctx.home_profile.suspensions) * 4
        away -= len(ctx.away_profile.injuries) * 3 + len(ctx.away_profile.suspensions) * 4

        delta = home - away
        if abs(delta) >= 5:
            fav = ctx.home_team if delta > 0 else ctx.away_team
            reasons.append(
                PredictionReason(
                    factor="True squad strength",
                    impact=f"Favours {fav}",
                    detail=(
                        f"{ctx.home_team} adjusted strength {home:.0f}/100 vs "
                        f"{ctx.away_team} {away:.0f}/100. "
                        "Lower leagues often misprice league position vs available quality."
                    ),
                    weight=min(0.22, abs(delta) / 40),
                )
            )
        if ctx.away_profile.injuries or ctx.away_profile.suspensions:
            missing = ctx.away_profile.injuries + ctx.away_profile.suspensions
            reasons.append(
                PredictionReason(
                    factor="Availability",
                    impact=f"Favours {ctx.home_team}",
                    detail=f"{ctx.away_team} missing: {', '.join(missing)}.",
                    weight=0.12,
                )
            )
        return reasons

    def _xg_reasons(self, ctx: MatchContext) -> list[PredictionReason]:
        reasons: list[PredictionReason] = []
        if not ctx.home_xg or not ctx.away_xg:
            return reasons

        home_net = ctx.home_xg.xg - ctx.home_xg.xga
        away_net = ctx.away_xg.xg - ctx.away_xg.xga

        if "Underrated" in ctx.home_xg.luck_label:
            reasons.append(
                PredictionReason(
                    factor="xG profile (home)",
                    impact=f"Favours {ctx.home_team}",
                    detail=(
                        f"{ctx.home_team} xG {ctx.home_xg.xg:.1f} / xGA {ctx.home_xg.xga:.1f} — "
                        f"{ctx.home_xg.luck_label}. Results should catch up."
                    ),
                    weight=0.20,
                )
            )
        if "Overrated" in ctx.away_xg.luck_label or "Overrated" in ctx.away_xg.luck_label:
            reasons.append(
                PredictionReason(
                    factor="xG profile (away)",
                    impact=f"Fades {ctx.away_team}",
                    detail=(
                        f"{ctx.away_team} xG {ctx.away_xg.xg:.1f} / xGA {ctx.away_xg.xga:.1f} — "
                        f"{ctx.away_xg.luck_label}."
                    ),
                    weight=0.18,
                )
            )
        if home_net > away_net + 0.4:
            reasons.append(
                PredictionReason(
                    factor="Chance quality differential",
                    impact=f"Favours {ctx.home_team}",
                    detail=f"Home net xG +{home_net:.1f} vs away +{away_net:.1f}.",
                    weight=0.15,
                )
            )
        return reasons

    def _form_reasons(self, ctx: MatchContext) -> list[PredictionReason]:
        reasons: list[PredictionReason] = []
        for team, form, venue in (
            (ctx.home_team, ctx.home_form, "home"),
            (ctx.away_team, ctx.away_form, "away"),
        ):
            if not form:
                continue
            venue_form = form.home_form if venue == "home" else form.away_form
            wins = venue_form.count("W")
            if wins >= 3:
                reasons.append(
                    PredictionReason(
                        factor=f"{venue.title()} form",
                        impact=f"Supports {team}",
                        detail=f"{team} {venue} form: {venue_form}. {form.trend_label}",
                        weight=0.10,
                    )
                )
            if "False" in form.trend_label:
                reasons.append(
                    PredictionReason(
                        factor="Form sustainability",
                        impact=f"Question {team} results",
                        detail=form.trend_label,
                        weight=0.08,
                    )
                )
        return reasons

    def _context_reasons(self, ctx: MatchContext) -> list[PredictionReason]:
        reasons: list[PredictionReason] = []
        for factor in ctx.context_factors:
            lower = factor.lower()
            if any(k in lower for k in ("travel", "trip", "km", "fatigue", "congestion")):
                reasons.append(
                    PredictionReason(
                        factor="Travel / fatigue",
                        impact=f"Favours {ctx.home_team}",
                        detail=factor,
                        weight=0.10,
                    )
                )
            if any(k in lower for k in ("promotion", "relegation", "title")):
                reasons.append(
                    PredictionReason(
                        factor="Motivation",
                        impact="Elevates variance",
                        detail=factor,
                        weight=0.08,
                    )
                )
            if "misprice" in lower or "thin" in lower or "sparse" in lower:
                reasons.append(
                    PredictionReason(
                        factor="Market structure",
                        impact="Edge opportunity",
                        detail=factor,
                        weight=0.12,
                    )
                )
        return reasons

    def _coach_reasons(self, ctx: MatchContext) -> list[PredictionReason]:
        if not ctx.home_coach:
            return []
        perf = ctx.home_coach.home_overperformance + ctx.home_coach.historical_overperformance
        if perf > 0.12:
            return [
                PredictionReason(
                    factor="Coach overperformance",
                    impact=f"Favours {ctx.home_team}",
                    detail=(
                        f"{ctx.home_coach.name}: {ctx.home_coach.tactical_style}. "
                        f"Home overperformance {ctx.home_coach.home_overperformance:+.0%}."
                    ),
                    weight=0.10,
                )
            ]
        return []

    def _market_favourite(self, ctx: MatchContext) -> str:
        if not ctx.bookmaker_odds:
            return "Unknown"
        ref = ctx.bookmaker_odds[0]
        if ref.draw:
            probs = {
                ctx.home_team: 1 / ref.home,
                "Draw": 1 / ref.draw,
                ctx.away_team: 1 / (ref.away or 99),
            }
            return max(probs, key=probs.get)
        home_p = 1 / ref.home
        away_p = 1 / (ref.away or 99)
        return ctx.home_team if home_p > away_p else ctx.away_team

    def _divergence_note(self, market: str, model: str, ctx: MatchContext) -> str:
        model_team = model.replace(" Win", "")
        if market == model_team or market in model:
            return "Model aligns with market favourite — edge must come from odds price, not outcome."
        return (
            f"Model disagrees with market: books favour {market}, "
            f"Kraitos prefers {model}. Lower-league mispricing opportunity."
        )

    def _confidence(self, prob: float, tier: int, reason_count: int) -> float:
        base = prob * 70 + min(reason_count, 6) * 4
        base -= self.TIER_DATA_PENALTY.get(tier, 10)
        return max(35.0, min(88.0, base))

    def _caveats(self, ctx: MatchContext, tier: int) -> list[str]:
        caveats = [
            "Lower-league data is sparser — confidence capped vs top-flight analysis.",
            "Kraitos predicts probabilities and edges, not certainties.",
        ]
        if tier >= 4:
            caveats.append(
                f"Tier {tier} league — liquidity limited; verify odds across multiple books."
            )
        if any("sparse" in f.lower() or "pass" in f.lower() for f in ctx.context_factors):
            caveats.append("Internal flags suggest caution on this fixture.")
        return caveats

    def _build_summary(
        self,
        ctx: MatchContext,
        outcome: str,
        prob: float,
        reasons: list[PredictionReason],
        market: str,
        divergence: str,
    ) -> str:
        top = sorted(reasons, key=lambda r: r.weight, reverse=True)[:3]
        because = "; ".join(r.detail.split(".")[0] for r in top) if top else "balanced metrics"

        return (
            f"Kraitos predicts {outcome} ({prob:.0%} model probability) in "
            f"{ctx.league}. Primary reasons: {because}. "
            f"{divergence} "
            f"This is a probability assessment — combine with edge score before acting."
        )
