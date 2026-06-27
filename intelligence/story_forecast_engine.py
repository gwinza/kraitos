"""Story Forecast Engine — predict next move from market story."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from intelligence.market_story_engine import MarketStoryResult, OpportunityType
from intelligence.narrative_forecast_engine import (
    MICRO_CLASS_STRATEGY,
    NarrativeForecastEngine,
    NarrativeForecastResult,
)

if TYPE_CHECKING:
    from intelligence.evidence_synthesis_engine import MarketStorySummary
    from intelligence.market_psychology_engine import MarketPsychologyResult
    from intelligence.story_evolution_engine import NestedStoryState
    from intelligence.trader_memory_engine import MemoryRecallInsight
    from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult

FORECAST_DNA = """
What is most likely next?

Story Forecast assigns continuation, pullback, reversal, breakout, compression, and
exhaustion probabilities using evidence synthesis, psychology, story evolution,
and trader memory.

Probabilities inform action — they never filter, veto, or refuse opportunities.
""".strip()

OPP_STRATEGY_MAP: dict[OpportunityType, str] = {
    "pullback_continuation": "pullback_harvest",
    "liquidity_sweep": "liquidity_sweep_fade",
    "breakout_retest": "pullback_harvest",
    "failed_breakout": "mean_reversion_snapback",
    "compression_breakout": "compression_breakout",
    "trend_pause_resume": "trend_continuation",
    "mean_reversion_snapback": "mean_reversion_snapback",
    "session_transition": "session_momentum",
}

OPP_PIP_RANGE: dict[OpportunityType, tuple[float, float]] = {
    "pullback_continuation": (2.0, 5.0),
    "liquidity_sweep": (1.5, 3.5),
    "breakout_retest": (2.0, 4.5),
    "failed_breakout": (1.5, 3.5),
    "compression_breakout": (2.5, 5.5),
    "trend_pause_resume": (2.5, 5.0),
    "mean_reversion_snapback": (1.5, 3.5),
    "session_transition": (2.5, 4.5),
}

SCENARIO_NAMES = (
    "continuation",
    "pullback",
    "reversal",
    "breakout",
    "compression",
    "exhaustion",
)


@dataclass(frozen=True)
class ForecastScenarioProbabilities:
    """Scenario probabilities — inform action, never filter."""

    continuation: float
    pullback: float
    reversal: float
    breakout: float
    compression: float
    exhaustion: float

    def to_dict(self) -> dict[str, float]:
        return {
            "continuation": round(self.continuation, 1),
            "pullback": round(self.pullback, 1),
            "reversal": round(self.reversal, 1),
            "breakout": round(self.breakout, 1),
            "compression": round(self.compression, 1),
            "exhaustion": round(self.exhaustion, 1),
        }

    def most_likely(self) -> tuple[str, float]:
        items = (
            ("continuation", self.continuation),
            ("pullback", self.pullback),
            ("reversal", self.reversal),
            ("breakout", self.breakout),
            ("compression", self.compression),
            ("exhaustion", self.exhaustion),
        )
        name, value = max(items, key=lambda x: x[1])
        return name, value

    def as_tuple(self) -> tuple[float, ...]:
        return (
            self.continuation,
            self.pullback,
            self.reversal,
            self.breakout,
            self.compression,
            self.exhaustion,
        )


@dataclass(frozen=True)
class StoryForecastResult:
    """Per-asset story-driven forecast."""

    symbol: str
    story: str
    expected_next_move: str
    expected_pip_range: float
    confidence: float
    invalidation: str
    opportunity_type: str | None
    recommended_strategy: str
    direction: str
    evolution_trajectory: str = "uncertain"
    confidence_trend: str = "stable"
    strengthening: bool = False
    deteriorating: bool = False
    transition_likely: bool = False
    reversal_probable: bool = False
    scenario_probabilities: ForecastScenarioProbabilities = field(
        default_factory=lambda: ForecastScenarioProbabilities(16.7, 16.7, 16.7, 16.7, 16.7, 16.5)
    )
    most_likely_next: str = "continuation"
    probability_rationale: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "story": self.story,
            "expected_next_move": self.expected_next_move,
            "expected_pip_range": round(self.expected_pip_range, 2),
            "confidence": round(self.confidence, 2),
            "invalidation": self.invalidation,
            "opportunity_type": self.opportunity_type,
            "recommended_strategy": self.recommended_strategy,
            "direction": self.direction,
            "evolution_trajectory": self.evolution_trajectory,
            "confidence_trend": self.confidence_trend,
            "strengthening": self.strengthening,
            "deteriorating": self.deteriorating,
            "transition_likely": self.transition_likely,
            "reversal_probable": self.reversal_probable,
            "scenario_probabilities": self.scenario_probabilities.to_dict(),
            "most_likely_next": self.most_likely_next,
            "probability_rationale": list(self.probability_rationale),
        }

    def to_narrative_forecast(self) -> NarrativeForecastResult:
        """Bridge for forecast_feedback and legacy consumers."""
        return NarrativeForecastResult(
            symbol=self.symbol,
            current_story=self.story,
            expected_next_move=self.expected_next_move,
            expected_pip_range=self.expected_pip_range,
            confidence=self.confidence,
            invalidation=self.invalidation,
            recommended_strategy=self.recommended_strategy,  # type: ignore[arg-type]
            direction=self.direction,
        )


@dataclass
class ForecastStats:
    """Accumulated forecast metrics for validation reporting."""

    forecasts_issued: int = 0
    most_likely_counts: dict[str, int] = field(default_factory=dict)
    avg_continuation: float = 0.0
    avg_reversal: float = 0.0
    avg_breakout: float = 0.0
    psychology_informed: int = 0
    memory_informed: int = 0
    synthesis_informed: int = 0
    evolution_informed: int = 0


class StoryForecastEngine:
    """Forecast next move from market story — probabilities inform, never filter."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self._latest: dict[str, StoryForecastResult] = {}
        self._narrative_engine = NarrativeForecastEngine(project_root)
        self._exit_profiles: dict[str, object] = {}
        self.stats = ForecastStats()
        self._prob_sums = {name: 0.0 for name in SCENARIO_NAMES}

    def forecast(
        self,
        *,
        symbol: str,
        market_story: MarketStoryResult,
        candles: dict[str, pd.DataFrame],
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        regime: RegimeResult,
        indicator_atr_ratio: float | None = None,
        indicator_confirmation_boost: float = 0.0,
        evolution_state: NestedStoryState | None = None,
        evolution_engine: object | None = None,
        evidence_synthesis: MarketStorySummary | None = None,
        market_psychology: MarketPsychologyResult | None = None,
        trader_memory_recall: MemoryRecallInsight | None = None,
    ) -> StoryForecastResult:
        narrative = market_story.to_narrative_result()
        legacy = self._narrative_engine.forecast(
            symbol=symbol,
            narrative=narrative,
            candles=candles,
            structure=structure,
            bias=bias,
            regime=regime,
            indicator_atr_ratio=indicator_atr_ratio,
            indicator_confirmation_boost=indicator_confirmation_boost,
        )
        self._exit_profiles[symbol] = self._narrative_engine.exit_profile(symbol)

        synthesis = evidence_synthesis or market_story.synthesis
        opp = market_story.opportunity_type
        strategy = legacy.recommended_strategy
        pip_range = legacy.expected_pip_range
        next_move = legacy.expected_next_move
        invalidation = legacy.invalidation

        if opp is not None:
            strategy = OPP_STRATEGY_MAP.get(opp, strategy)  # type: ignore[assignment]
            low, high = OPP_PIP_RANGE.get(opp, (pip_range * 0.8, pip_range * 1.2))
            pip_range = (low + high) / 2
            next_move = f"{opp.replace('_', ' ')} — {next_move}"
            invalidation = self._invalidation_for(opp, structure, bias)

        conf = market_story.overall_confidence + indicator_confirmation_boost
        if market_story.story_clear:
            conf = min(100.0, conf + 5.0)
        if market_story.strike.strike not in {"none"}:
            conf = min(100.0, conf + 4.0)

        trajectory = "uncertain"
        conf_trend = "stable"
        strengthening = False
        deteriorating = False
        transition_likely = False
        reversal_probable = False
        conf_delta = 0.0

        if evolution_state is not None:
            trajectory = evolution_state.probable_evolution
            conf_trend = evolution_state.confidence_trend
            strengthening = evolution_state.probable_evolution == "strengthening"
            deteriorating = evolution_state.probable_evolution == "deteriorating"
            transition_likely = evolution_state.transition or evolution_state.probable_evolution == "transition"
            reversal_probable = evolution_state.probable_evolution == "reversal_probable"
            if evolution_state.alignment == "aligned":
                conf_delta += 3.0
            elif evolution_state.alignment == "conflict":
                conf_delta -= 4.0
            if evolution_state.confidence_trend == "strengthening":
                conf_delta += 2.0
            elif evolution_state.confidence_trend == "deteriorating":
                conf_delta -= 3.0
            if evolution_state.impact_accumulation > 4:
                conf_delta += 1.5
            elif evolution_state.impact_accumulation < -4:
                conf_delta -= 2.0
            if transition_likely:
                next_move = f"[transition] {next_move}"
            if reversal_probable:
                next_move = f"[reversal risk] {next_move}"
            conf += conf_delta
            if evolution_engine is not None and hasattr(evolution_engine, "record_forecast_adjustment"):
                evolution_engine.record_forecast_adjustment(
                    symbol,
                    adjustment=trajectory,
                    confidence_delta=conf_delta,
                )

        conf = max(0.0, min(100.0, conf))

        probabilities, rationale = _compute_scenario_probabilities(
            market_story=market_story,
            synthesis=synthesis,
            evolution_state=evolution_state,
            market_psychology=market_psychology,
            trader_memory_recall=trader_memory_recall,
            bias=bias,
            regime=regime,
        )
        likely_name, likely_pct = probabilities.most_likely()
        most_likely_next = likely_name
        next_move = (
            f"Most likely: {likely_name} ({likely_pct:.0f}%) — {next_move}"
        )

        result = StoryForecastResult(
            symbol=symbol,
            story=market_story.primary_story,
            expected_next_move=next_move,
            expected_pip_range=pip_range,
            confidence=conf,
            invalidation=invalidation,
            opportunity_type=opp,
            recommended_strategy=strategy,
            direction=legacy.direction,
            evolution_trajectory=trajectory,
            confidence_trend=conf_trend,
            strengthening=strengthening,
            deteriorating=deteriorating,
            transition_likely=transition_likely,
            reversal_probable=reversal_probable,
            scenario_probabilities=probabilities,
            most_likely_next=most_likely_next,
            probability_rationale=tuple(rationale),
        )
        self._latest[symbol] = result
        self._record_stats(
            result,
            synthesis_informed=synthesis is not None,
            psychology_informed=market_psychology is not None,
            memory_informed=trader_memory_recall is not None,
            evolution_informed=evolution_state is not None,
        )
        return result

    def exit_profile(self, symbol: str):
        return self._exit_profiles.get(symbol) or self._narrative_engine.exit_profile(symbol)

    def write_report(self, path: Path | None = None) -> Path | None:
        if not self._latest or self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "story_forecast_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Story Forecast Report",
            "",
            f"**Generated:** {now}",
            "",
            "Story-driven forecast — probabilities inform action, never filter.",
            "",
            "| Symbol | Most likely | Cont | Pull | Rev | Brk | Comp | Exh | Conf |",
            "|--------|-------------|------|------|-----|-----|------|-----|------|",
        ]
        for symbol in sorted(self._latest):
            f = self._latest[symbol]
            p = f.scenario_probabilities
            lines.append(
                f"| {symbol} | {f.most_likely_next} | {p.continuation:.0f}% | "
                f"{p.pullback:.0f}% | {p.reversal:.0f}% | {p.breakout:.0f}% | "
                f"{p.compression:.0f}% | {p.exhaustion:.0f}% | {f.confidence:.0f} |"
            )
        lines.extend(["", "## Expected next moves", ""])
        for symbol in sorted(self._latest):
            f = self._latest[symbol]
            lines.append(f"- **{symbol}:** {f.expected_next_move}")
        lines.extend(["", "## Invalidation", ""])
        for symbol in sorted(self._latest):
            f = self._latest[symbol]
            lines.append(f"- **{symbol}:** {f.invalidation}")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_forecast_quality_report(self, path: Path | None = None) -> Path | None:
        """Validation-only forecast quality summary."""
        if self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "forecast_quality_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        n = max(self.stats.forecasts_issued, 1)
        lines = [
            "# Forecast Quality Report",
            "",
            f"**Generated:** {now}",
            "",
            "Validation-only — scenario probabilities inform action, never filter trades.",
            "",
            "## Coverage",
            "",
            f"- Forecasts issued: **{self.stats.forecasts_issued}**",
            f"- Evidence synthesis informed: **{self.stats.synthesis_informed}**",
            f"- Psychology informed: **{self.stats.psychology_informed}**",
            f"- Story evolution informed: **{self.stats.evolution_informed}**",
            f"- Trader memory informed: **{self.stats.memory_informed}**",
            "",
            "## Average scenario probabilities",
            "",
            f"- Continuation: **{self._prob_sums['continuation'] / n:.1f}%**",
            f"- Pullback: **{self._prob_sums['pullback'] / n:.1f}%**",
            f"- Reversal: **{self._prob_sums['reversal'] / n:.1f}%**",
            f"- Breakout: **{self._prob_sums['breakout'] / n:.1f}%**",
            f"- Compression: **{self._prob_sums['compression'] / n:.1f}%**",
            f"- Exhaustion: **{self._prob_sums['exhaustion'] / n:.1f}%**",
            "",
            "## Most likely next (distribution)",
            "",
        ]
        for scenario, count in sorted(
            self.stats.most_likely_counts.items(),
            key=lambda x: -x[1],
        ):
            lines.append(f"- **{scenario}:** {count} ({100.0 * count / n:.1f}%)")
        lines.extend([
            "",
            "## Doctrine check",
            "",
            "- Probabilities are informational only — no probability threshold vetoes.",
            "- Forecast informs action; TraderBrain and Portfolio retain allocation authority.",
            "- Live trading remains disabled during validation.",
            "",
        ])
        if self._latest:
            lines.extend(["## Latest forecasts", ""])
            for symbol in sorted(self._latest):
                f = self._latest[symbol]
                p = f.scenario_probabilities
                lines.append(
                    f"- **{symbol}** — most likely **{f.most_likely_next}** "
                    f"(cont {p.continuation:.0f}%, pull {p.pullback:.0f}%, "
                    f"rev {p.reversal:.0f}%, brk {p.breakout:.0f}%, "
                    f"comp {p.compression:.0f}%, exh {p.exhaustion:.0f}%)"
                )
                for note in f.probability_rationale[:3]:
                    lines.append(f"  - {note}")
            lines.append("")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def _record_stats(
        self,
        result: StoryForecastResult,
        *,
        synthesis_informed: bool,
        psychology_informed: bool,
        memory_informed: bool,
        evolution_informed: bool,
    ) -> None:
        self.stats.forecasts_issued += 1
        if synthesis_informed:
            self.stats.synthesis_informed += 1
        if psychology_informed:
            self.stats.psychology_informed += 1
        if memory_informed:
            self.stats.memory_informed += 1
        if evolution_informed:
            self.stats.evolution_informed += 1
        likely = result.most_likely_next
        self.stats.most_likely_counts[likely] = self.stats.most_likely_counts.get(likely, 0) + 1
        p = result.scenario_probabilities
        for name, value in p.to_dict().items():
            self._prob_sums[name] = self._prob_sums.get(name, 0.0) + value

    @staticmethod
    def _invalidation_for(
        opp: OpportunityType,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
    ) -> str:
        if opp in {"pullback_continuation", "breakout_retest", "trend_pause_resume"}:
            return (
                "Close below recent swing low"
                if bias.bias == "bullish"
                else "Close above recent swing high"
            )
        if opp == "liquidity_sweep":
            return "Sweep level reclaimed against entry"
        if opp == "compression_breakout":
            return "Return inside compression range"
        if opp in {"failed_breakout", "mean_reversion_snapback"}:
            return "Extension beyond mean reversion target"
        if structure.last_bos is not None:
            return f"Break of BOS level at {structure.last_bos.price:.5f}"
        return "Structure break against forecast direction"


def _compute_scenario_probabilities(
    *,
    market_story: MarketStoryResult,
    synthesis: MarketStorySummary | None,
    evolution_state: NestedStoryState | None,
    market_psychology: MarketPsychologyResult | None,
    trader_memory_recall: MemoryRecallInsight | None,
    bias: MultiTimeframeBiasResult,
    regime: RegimeResult,
) -> tuple[ForecastScenarioProbabilities, list[str]]:
    raw = {name: 10.0 for name in SCENARIO_NAMES}
    rationale: list[str] = []

    if market_story.macro_story == "trending":
        raw["continuation"] += 3.0
        rationale.append("Macro story trending — continuation weighted higher")
    elif market_story.macro_story == "compression":
        raw["compression"] += 3.5
        raw["breakout"] += 2.0
        rationale.append("Macro compression — coil and breakout weighted")
    elif market_story.macro_story == "exhaustion":
        raw["exhaustion"] += 3.5
        raw["reversal"] += 2.0
        rationale.append("Macro exhaustion — fade scenarios weighted")

    if market_story.h1_integrity == "confirmed":
        raw["continuation"] += 2.5
    elif market_story.h1_integrity == "weakening":
        raw["pullback"] += 2.0
        raw["exhaustion"] += 1.5
    elif market_story.h1_integrity == "changing":
        raw["reversal"] += 2.5
        raw["compression"] += 1.0

    if market_story.compression_detected:
        raw["compression"] += 3.0
        raw["breakout"] += 2.0
    if market_story.exhaustion_detected:
        raw["exhaustion"] += 3.0
        raw["reversal"] += 1.5
    if market_story.rejection_detected:
        raw["pullback"] += 2.0
        raw["reversal"] += 1.0

    opp = market_story.opportunity_type
    if opp == "pullback_continuation":
        raw["pullback"] += 3.0
        raw["continuation"] += 2.5
    elif opp == "compression_breakout":
        raw["breakout"] += 3.5
        raw["compression"] += 2.0
    elif opp in {"failed_breakout", "mean_reversion_snapback"}:
        raw["reversal"] += 3.0
        raw["exhaustion"] += 1.5
    elif opp == "trend_pause_resume":
        raw["continuation"] += 2.5
        raw["pullback"] += 2.0
    elif opp == "liquidity_sweep":
        raw["reversal"] += 2.0
        raw["pullback"] += 2.0

    if synthesis is not None:
        rationale.append("Evidence synthesis informs scenario blend")
        event = synthesis.probable_next_event.lower()
        if "continuation" in event or "resume" in event:
            raw["continuation"] += 2.5
        if "pullback" in event or "retrace" in event:
            raw["pullback"] += 2.5
        if "reversal" in event or "snapback" in event:
            raw["reversal"] += 2.5
        if "breakout" in event or "expansion" in event:
            raw["breakout"] += 2.5
        if "compression" in event or "coil" in event:
            raw["compression"] += 2.5
        if "exhaustion" in event or "fade" in event:
            raw["exhaustion"] += 2.5
        if synthesis.contradicting_evidence:
            raw["compression"] += 1.0
            raw["reversal"] += 1.0
            rationale.append("Synthesis conflict — transition scenarios nudged")

    if evolution_state is not None:
        rationale.append(f"Story evolution: {evolution_state.probable_evolution}")
        evo_map = {
            "continuation_likely": ("continuation", 3.0),
            "strengthening": ("continuation", 2.5),
            "reversal_probable": ("reversal", 3.5),
            "deteriorating": ("exhaustion", 2.5),
            "transition": ("compression", 2.0),
            "uncertain": ("compression", 1.0),
        }
        boost = evo_map.get(evolution_state.probable_evolution)
        if boost:
            raw[boost[0]] += boost[1]
        if evolution_state.chapter_story in {"pullback", "weakening"}:
            raw["pullback"] += 2.0
        if evolution_state.paragraph_story in {"compression", "breakout_attempt"}:
            raw["compression"] += 1.5
            raw["breakout"] += 1.5
        if evolution_state.sentence_story in {"exhaustion_candle", "rejection_wick"}:
            raw["exhaustion"] += 2.0

    if market_psychology is not None:
        rationale.append(
            f"Psychology: dominant {market_psychology.psychology_state.dominant_emotion}"
        )
        emotion = market_psychology.psychology_state.dominant_emotion
        emotion_map = {
            "greed": ("continuation", 2.0),
            "euphoria": ("exhaustion", 2.5),
            "confidence": ("continuation", 2.5),
            "accumulation": ("breakout", 2.0),
            "fear": ("pullback", 2.0),
            "panic": ("reversal", 2.5),
            "hesitation": ("compression", 2.5),
            "uncertainty": ("compression", 2.0),
            "distribution": ("reversal", 2.0),
            "exhaustion": ("exhaustion", 3.0),
        }
        boost = emotion_map.get(emotion)
        if boost:
            raw[boost[0]] += boost[1]
        shift = market_psychology.psychology_state.confidence_shift
        if shift == "strengthening":
            raw["continuation"] += 1.5
        elif shift in {"weakening", "fading"}:
            raw["exhaustion"] += 1.5
            raw["pullback"] += 1.0

    if trader_memory_recall is not None and trader_memory_recall.similar_count > 0:
        rationale.append(
            f"Memory: {trader_memory_recall.similar_count} similar narratives recalled"
        )
        if trader_memory_recall.success_rate >= 0.55:
            raw["continuation"] += 1.5
            rationale.append("Memory success bias — continuation nudged (inform only)")
        if trader_memory_recall.failure_rate >= 0.55:
            raw["reversal"] += 1.0
            raw["pullback"] += 1.0
            rationale.append("Memory failure lessons — transition nudged (inform only)")
        if "repeat_success_pattern" in trader_memory_recall.opportunity_expansion:
            raw["continuation"] += 1.0
        if "learn_from_failure" in trader_memory_recall.opportunity_expansion:
            raw["reversal"] += 0.8

    if bias.bias == "bullish" and regime.regime == "trending":
        raw["continuation"] += 1.5
    elif bias.bias == "bearish" and regime.regime == "trending":
        raw["continuation"] += 1.5

    total = sum(raw.values())
    normalized = {k: 100.0 * v / total for k, v in raw.items()}
    return (
        ForecastScenarioProbabilities(
            continuation=normalized["continuation"],
            pullback=normalized["pullback"],
            reversal=normalized["reversal"],
            breakout=normalized["breakout"],
            compression=normalized["compression"],
            exhaustion=normalized["exhaustion"],
        ),
        rationale,
    )


__all__ = [
    "FORECAST_DNA",
    "ForecastScenarioProbabilities",
    "ForecastStats",
    "StoryForecastEngine",
    "StoryForecastResult",
]
