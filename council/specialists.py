"""Twelve specialist councils — parallel evidence, no gatekeeping."""

from __future__ import annotations

from abc import ABC, abstractmethod

from council.cognitive_context import MarketCognitiveContext
from council.cognitive_models import CouncilObservation, CouncilName, DirectionBias
from intelligence.harvest_opportunity_score import infer_session


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _direction_from_label(label: str) -> DirectionBias:
    normalized = label.strip().lower()
    if normalized in {"bullish", "buy", "long"}:
        return "bullish"
    if normalized in {"bearish", "sell", "short"}:
        return "bearish"
    return "neutral"


class SpecialistCouncil(ABC):
    """Base class for cognitive specialist councils."""

    name: CouncilName

    @abstractmethod
    def analyze(self, context: MarketCognitiveContext) -> CouncilObservation:
        """Produce evidence from current market state."""


class StoryCouncil(SpecialistCouncil):
    name = "story"

    def analyze(self, context: MarketCognitiveContext) -> CouncilObservation:
        c = context.candidate
        story = c.market_story
        forecast = c.story_forecast
        brain = c.brain_story
        if story is None and brain is None:
            return CouncilObservation(
                council=self.name,
                headline="No narrative yet",
                reasoning="Story engines have not produced a market narrative.",
                direction="neutral",
                confidence=20.0,
                success_probability=0.35,
            )
        direction = "neutral"
        confidence = 40.0
        narrative = "Market narrative unavailable."
        forecast_text = "Direction unclear."
        evidence: list[str] = []
        if story is not None:
            direction = _direction_from_label(getattr(story, "direction", "neutral"))
            confidence = float(getattr(story, "overall_confidence", 40) or 40)
            narrative = getattr(story, "primary_story", narrative)[:240]
            if getattr(story, "story_clear", False):
                evidence.append("Story is clear and actionable")
        if forecast is not None:
            forecast_text = getattr(forecast, "expected_next_move", forecast_text)
            opp = getattr(forecast, "opportunity_type", None)
            if opp:
                evidence.append(f"Story opportunity: {opp}")
        if brain is not None:
            brain_dir = getattr(brain, "direction", "neutral")
            if brain_dir != "neutral":
                direction = _direction_from_label(brain_dir)
            brain_conf = float(getattr(brain, "confidence", 0) or 0) * 100
            confidence = max(confidence, brain_conf)
            evidence.append(getattr(brain, "narrative", "")[:120])
        prob = _clamp(confidence) / 100.0 * 0.85
        return CouncilObservation(
            council=self.name,
            headline=f"Story reads {direction} ({confidence:.0f}/100)",
            reasoning=narrative,
            direction=direction,
            confidence=_clamp(confidence),
            success_probability=prob,
            evidence=tuple(evidence[:4]),
            forecasts=(forecast_text,),
        )


class TrendCouncil(SpecialistCouncil):
    name = "trend"

    def analyze(self, context: MarketCognitiveContext) -> CouncilObservation:
        c = context.candidate
        bias = c.bias
        tq = c.trend_quality
        asset = c.asset_trend
        direction: DirectionBias = "neutral"
        confidence = 35.0
        evidence: list[str] = []
        if bias is not None:
            direction = _direction_from_label(bias.bias)
            confidence = float(bias.confidence) * 100
            evidence.append(f"MTF bias {bias.bias} ({bias.confidence:.2f})")
        if tq is not None:
            t_dir = getattr(tq, "trend_direction", "neutral")
            t_score = float(getattr(tq, "trend_quality_score", 50) or 50)
            cont = float(getattr(tq, "continuation_probability", 0.5) or 0.5)
            if t_dir != "neutral":
                direction = _direction_from_label(t_dir)
            confidence = max(confidence, t_score)
            evidence.append(
                f"Trend quality {t_score:.0f}/100, continuation {cont:.0%}"
            )
        if asset is not None:
            snap_dir = getattr(asset, "direction", None) or getattr(asset, "trend", None)
            if snap_dir:
                direction = _direction_from_label(str(snap_dir))
                evidence.append(f"Asset trend: {snap_dir}")
        headline = f"I remain {direction}." if direction != "neutral" else "Trend is mixed."
        return CouncilObservation(
            council=self.name,
            headline=headline,
            reasoning=" | ".join(evidence) if evidence else "Insufficient trend data.",
            direction=direction,
            confidence=_clamp(confidence),
            success_probability=_clamp(confidence) / 100.0 * 0.80,
            evidence=tuple(evidence[:4]),
            forecasts=(f"Trend continuation bias: {direction}",),
        )


class StructureCouncil(SpecialistCouncil):
    name = "structure"

    def analyze(self, context: MarketCognitiveContext) -> CouncilObservation:
        c = context.candidate
        structure = c.structure
        if structure is None:
            return CouncilObservation(
                council=self.name,
                headline="Structure unknown",
                reasoning="No structure analysis available.",
                direction="neutral",
                confidence=25.0,
                success_probability=0.30,
            )
        direction = _direction_from_label(structure.trend)
        evidence: list[str] = [f"Structure trend: {structure.trend}"]
        confidence = 55.0
        if structure.higher_highs and structure.higher_lows:
            direction = "bullish"
            confidence = 72.0
            evidence.append("Higher highs and higher lows")
        elif structure.lower_highs and structure.lower_lows:
            direction = "bearish"
            confidence = 72.0
            evidence.append("Lower highs and lower lows")
        if structure.last_bos:
            evidence.append(f"Break of structure: {structure.last_bos}")
        if structure.last_choch:
            evidence.append(f"Change of character: {structure.last_choch}")
        zones = len(structure.support_zones) + len(structure.resistance_zones)
        if zones:
            evidence.append(f"{zones} active structure zones mapped")
        return CouncilObservation(
            council=self.name,
            headline=f"Structure supports {direction} control",
            reasoning="; ".join(evidence),
            direction=direction,
            confidence=_clamp(confidence),
            success_probability=_clamp(confidence) / 100.0 * 0.82,
            evidence=tuple(evidence[:5]),
            forecasts=(f"Structure favours {direction} continuation unless invalidated",),
        )


class LiquidityCouncil(SpecialistCouncil):
    name = "liquidity"

    def analyze(self, context: MarketCognitiveContext) -> CouncilObservation:
        c = context.candidate
        structure = c.structure
        harvest = c.harvest
        sweep = c.liquidity_sweep
        rng = c.range_intelligence
        direction: DirectionBias = "neutral"
        confidence = 45.0
        evidence: list[str] = []
        headline = "Liquidity map is inconclusive."
        if structure is not None and structure.liquidity_zones:
            evidence.append(f"{len(structure.liquidity_zones)} liquidity pools active")
            headline = "Liquidity pools mapped — watch for sweep reactions."
        if sweep is not None:
            swept = getattr(sweep, "swept", False) or getattr(sweep, "detected", False)
            if swept:
                headline = "A stop hunt has just completed below support."
                direction = "bullish"
                confidence = 68.0
                evidence.append("Liquidity sweep detected — stop hunt likely complete")
        if harvest is not None and harvest.allowed:
            evidence.append(f"Harvest path: {getattr(harvest, 'reason', 'edge detected')[:80]}")
            confidence = max(confidence, 58.0)
        if rng is not None:
            support = getattr(rng, "support_level", None)
            resistance = getattr(rng, "resistance_level", None)
            location = getattr(rng, "price_location", "")
            if support and resistance:
                evidence.append(f"Range {support:.5f}–{resistance:.5f}, location={location}")
            likely = getattr(rng, "likely_breakout_direction", None)
            if likely:
                direction = _direction_from_label(str(likely))
        return CouncilObservation(
            council=self.name,
            headline=headline,
            reasoning=" | ".join(evidence) if evidence else "No liquidity edge identified.",
            direction=direction,
            confidence=_clamp(confidence),
            success_probability=_clamp(confidence) / 100.0 * 0.78,
            evidence=tuple(evidence[:4]),
            forecasts=("Price likely seeks nearest resting liquidity next",),
        )


class VolumeCouncil(SpecialistCouncil):
    name = "volume"

    def analyze(self, context: MarketCognitiveContext) -> CouncilObservation:
        c = context.candidate
        interp = c.indicator_interpretation
        narrative = c.market_narrative
        direction: DirectionBias = "neutral"
        confidence = 42.0
        evidence: list[str] = []
        headline = "Volume is inconclusive."
        if interp is not None:
            vol_state = getattr(interp, "volume_state", None) or getattr(interp, "volume_signal", "")
            insight = float(getattr(interp, "insight_score", 50) or 50)
            confidence = max(confidence, insight)
            if vol_state:
                evidence.append(f"Volume state: {vol_state}")
                if "weak" in str(vol_state).lower():
                    headline = "Volume is weak."
                elif "strong" in str(vol_state).lower():
                    headline = "Volume confirms participation."
            flow = getattr(interp, "flow_direction", None)
            if flow:
                direction = _direction_from_label(str(flow))
        if narrative is not None:
            vol_note = getattr(narrative, "volume_narrative", None) or getattr(
                narrative, "volume_story", None
            )
            if vol_note:
                evidence.append(str(vol_note)[:120])
        return CouncilObservation(
            council=self.name,
            headline=headline,
            reasoning=" | ".join(evidence) if evidence else "Volume flow not assessed.",
            direction=direction,
            confidence=_clamp(confidence),
            success_probability=_clamp(confidence) / 100.0 * 0.70,
            evidence=tuple(evidence[:3]),
            forecasts=("Weak volume after sweeps often precedes continuation once accepted",),
        )


class VolatilityCouncil(SpecialistCouncil):
    name = "volatility"

    def analyze(self, context: MarketCognitiveContext) -> CouncilObservation:
        c = context.candidate
        regime = c.regime
        mri = c.market_regime_intelligence
        confidence = 50.0
        evidence: list[str] = []
        direction: DirectionBias = "neutral"
        if regime is not None:
            evidence.append(f"Regime: {regime.regime} ({regime.confidence:.2f})")
            confidence = max(confidence, float(regime.confidence) * 100)
        if mri is not None:
            current = getattr(mri, "market_regime", None) or getattr(mri, "current_regime", "")
            breakout_risk = float(getattr(mri, "breakout_risk_score", 50) or 50)
            compression = float(getattr(mri, "compression_probability", 0) or 0)
            evidence.append(f"Market regime {current}, breakout risk {breakout_risk:.0f}/100")
            if compression > 0.5:
                evidence.append(f"Compression building ({compression:.0%})")
            strategy = getattr(mri, "strategy_bias", "")
            if strategy:
                evidence.append(f"Strategy bias: {strategy}")
        headline = "Volatility supports measured participation."
        if regime is not None and regime.regime in {"low_liquidity", "high_volatility"}:
            headline = f"Volatility caution — {regime.regime}."
            confidence = min(confidence, 55.0)
        return CouncilObservation(
            council=self.name,
            headline=headline,
            reasoning=" | ".join(evidence) if evidence else "Volatility context unavailable.",
            direction=direction,
            confidence=_clamp(confidence),
            success_probability=_clamp(confidence) / 100.0 * 0.72,
            evidence=tuple(evidence[:4]),
            forecasts=("Expect expansion after compression or fade in extreme vol",),
        )


class OrderFlowCouncil(SpecialistCouncil):
    name = "order_flow"

    def analyze(self, context: MarketCognitiveContext) -> CouncilObservation:
        c = context.candidate
        scalp = c.scalping_intelligence
        micro = c.micro_scalp
        direction: DirectionBias = "neutral"
        confidence = 40.0
        evidence: list[str] = []
        if scalp is not None:
            micro_trend = getattr(scalp, "micro_trend_state", "")
            micro_struct = getattr(scalp, "micro_structure_state", "")
            quality = float(getattr(scalp, "scalp_quality_score", 50) or 50)
            expectancy = float(getattr(scalp, "scalp_expectancy_score", 50) or 50)
            confidence = max(confidence, (quality + expectancy) / 2)
            evidence.append(f"Micro trend={micro_trend}, structure={micro_struct}")
            evidence.append(f"Scalp quality {quality:.0f}, expectancy {expectancy:.0f}")
            if "bullish" in str(micro_trend).lower() or "bullish" in str(micro_struct).lower():
                direction = "bullish"
            elif "bearish" in str(micro_trend).lower() or "bearish" in str(micro_struct).lower():
                direction = "bearish"
            action = getattr(scalp, "suggested_action", "")
            if action:
                evidence.append(f"Suggested micro action: {action}")
        if micro is not None and micro.action in {"buy", "sell"}:
            direction = _direction_from_label(micro.action)
            evidence.append(f"M1 momentum: {micro.action} — {micro.reason[:80]}")
            confidence = max(confidence, 62.0)
        headline = f"Order flow leans {direction}." if direction != "neutral" else "Order flow is balanced."
        return CouncilObservation(
            council=self.name,
            headline=headline,
            reasoning=" | ".join(evidence) if evidence else "Micro order flow not assessed.",
            direction=direction,
            confidence=_clamp(confidence),
            success_probability=_clamp(confidence) / 100.0 * 0.75,
            evidence=tuple(evidence[:4]),
            forecasts=("Micro control likely persists until VWAP/structure reclaim fails",),
        )


class SessionCouncil(SpecialistCouncil):
    name = "session"

    def analyze(self, context: MarketCognitiveContext) -> CouncilObservation:
        hour = 12
        if context.evaluation_moment is not None:
            hour = context.evaluation_moment.hour
        session = context.session_label
        if session == "unknown":
            session = infer_session(hour)
        si = context.candidate.session_intelligence
        confidence = 55.0
        evidence = [f"Session bucket: {session} (UTC hour {hour})"]
        headline = f"Session context: {session.replace('_', ' ')}."
        if si is not None:
            quality = float(getattr(si, "session_quality_score", 55) or 55)
            confidence = quality
            phase = getattr(si, "session_phase", None)
            if phase:
                evidence.append(f"Phase: {phase}")
        favourable = session in {"london", "london_ny_overlap", "new_york"}
        if not favourable:
            confidence = min(confidence, 48.0)
            headline = f"Thin session ({session}) — reduce urgency."
        return CouncilObservation(
            council=self.name,
            headline=headline,
            reasoning=" | ".join(evidence),
            direction="neutral",
            confidence=_clamp(confidence),
            success_probability=_clamp(confidence) / 100.0 * 0.65,
            evidence=tuple(evidence),
            forecasts=(f"Best liquidity typically during London/NY overlap, not {session}",),
        )


class PsychologyCouncil(SpecialistCouncil):
    name = "psychology"

    def analyze(self, context: MarketCognitiveContext) -> CouncilObservation:
        c = context.candidate
        lifecycle = c.market_lifecycle
        reversal = c.reversal_pressure
        tq = c.trend_quality
        direction: DirectionBias = "neutral"
        confidence = 45.0
        evidence: list[str] = []
        if tq is not None:
            phase = getattr(tq, "trend_phase", "")
            rev_prob = float(getattr(tq, "reversal_probability", 0) or 0)
            cont_prob = float(getattr(tq, "continuation_probability", 0.5) or 0.5)
            evidence.append(f"Phase={phase}, reversal {rev_prob:.0%}, continuation {cont_prob:.0%}")
            confidence = max(confidence, float(getattr(tq, "trend_quality_score", 45) or 45))
            if rev_prob > cont_prob:
                direction = "bearish" if getattr(tq, "trend_direction", "") == "bullish" else "bullish"
        if reversal is not None:
            score = float(getattr(reversal, "reversal_pressure_score", 0) or 0)
            evidence.append(f"Reversal pressure {score:.2f}")
        if lifecycle is not None:
            phase = getattr(lifecycle, "current_phase", None)
            if phase:
                evidence.append(f"Lifecycle phase: {phase}")
        headline = "Market psychology is balanced."
        if evidence and "reversal" in evidence[0].lower():
            headline = "Psychology warns of exhaustion or reversal risk."
        return CouncilObservation(
            council=self.name,
            headline=headline,
            reasoning=" | ".join(evidence) if evidence else "Psychology not assessed.",
            direction=direction,
            confidence=_clamp(confidence),
            success_probability=_clamp(confidence) / 100.0 * 0.68,
            evidence=tuple(evidence[:4]),
            forecasts=("Crowded positioning often resolves via liquidity sweep then continuation",),
        )


class MemoryCouncil(SpecialistCouncil):
    name = "memory"

    def analyze(self, context: MarketCognitiveContext) -> CouncilObservation:
        c = context.candidate
        archetype = c.archetype_check
        harvest_score = c.harvest_score
        confidence = 50.0
        evidence: list[str] = []
        direction: DirectionBias = "neutral"
        if archetype is not None:
            allowed = getattr(archetype, "allowed", True)
            mult = float(getattr(archetype, "risk_multiplier", 1.0) or 1.0)
            evidence.append(f"Archetype memory: allowed={allowed}, risk mult={mult:.2f}")
            confidence = 65.0 if allowed else 35.0
        if harvest_score is not None:
            band = getattr(harvest_score, "band", "")
            score = float(getattr(harvest_score, "score", 50) or 50)
            evidence.append(f"Historical harvest score {score:.0f} ({band})")
            confidence = max(confidence, score)
        if c.council_consensus is not None:
            cc = c.council_consensus
            evidence.append(
                f"Prior council confidence {cc.consensus_confidence:.0f}/100 — {cc.consensus_narrative[:80]}"
            )
        headline = "Memory supports current setup quality."
        if archetype is not None and not getattr(archetype, "allowed", True):
            headline = "Memory warns this archetype has underperformed recently."
            confidence = 38.0
        return CouncilObservation(
            council=self.name,
            headline=headline,
            reasoning=" | ".join(evidence) if evidence else "Insufficient memory context.",
            direction=direction,
            confidence=_clamp(confidence),
            success_probability=_clamp(confidence) / 100.0 * 0.70,
            evidence=tuple(evidence[:3]),
            forecasts=("Historically weak volume after stop hunts often precedes continuation",),
        )


class RiskCouncil(SpecialistCouncil):
    """Only council that may recommend hard vetoes — objective constraints only."""

    name = "risk"

    def analyze(self, context: MarketCognitiveContext) -> CouncilObservation:
        spread_ratio = context.spread_pips / max(context.spread_limit, 0.01)
        confidence = 70.0
        evidence: list[str] = []
        if spread_ratio > 1.0:
            evidence.append(f"Spread {context.spread_pips:.1f} pips exceeds limit {context.spread_limit:.1f}")
            confidence = 25.0
        else:
            evidence.append(f"Spread acceptable ({context.spread_pips:.1f}/{context.spread_limit:.1f} pips)")
        allocation = context.candidate.opportunity_allocation
        if allocation is not None:
            evidence.append(f"Opportunity allocation posture available")
        headline = "Risk constraints within limits."
        if spread_ratio > 1.0:
            headline = "Risk veto — spread too wide for execution."
        return CouncilObservation(
            council=self.name,
            headline=headline,
            reasoning=" | ".join(evidence),
            direction="neutral",
            confidence=_clamp(confidence),
            success_probability=0.5 if spread_ratio <= 1.0 else 0.1,
            evidence=tuple(evidence),
            forecasts=("Capital preservation overrides opportunity when costs dominate edge",),
            weight_hint=1.5 if spread_ratio > 1.0 else 1.0,
        )


class ExecutionCouncil(SpecialistCouncil):
    name = "execution"

    def analyze(self, context: MarketCognitiveContext) -> CouncilObservation:
        c = context.candidate
        eq = c.execution_quality
        timing = c.timing_quality
        maturity = c.trade_maturity
        patience = c.patience_decision
        direction: DirectionBias = "neutral"
        confidence = 50.0
        evidence: list[str] = []
        timing_score = 50.0
        if eq is not None:
            timing_score = float(getattr(eq, "timing_score", 50) or 50)
            exec_score = float(getattr(eq, "execution_score", 50) or 50)
            confidence = max(confidence, exec_score)
            style = getattr(eq, "entry_style", "standard")
            evidence.append(f"Execution {exec_score:.0f}/100, style={style}, timing {timing_score:.0f}")
        if timing is not None:
            tq = float(getattr(timing, "timing_quality_score", timing_score) or timing_score)
            timing_score = tq
            evidence.append(getattr(timing, "explanation", "")[:100])
        if maturity is not None:
            stage = getattr(maturity, "maturity_stage", "")
            commit = getattr(maturity, "commitment", "")
            evidence.append(f"Maturity {getattr(maturity, 'maturity_score', 0)}/100 ({stage}, {commit})")
            confidence = max(confidence, float(getattr(maturity, "maturity_score", 50) or 50))
        headline = "Execution timing acceptable."
        if timing_score < 35:
            headline = "Wait for one confirmation candle then execute."
        elif timing_score >= 75:
            headline = "Timing is favourable — express conviction on confirmation."
        if patience is not None and not getattr(patience, "ready", True):
            headline = "Wait for professional entry location before executing."
        return CouncilObservation(
            council=self.name,
            headline=headline,
            reasoning=" | ".join(evidence) if evidence else "Execution quality not assessed.",
            direction=direction,
            confidence=_clamp(confidence),
            success_probability=_clamp(timing_score) / 100.0 * 0.85,
            evidence=tuple(evidence[:4]),
            forecasts=(headline,),
        )


ALL_SPECIALIST_COUNCILS: tuple[SpecialistCouncil, ...] = (
    StoryCouncil(),
    TrendCouncil(),
    StructureCouncil(),
    LiquidityCouncil(),
    VolumeCouncil(),
    VolatilityCouncil(),
    OrderFlowCouncil(),
    SessionCouncil(),
    PsychologyCouncil(),
    MemoryCouncil(),
    RiskCouncil(),
    ExecutionCouncil(),
)
