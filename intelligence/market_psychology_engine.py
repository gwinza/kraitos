"""Market Psychology Engine — infer participant emotions, never filter trades."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from intelligence.evidence_synthesis_engine import EvidencePiece
from intelligence.indicator_interpretation_engine import (
    FORBIDDEN_OUTPUT,
    IndicatorInterpretation,
    IndicatorInterpretationEngine,
    PsychologicalReading,
)

if TYPE_CHECKING:
    from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult

MARKET_PSYCHOLOGY_DNA = """
Markets are driven by people.
Indicators reveal psychology.

Kraitos infers fear, greed, euphoria, panic, uncertainty, accumulation,
distribution, confidence, hesitation, and exhaustion from RSI, MACD, ADX,
volume, OBV, accumulation/distribution, ATR, Bollinger Bands, price action,
and candlesticks.

Psychology improves understanding — it never filters, vetoes, or refuses trades.
Understanding expands opportunities.
""".strip()

PRIMARY_TIMEFRAME = "H1"
PSYCHOLOGY_TIMEFRAMES = ("H8", "H4", "H1", "M15", "M5", "M1")

INFERRED_EMOTIONS = (
    "fear",
    "greed",
    "euphoria",
    "panic",
    "uncertainty",
    "accumulation",
    "distribution",
    "confidence",
    "hesitation",
    "exhaustion",
)

CONVICTION_LEVELS = ("strong", "moderate", "weak", "contested")
PARTICIPATION_QUALITIES = (
    "strong_sponsorship",
    "mixed",
    "thin",
    "stealth_accumulation",
    "distribution_pressure",
)
CONFIDENCE_SHIFTS = ("strengthening", "stable", "weakening", "fading")

VALID_OPPORTUNITY_EXPANSIONS = frozenset({
    "contrarian_snapback",
    "momentum_continuation",
    "compression_release",
    "accumulation_breakout",
    "exhaustion_pause",
    "panic_capitulation_bounce",
    "distribution_fade",
    "hesitation_break",
})


@dataclass(frozen=True)
class PsychologyState:
    """Synthesised participant psychology — enrichment only."""

    dominant_emotion: str
    conviction_level: str
    participation_quality: str
    confidence_shift: str
    emotional_extremes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "dominant_emotion": self.dominant_emotion,
            "conviction_level": self.conviction_level,
            "participation_quality": self.participation_quality,
            "confidence_shift": self.confidence_shift,
            "emotional_extremes": list(self.emotional_extremes),
        }


@dataclass(frozen=True)
class MarketPsychologyResult:
    """Full market psychology read for one symbol."""

    symbol: str
    psychology_state: PsychologyState
    emotion_scores: dict[str, float]
    narrative: str
    observations: tuple[str, ...]
    opportunity_expansion: tuple[str, ...]
    insight_score: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "psychology_state": self.psychology_state.to_dict(),
            "emotion_scores": {k: round(v, 1) for k, v in self.emotion_scores.items()},
            "narrative": self.narrative,
            "observations": list(self.observations),
            "opportunity_expansion": list(self.opportunity_expansion),
            "insight_score": round(self.insight_score, 2),
        }

    def to_evidence_pieces(self) -> list[EvidencePiece]:
        state = self.psychology_state
        pieces = [
            EvidencePiece(
                category="market_psychology",
                timeframe=PRIMARY_TIMEFRAME,
                signal="dominant_emotion",
                description=f"Dominant emotion: {state.dominant_emotion}",
                direction=_emotion_direction(state.dominant_emotion),
                strength=_dominant_strength(self.emotion_scores, state.dominant_emotion),
            ),
            EvidencePiece(
                category="market_psychology",
                timeframe=PRIMARY_TIMEFRAME,
                signal="conviction",
                description=f"Conviction {state.conviction_level}, participation {state.participation_quality}",
                direction="neutral",
                strength=_conviction_strength(state.conviction_level),
            ),
            EvidencePiece(
                category="market_psychology",
                timeframe=PRIMARY_TIMEFRAME,
                signal="confidence_shift",
                description=f"Confidence {state.confidence_shift}",
                direction=_shift_direction(state.confidence_shift),
                strength=55.0,
            ),
        ]
        for extreme in state.emotional_extremes[:3]:
            if extreme != state.dominant_emotion:
                pieces.append(EvidencePiece(
                    category="market_psychology",
                    timeframe=PRIMARY_TIMEFRAME,
                    signal=f"extreme_{extreme}",
                    description=f"Emotional extreme: {extreme}",
                    direction=_emotion_direction(extreme),
                    strength=_dominant_strength(self.emotion_scores, extreme),
                ))
        return pieces


@dataclass
class PsychologyStats:
    """Accumulated inference metrics for reporting."""

    inferred: int = 0
    opportunity_expansions_emitted: int = 0
    evidence_pieces_added: int = 0


class MarketPsychologyEngine:
    """
    Infer market psychology from indicator evidence.

    Enriches understanding — never creates trades or refuses them.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self._interpreter = IndicatorInterpretationEngine(project_root)
        self._latest: dict[str, MarketPsychologyResult] = {}
        self.stats = PsychologyStats()

    def infer(
        self,
        *,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        regime: RegimeResult | None = None,
        indicator_interpretation: IndicatorInterpretation | None = None,
        narrative_direction: str = "neutral",
    ) -> MarketPsychologyResult:
        symbol = symbol.strip().upper()
        if indicator_interpretation is None:
            indicator_interpretation = self._interpreter.interpret(
                symbol=symbol,
                candles=candles,
                structure=structure,
                bias=bias,
                regime=regime,
                narrative_direction=narrative_direction,
            )

        scores = _score_emotions(indicator_interpretation.psychological_readings)
        state = _build_psychology_state(scores, indicator_interpretation.psychological_readings)
        expansions = _derive_opportunity_expansion(state, scores, indicator_interpretation)
        observations = _build_observations(state, indicator_interpretation.psychological_readings)
        narrative = _build_narrative(state, scores)
        insight = _compute_insight_score(state, scores, expansions)

        result = MarketPsychologyResult(
            symbol=symbol,
            psychology_state=state,
            emotion_scores=scores,
            narrative=narrative,
            observations=tuple(observations),
            opportunity_expansion=tuple(expansions),
            insight_score=insight,
        )
        self._latest[symbol] = result
        self.stats.inferred += 1
        self.stats.opportunity_expansions_emitted += len(expansions)
        self.stats.evidence_pieces_added += len(result.to_evidence_pieces())
        return result

    def write_market_psychology_engine_report(self, path: Path | None = None) -> Path | None:
        if not self._latest or self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "market_psychology_engine_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Market Psychology Engine Report",
            "",
            f"**Generated:** {now}",
            "",
            "Participant psychology inferred from indicators — never signals or vetoes.",
            "",
            f"- Inferred: **{self.stats.inferred}**",
            f"- Opportunity expansions: **{self.stats.opportunity_expansions_emitted}**",
            f"- Evidence pieces added: **{self.stats.evidence_pieces_added}**",
            "",
        ]
        for sym in sorted(self._latest):
            result = self._latest[sym]
            state = result.psychology_state
            lines.extend([
                f"## {sym}",
                "",
                f"**Dominant emotion:** {state.dominant_emotion}",
                f"**Conviction:** {state.conviction_level} | "
                f"**Participation:** {state.participation_quality} | "
                f"**Confidence shift:** {state.confidence_shift}",
                "",
                f"**Narrative:** {result.narrative}",
                "",
                "**Emotional extremes:**",
                "",
            ])
            for extreme in state.emotional_extremes:
                lines.append(f"- {extreme} ({result.emotion_scores.get(extreme, 0):.0f})")
            lines.append("")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_emotion_landscape_report(self, path: Path | None = None) -> Path | None:
        if not self._latest or self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "emotion_landscape_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Emotion Landscape Report",
            "",
            f"**Generated:** {now}",
            "",
            "Emotion score landscape across inferred states.",
            "",
        ]
        for sym in sorted(self._latest):
            result = self._latest[sym]
            lines.extend([f"## {sym}", "", "| Emotion | Score |", "|---------|-------|"])
            for emotion in INFERRED_EMOTIONS:
                lines.append(f"| {emotion} | {result.emotion_scores.get(emotion, 0):.0f} |")
            lines.extend(["", "**Opportunity expansion:**", ""])
            for hint in result.opportunity_expansion:
                lines.append(f"- {hint}")
            lines.append("")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_all_reports(self) -> tuple[Path | None, Path | None]:
        return (
            self.write_market_psychology_engine_report(),
            self.write_emotion_landscape_report(),
        )


def _score_emotions(readings: tuple[PsychologicalReading, ...]) -> dict[str, float]:
    scores = {emotion: 12.0 for emotion in INFERRED_EMOTIONS}
    for reading in readings:
        blob = f"{reading.reading} {reading.psychology}".lower()
        weight = max(0.5, reading.strength / 50.0)

        if reading.indicator == "RSI":
            _boost(scores, "euphoria", 35, "euphoria" in blob, weight)
            _boost(scores, "greed", 30, "greed" in blob or "optimism" in blob, weight)
            _boost(scores, "exhaustion", 28, "stretch" in blob or "exhaustion" in blob, weight)
            _boost(scores, "panic", 35, "panic" in blob, weight)
            _boost(scores, "fear", 30, "fear" in blob, weight)
            _boost(scores, "confidence", 15, "balanced" in blob or "neutral" in blob, weight * 0.5)

        elif reading.indicator == "MACD":
            _boost(scores, "confidence", 32, "accelerating" in blob, weight)
            _boost(scores, "hesitation", 28, "fading" in blob or "flat" in blob, weight)
            _boost(scores, "exhaustion", 20, "losing steam" in blob or "easing" in blob, weight)

        elif reading.indicator == "ADX":
            _boost(scores, "confidence", 30, "strong" in blob or "conviction" in blob, weight)
            _boost(scores, "uncertainty", 32, "weak" in blob or "contested" in blob, weight)
            _boost(scores, "hesitation", 22, "emerging" in blob, weight * 0.7)

        elif reading.indicator == "Volume":
            _boost(scores, "confidence", 25, "spike" in blob or "confirms" in blob, weight)
            _boost(scores, "hesitation", 22, "quiet" in blob or "apathy" in blob, weight)
            _boost(scores, "uncertainty", 18, "mixed" in blob, weight)

        elif reading.indicator == "OBV":
            _boost(scores, "accumulation", 35, "accumulation" in blob, weight)
            _boost(scores, "distribution", 35, "distribution" in blob, weight)
            _boost(scores, "uncertainty", 20, "mixed" in blob, weight)

        elif reading.indicator == "Accumulation/Distribution":
            _boost(scores, "accumulation", 38, "accumulating" in blob or "accumulation" in blob, weight)
            _boost(scores, "distribution", 38, "distribut" in blob, weight)

        elif reading.indicator == "ATR":
            _boost(scores, "panic", 22, "expanding" in blob, weight * 0.8)
            _boost(scores, "euphoria", 18, "expanding" in blob and reading.direction == "bullish", weight * 0.8)
            _boost(scores, "hesitation", 26, "compressing" in blob or "coiling" in blob, weight)

        elif reading.indicator == "Bollinger Bands":
            _boost(scores, "euphoria", 30, "upper" in blob or "greed" in blob, weight)
            _boost(scores, "greed", 25, "greed" in blob or "stretch" in blob, weight)
            _boost(scores, "fear", 28, "lower" in blob or "fear" in blob, weight)
            _boost(scores, "hesitation", 24, "compressed" in blob or "coiled" in blob, weight)

        elif reading.indicator == "Price Action":
            _boost(scores, "confidence", 22, "impulse" in blob or "conviction" in blob, weight)
            _boost(scores, "hesitation", 24, "range-bound" in blob, weight)
            _boost(scores, "exhaustion", 20, "rejection" in blob, weight)

        elif reading.indicator == "Candlesticks":
            _boost(scores, "confidence", 28, "engulfing" in blob or "took control" in blob, weight)
            _boost(scores, "hesitation", 26, "inside bar" in blob or "waiting" in blob, weight)
            _boost(scores, "exhaustion", 24, "rejection" in blob or "rejected" in blob, weight)
            _boost(scores, "uncertainty", 18, "continuation bar" in blob, weight * 0.6)

        elif reading.indicator == "Sentiment":
            _boost(scores, "greed", 28, "optimistic" in blob or "greed" in blob, weight)
            _boost(scores, "fear", 28, "fearful" in blob or "fear" in blob, weight)
            _boost(scores, "uncertainty", 20, "balanced" in blob or "equilibrium" in blob, weight)

    return scores


def _boost(
    scores: dict[str, float],
    emotion: str,
    amount: float,
    condition: bool,
    weight: float,
) -> None:
    if condition:
        scores[emotion] = scores.get(emotion, 0.0) + amount * weight


def _build_psychology_state(
    scores: dict[str, float],
    readings: tuple[PsychologicalReading, ...],
) -> PsychologyState:
    dominant = max(INFERRED_EMOTIONS, key=lambda e: scores.get(e, 0.0))
    threshold = max(scores.values()) * 0.72
    extremes = tuple(
        e for e in sorted(INFERRED_EMOTIONS, key=lambda x: scores[x], reverse=True)
        if scores[e] >= threshold and scores[e] >= 40.0
    )[:4]
    if not extremes:
        extremes = (dominant,)

    adx_reading = _reading_for(readings, "ADX")
    macd_reading = _reading_for(readings, "MACD")
    vol_reading = _reading_for(readings, "Volume")
    obv_reading = _reading_for(readings, "OBV")
    ad_reading = _reading_for(readings, "Accumulation/Distribution")

    conviction = _conviction_level(adx_reading, macd_reading)
    participation = _participation_quality(vol_reading, obv_reading, ad_reading)
    shift = _confidence_shift(macd_reading, adx_reading)

    return PsychologyState(
        dominant_emotion=dominant,
        conviction_level=conviction,
        participation_quality=participation,
        confidence_shift=shift,
        emotional_extremes=extremes,
    )


def _reading_for(
    readings: tuple[PsychologicalReading, ...],
    indicator: str,
) -> PsychologicalReading | None:
    return next((r for r in readings if r.indicator == indicator), None)


def _conviction_level(
    adx: PsychologicalReading | None,
    macd: PsychologicalReading | None,
) -> str:
    adx_strength = adx.strength if adx else 45.0
    macd_text = (macd.reading + macd.psychology).lower() if macd else ""
    if adx_strength >= 70 or "strong" in (adx.reading.lower() if adx else ""):
        return "strong"
    if adx_strength >= 55 or "moderate" in (adx.reading.lower() if adx else ""):
        return "moderate"
    if "accelerating" in macd_text:
        return "moderate"
    if adx_strength < 48 or "weak" in (adx.reading.lower() if adx else ""):
        return "weak"
    return "contested"


def _participation_quality(
    volume: PsychologicalReading | None,
    obv: PsychologicalReading | None,
    ad_line: PsychologicalReading | None,
) -> str:
    vol_text = (volume.reading + volume.psychology).lower() if volume else ""
    obv_text = (obv.reading + obv.psychology).lower() if obv else ""
    ad_text = (ad_line.reading + ad_line.psychology).lower() if ad_line else ""

    if "accumulation" in obv_text or "accumul" in ad_text:
        if "quiet" in vol_text or "apathy" in vol_text:
            return "stealth_accumulation"
        return "strong_sponsorship"
    if "distribution" in obv_text or "distribut" in ad_text:
        return "distribution_pressure"
    if "spike" in vol_text or "confirms" in vol_text:
        return "strong_sponsorship"
    if "quiet" in vol_text or "mixed" in obv_text:
        return "thin"
    return "mixed"


def _confidence_shift(
    macd: PsychologicalReading | None,
    adx: PsychologicalReading | None,
) -> str:
    macd_text = (macd.reading + macd.psychology).lower() if macd else ""
    adx_text = (adx.reading + adx.psychology).lower() if adx else ""
    if "accelerating" in macd_text or "strengthening" in adx_text:
        return "strengthening"
    if "fading" in macd_text or "weakening" in adx_text or "losing steam" in macd_text:
        return "weakening"
    if "easing" in macd_text or "contested" in adx_text:
        return "fading"
    return "stable"


def _derive_opportunity_expansion(
    state: PsychologyState,
    scores: dict[str, float],
    interpretation: IndicatorInterpretation,
) -> list[str]:
    hints: list[str] = []
    dominant = state.dominant_emotion

    if dominant in {"euphoria", "greed", "exhaustion"} or scores.get("exhaustion", 0) >= 45:
        hints.append("contrarian_snapback")
    if dominant in {"accumulation", "confidence"} and state.conviction_level in {"strong", "moderate"}:
        hints.append("momentum_continuation")
    if state.participation_quality == "stealth_accumulation":
        hints.append("accumulation_breakout")
    if "compressed" in interpretation.market_explanation_contribution.lower():
        hints.append("compression_release")
    if dominant in {"hesitation", "uncertainty"} and state.confidence_shift == "stable":
        hints.append("hesitation_break")
    if dominant == "panic" or scores.get("panic", 0) >= 50:
        hints.append("panic_capitulation_bounce")
    if dominant == "distribution" or state.participation_quality == "distribution_pressure":
        hints.append("distribution_fade")
    if state.confidence_shift == "weakening" and scores.get("exhaustion", 0) >= 40:
        hints.append("exhaustion_pause")

    deduped: list[str] = []
    for hint in hints:
        if hint in VALID_OPPORTUNITY_EXPANSIONS and hint not in deduped:
            deduped.append(hint)
    if not deduped:
        deduped = ["momentum_continuation", "hesitation_break"]
    return deduped


def _build_observations(
    state: PsychologyState,
    readings: tuple[PsychologicalReading, ...],
) -> list[str]:
    obs = [
        f"Dominant emotion: {state.dominant_emotion}",
        f"Conviction {state.conviction_level}, confidence {state.confidence_shift}",
        f"Participation: {state.participation_quality}",
    ]
    for reading in readings:
        if reading.indicator in {"RSI", "MACD", "OBV", "Volume"}:
            obs.append(f"{reading.indicator}: {reading.psychology}")
    if state.emotional_extremes:
        obs.append(f"Extremes: {', '.join(state.emotional_extremes)}")
    return obs[:7]


def _build_narrative(state: PsychologyState, scores: dict[str, float]) -> str:
    top = sorted(INFERRED_EMOTIONS, key=lambda e: scores[e], reverse=True)[:3]
    emotion_phrase = ", ".join(top)
    return (
        f"Participants appear driven by {state.dominant_emotion} with "
        f"{state.conviction_level} conviction. "
        f"Participation quality is {state.participation_quality}; "
        f"confidence is {state.confidence_shift}. "
        f"Emotional landscape: {emotion_phrase}."
    )


def _compute_insight_score(
    state: PsychologyState,
    scores: dict[str, float],
    expansions: list[str],
) -> float:
    base = 5.0 + len(state.emotional_extremes) * 0.9 + len(expansions) * 0.7
    spread = max(scores.values()) - min(scores.values())
    base += min(3.0, spread * 0.04)
    if state.conviction_level == "strong":
        base += 1.5
    return min(14.0, max(0.0, base))


def _emotion_direction(emotion: str) -> str:
    if emotion in {"fear", "panic", "distribution", "hesitation", "uncertainty", "exhaustion"}:
        if emotion in {"distribution"}:
            return "bearish"
        return "neutral"
    if emotion in {"greed", "euphoria", "accumulation", "confidence"}:
        return "bullish"
    return "neutral"


def _dominant_strength(scores: dict[str, float], emotion: str) -> float:
    return min(100.0, max(35.0, scores.get(emotion, 40.0)))


def _conviction_strength(level: str) -> float:
    return {"strong": 78.0, "moderate": 62.0, "weak": 45.0, "contested": 38.0}.get(level, 50.0)


def _shift_direction(shift: str) -> str:
    if shift == "strengthening":
        return "bullish"
    if shift in {"weakening", "fading"}:
        return "bearish"
    return "neutral"


__all__ = [
    "FORBIDDEN_OUTPUT",
    "MARKET_PSYCHOLOGY_DNA",
    "MarketPsychologyEngine",
    "MarketPsychologyResult",
    "PsychologyState",
]
