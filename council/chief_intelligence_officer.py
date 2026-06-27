"""Chief Intelligence Officer — central reasoning engine for Kraitos V3."""

from __future__ import annotations

from council.cognitive_models import (
    ALLOCATION_TIERS,
    CIODecision,
    CognitiveThesis,
    CouncilObservation,
    DeliberationMessage,
    ExecutionStrategy,
    HardVeto,
    MarketUnderstanding,
    TradeSideHint,
)
from council.cognitive_context import MarketCognitiveContext
from council.council_memory import CouncilMemory


class ChiefIntelligenceOfficer:
    """
    Fuses council evidence into one coherent thesis.

    Does not count votes — reasons about regime-weighted evidence,
    resolves conflicts, and maps confidence to capital allocation.
    """

    def __init__(self, memory: CouncilMemory | None = None) -> None:
        self._memory = memory

    def reason(
        self,
        context: MarketCognitiveContext,
        observations: tuple[CouncilObservation, ...],
        deliberation: tuple[DeliberationMessage, ...],
    ) -> CIODecision:
        regime = context.regime_label
        weights = self._regime_weights(observations, regime)
        hard_vetoes = self._hard_vetoes(context, observations)

        bullish_score = 0.0
        bearish_score = 0.0
        weighted_conf = 0.0
        weighted_prob = 0.0
        weight_total = 0.0
        supporting: list[str] = []
        conflicts: list[str] = []

        for obs in observations:
            w = weights.get(obs.council, 1.0) * obs.weight_hint
            weighted_conf += obs.confidence * w
            weighted_prob += obs.success_probability * w
            weight_total += w
            if obs.evidence:
                supporting.append(f"{obs.council}: {obs.evidence[0]}")
            if obs.direction == "bullish":
                bullish_score += obs.confidence * w
            elif obs.direction == "bearish":
                bearish_score += obs.confidence * w

        confidence = weighted_conf / max(weight_total, 0.01)
        success_probability = weighted_prob / max(weight_total, 0.01)

        side = self._resolve_side(bullish_score, bearish_score, observations)
        conflicts.extend(self._detect_conflicts(observations))

        expected_r = self._estimate_expected_r(context, success_probability)
        opportunity_quality = self._opportunity_quality(observations, confidence)
        risk_score = self._risk_score(observations, context)

        understanding = self._build_understanding(context, observations, side, deliberation)
        narrative = self._synthesise_narrative(observations, understanding)
        forecast = self._synthesise_forecast(observations, side, success_probability)

        thesis = CognitiveThesis(
            side=side,
            market_understanding=understanding,
            success_probability=success_probability,
            expected_reward_r=expected_r,
            confidence=confidence,
            opportunity_quality=opportunity_quality,
            risk_score=risk_score,
            narrative=narrative,
            forecast=forecast,
            conflicts=tuple(conflicts[:6]),
            supporting_evidence=tuple(supporting[:8]),
        )

        execution = self._execution_strategy(confidence, observations, hard_vetoes)
        can_trade = not hard_vetoes and execution.allocation_multiplier > 0
        observe_only = execution.mode in {"observe", "wait"} and execution.allocation_multiplier <= 0.12

        summary = (
            f"CIO: {side.upper()} | confidence {confidence:.0f}/100 | "
            f"P(success) {success_probability:.0%} | E[R] {expected_r:.2f} | "
            f"{execution.mode} @ {execution.allocation_multiplier:.0%} allocation"
        )
        if hard_vetoes:
            summary = f"CIO BLOCKED: {hard_vetoes[0].reason}"

        return CIODecision(
            symbol=context.symbol,
            thesis=thesis,
            execution=execution,
            hard_vetoes=hard_vetoes,
            deliberation=deliberation,
            council_observations=observations,
            regime=regime,
            can_trade=can_trade,
            observe_only=observe_only,
            summary=summary,
        )

    def _regime_weights(
        self,
        observations: tuple[CouncilObservation, ...],
        regime: str,
    ) -> dict[str, float]:
        weights: dict[str, float] = {}
        for obs in observations:
            if self._memory is not None:
                weights[obs.council] = self._memory.weight_for(obs.council, regime)
            else:
                weights[obs.council] = 1.0
        return weights

    def _hard_vetoes(
        self,
        context: MarketCognitiveContext,
        observations: tuple[CouncilObservation, ...],
    ) -> tuple[HardVeto, ...]:
        vetoes: list[HardVeto] = []
        if context.spread_pips > context.spread_limit:
            vetoes.append(
                HardVeto(
                    code="spread_excessive",
                    reason=(
                        f"Spread {context.spread_pips:.1f} pips exceeds "
                        f"limit {context.spread_limit:.1f} pips"
                    ),
                )
            )
        risk_obs = next((o for o in observations if o.council == "risk"), None)
        if risk_obs and "veto" in risk_obs.headline.lower():
            vetoes.append(HardVeto(code="risk_constraint", reason=risk_obs.headline))

        c = context.candidate
        if not c.pair_allowed:
            vetoes.append(HardVeto(code="pair_gated", reason="Pair trading not allowed"))
        if not c.news_allowed:
            vetoes.append(HardVeto(code="news_blackout", reason="News filter blocks trading"))

        return tuple(vetoes)

    def _resolve_side(
        self,
        bullish_score: float,
        bearish_score: float,
        observations: tuple[CouncilObservation, ...],
    ) -> TradeSideHint:
        margin = abs(bullish_score - bearish_score)
        if margin < 15:
            story = next((o for o in observations if o.council == "story"), None)
            if story and story.direction == "bullish":
                return "buy"
            if story and story.direction == "bearish":
                return "sell"
            return "observe"
        return "buy" if bullish_score > bearish_score else "sell"

    def _detect_conflicts(
        self,
        observations: tuple[CouncilObservation, ...],
    ) -> list[str]:
        conflicts: list[str] = []
        directional = [o for o in observations if o.direction in {"bullish", "bearish"}]
        bulls = [o for o in directional if o.direction == "bullish"]
        bears = [o for o in directional if o.direction == "bearish"]
        if bulls and bears:
            bull_names = ", ".join(o.council for o in bulls[:3])
            bear_names = ", ".join(o.council for o in bears[:3])
            conflicts.append(f"{bull_names} bullish vs {bear_names} bearish")
        exec_obs = next((o for o in observations if o.council == "execution"), None)
        trend_obs = next((o for o in observations if o.council == "trend"), None)
        if exec_obs and trend_obs:
            if "wait" in exec_obs.headline.lower() and trend_obs.confidence >= 70:
                conflicts.append("Trend confident but execution wants patience")
        return conflicts

    def _estimate_expected_r(
        self,
        context: MarketCognitiveContext,
        success_probability: float,
    ) -> float:
        c = context.candidate
        forecast = c.story_forecast
        if forecast is not None:
            edge = float(getattr(forecast, "expected_r", 0) or getattr(forecast, "expected_R", 0) or 0)
            if edge > 0:
                return round(edge * success_probability, 3)
        harvest = c.harvest_score
        if harvest is not None:
            score = float(getattr(harvest, "score", 50) or 50)
            return round((score / 100.0) * 1.5 * success_probability, 3)
        return round(1.0 * success_probability - (1 - success_probability), 3)

    def _opportunity_quality(
        self,
        observations: tuple[CouncilObservation, ...],
        confidence: float,
    ) -> float:
        story = next((o for o in observations if o.council == "story"), None)
        liquidity = next((o for o in observations if o.council == "liquidity"), None)
        base = confidence
        if story is not None:
            base = max(base, story.confidence)
        if liquidity is not None and "stop hunt" in liquidity.headline.lower():
            base = min(100.0, base + 8.0)
        return round(base, 2)

    def _risk_score(
        self,
        observations: tuple[CouncilObservation, ...],
        context: MarketCognitiveContext,
    ) -> float:
        spread_penalty = min(40.0, (context.spread_pips / max(context.spread_limit, 0.01)) * 20)
        vol = next((o for o in observations if o.council == "volatility"), None)
        vol_penalty = 0.0
        if vol is not None and "caution" in vol.headline.lower():
            vol_penalty = 15.0
        psychology = next((o for o in observations if o.council == "psychology"), None)
        psych_penalty = 0.0
        if psychology is not None and "reversal" in psychology.headline.lower():
            psych_penalty = 12.0
        return round(spread_penalty + vol_penalty + psych_penalty, 2)

    def _build_understanding(
        self,
        context: MarketCognitiveContext,
        observations: tuple[CouncilObservation, ...],
        side: TradeSideHint,
        deliberation: tuple[DeliberationMessage, ...],
    ) -> MarketUnderstanding:
        story = next((o for o in observations if o.council == "story"), None)
        trend = next((o for o in observations if o.council == "trend"), None)
        structure = next((o for o in observations if o.council == "liquidity"), None)
        order_flow = next((o for o in observations if o.council == "order_flow"), None)

        what = story.reasoning[:200] if story else "Market conditions being assessed."
        why = trend.reasoning[:200] if trend else "Causal drivers unclear."
        who = order_flow.headline if order_flow else "Control undetermined."
        liquidity = structure.headline if structure else "Liquidity location unknown."
        destination = story.forecasts[0] if story and story.forecasts else "Direction pending."
        smart_money = (
            deliberation[-1].message[:160]
            if deliberation
            else "Observe institutional footprint at key levels."
        )
        outcome = f"Highest probability: express {side} with sized conviction" if side != "observe" else "Observe — edge insufficient for capital deployment"

        return MarketUnderstanding(
            what_is_happening=what,
            why_it_is_happening=why,
            who_controls=who,
            liquidity_location=liquidity,
            price_destination=destination,
            smart_money_view=smart_money,
            highest_probability_outcome=outcome,
        )

    def _synthesise_narrative(
        self,
        observations: tuple[CouncilObservation, ...],
        understanding: MarketUnderstanding,
    ) -> str:
        parts = [understanding.what_is_happening]
        for obs in observations:
            if obs.confidence >= 60:
                parts.append(obs.headline)
        return " ".join(parts[:4])

    def _synthesise_forecast(
        self,
        observations: tuple[CouncilObservation, ...],
        side: TradeSideHint,
        success_probability: float,
    ) -> str:
        forecasts = [f for o in observations for f in o.forecasts if f]
        base = forecasts[0] if forecasts else "No dominant forecast."
        return f"{base} CIO assigns {success_probability:.0%} success probability to {side} expression."

    def _execution_strategy(
        self,
        confidence: float,
        observations: tuple[CouncilObservation, ...],
        hard_vetoes: tuple[HardVeto, ...],
    ) -> ExecutionStrategy:
        if hard_vetoes:
            return ExecutionStrategy(
                mode="observe",
                allocation_multiplier=0.0,
                timing_guidance="Do not trade — hard risk veto active.",
                entry_style="none",
                rationale=hard_vetoes[0].reason,
            )

        exec_obs = next((o for o in observations if o.council == "execution"), None)
        timing_guidance = exec_obs.headline if exec_obs else "Standard entry timing."
        entry_style = "confirmation"
        if exec_obs and "wait" in exec_obs.headline.lower():
            entry_style = "wait_for_confirmation"

        mode = "observe"
        multiplier = 0.0
        for threshold, tier_mode, tier_mult in ALLOCATION_TIERS:
            if confidence >= threshold:
                mode = tier_mode
                multiplier = tier_mult
                break

        if exec_obs and exec_obs.confidence < 40:
            mode = "wait"
            multiplier = min(multiplier, 0.12)
            timing_guidance = exec_obs.headline

        rationale = (
            f"Confidence {confidence:.0f}/100 maps to {mode} "
            f"({multiplier:.0%} allocation). {timing_guidance}"
        )
        return ExecutionStrategy(
            mode=mode,
            allocation_multiplier=multiplier,
            timing_guidance=timing_guidance,
            entry_style=entry_style,
            rationale=rationale,
        )
