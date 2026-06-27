"""Human Trader Reasoning Layer — explain opportunities like an experienced trader."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from intelligence.evidence_synthesis_engine import EvidencePiece
from intelligence.indicator_interpretation_engine import FORBIDDEN_OUTPUT

if TYPE_CHECKING:
    from intelligence.indicator_interpretation_engine import IndicatorInterpretation
    from intelligence.market_psychology_engine import MarketPsychologyResult
    from intelligence.market_story_engine import MarketStoryResult
    from intelligence.story_evolution_engine import NestedStoryState
    from intelligence.story_forecast_engine import StoryForecastResult
    from intelligence.trader_memory_engine import MemoryRecallInsight
    from strategies.models import HarvestDecision, MicroScalpSignal

HUMAN_TRADER_REASONING_DNA = """
Kraitos explains trades the way an experienced trader would.

For every opportunity: what is happening, why, what participants feel,
what is likely next, what opportunity exists, why it is attractive, and
what evidence contradicts the view — woven into a coherent trade thesis.

Reasoning improves understanding — it never filters, vetoes, or refuses trades.
""".strip()

PRIMARY_TIMEFRAME = "H1"

REASONING_QUESTIONS = (
    "what_is_happening",
    "why_is_it_happening",
    "what_participants_feel",
    "what_is_likely_next",
    "what_opportunity_exists",
    "why_opportunity_attractive",
    "contradicting_evidence",
)


@dataclass(frozen=True)
class TradeReasoning:
    """Human-style trade explanation — enrichment only."""

    symbol: str
    what_is_happening: str
    why_is_it_happening: str
    what_participants_feel: str
    what_is_likely_next: str
    what_opportunity_exists: str
    why_opportunity_attractive: str
    contradicting_evidence: tuple[str, ...]
    trade_thesis: str
    setup_kind: str = "harvest"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "setup_kind": self.setup_kind,
            "what_is_happening": self.what_is_happening,
            "why_is_it_happening": self.why_is_it_happening,
            "what_participants_feel": self.what_participants_feel,
            "what_is_likely_next": self.what_is_likely_next,
            "what_opportunity_exists": self.what_opportunity_exists,
            "why_opportunity_attractive": self.why_opportunity_attractive,
            "contradicting_evidence": list(self.contradicting_evidence),
            "trade_thesis": self.trade_thesis,
        }

    def to_evidence_pieces(self) -> list[EvidencePiece]:
        direction = "neutral"
        if "bullish" in self.what_is_happening.lower() or "bull" in self.trade_thesis.lower()[:120]:
            direction = "bullish"
        elif "bearish" in self.what_is_happening.lower() or "bear" in self.trade_thesis.lower()[:120]:
            direction = "bearish"
        return [
            EvidencePiece(
                category="human_trader_reasoning",
                timeframe=PRIMARY_TIMEFRAME,
                signal="trade_thesis",
                description=self.trade_thesis[:240],
                direction=direction,
                strength=62.0,
            ),
            EvidencePiece(
                category="human_trader_reasoning",
                timeframe=PRIMARY_TIMEFRAME,
                signal="what_is_happening",
                description=self.what_is_happening,
                direction=direction,
                strength=55.0,
            ),
        ]


@dataclass
class ReasoningStats:
    """Accumulated reasoning metrics for reporting."""

    explained: int = 0
    evidence_pieces_added: int = 0


class HumanTraderReasoningLayer:
    """
    Generate experienced-trader explanations for every opportunity.

    Enriches understanding — never creates trades or refuses them.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self._latest: dict[str, TradeReasoning] = {}
        self.stats = ReasoningStats()

    def explain(
        self,
        *,
        symbol: str,
        setup_kind: str = "harvest",
        market_story: MarketStoryResult | None = None,
        story_forecast: StoryForecastResult | None = None,
        indicator_interpretation: IndicatorInterpretation | None = None,
        story_evolution: NestedStoryState | None = None,
        market_psychology: MarketPsychologyResult | None = None,
        trader_memory_recall: MemoryRecallInsight | None = None,
        harvest: HarvestDecision | None = None,
        micro_scalp: MicroScalpSignal | None = None,
    ) -> TradeReasoning:
        symbol = symbol.strip().upper()
        trend_label, happening = _what_is_happening(
            market_story, story_evolution, harvest, micro_scalp, setup_kind
        )
        why = _why_is_it_happening(market_story, story_evolution, indicator_interpretation)
        feel = _what_participants_feel(
            market_psychology, indicator_interpretation, market_story
        )
        likely_next = _what_is_likely_next(story_forecast, market_story, story_evolution)
        opportunity = _what_opportunity_exists(
            market_story, story_forecast, harvest, micro_scalp, setup_kind
        )
        attractive = _why_opportunity_attractive(
            market_story,
            story_forecast,
            harvest,
            trader_memory_recall,
            setup_kind,
        )
        contradicting = _contradicting_evidence(
            market_story, indicator_interpretation, story_evolution, story_forecast
        )
        thesis = _build_trade_thesis(
            trend_label=trend_label,
            happening=happening,
            why=why,
            feel=feel,
            likely_next=likely_next,
            opportunity=opportunity,
            attractive=attractive,
            contradicting=contradicting,
        )

        result = TradeReasoning(
            symbol=symbol,
            what_is_happening=happening,
            why_is_it_happening=why,
            what_participants_feel=feel,
            what_is_likely_next=likely_next,
            what_opportunity_exists=opportunity,
            why_opportunity_attractive=attractive,
            contradicting_evidence=tuple(contradicting),
            trade_thesis=thesis,
            setup_kind=setup_kind,
        )
        key = f"{symbol}:{setup_kind}"
        self._latest[key] = result
        self.stats.explained += 1
        self.stats.evidence_pieces_added += len(result.to_evidence_pieces())
        return result

    def write_human_trader_reasoning_report(self, path: Path | None = None) -> Path | None:
        if not self._latest or self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "human_trader_reasoning_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Human Trader Reasoning Report",
            "",
            f"**Generated:** {now}",
            "",
            "Experienced-trader explanations — never signals or vetoes.",
            "",
            f"- Opportunities explained: **{self.stats.explained}**",
            f"- Evidence pieces added: **{self.stats.evidence_pieces_added}**",
            "",
        ]
        for key in sorted(self._latest):
            reasoning = self._latest[key]
            lines.extend([
                f"## {reasoning.symbol} ({reasoning.setup_kind})",
                "",
                f"**Thesis:** {reasoning.trade_thesis}",
                "",
                "| Question | Answer |",
                "|----------|--------|",
                f"| What is happening? | {reasoning.what_is_happening} |",
                f"| Why is it happening? | {reasoning.why_is_it_happening} |",
                f"| What are participants feeling? | {reasoning.what_participants_feel} |",
                f"| What is likely next? | {reasoning.what_is_likely_next} |",
                f"| What opportunity exists? | {reasoning.what_opportunity_exists} |",
                f"| Why is this attractive? | {reasoning.why_opportunity_attractive} |",
                "",
                "**Contradicting evidence:**",
                "",
            ])
            if reasoning.contradicting_evidence:
                for item in reasoning.contradicting_evidence:
                    lines.append(f"- {item}")
            else:
                lines.append("- No major contradictions surfaced in current evidence.")
            lines.append("")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path


def _what_is_happening(
    market_story: MarketStoryResult | None,
    story_evolution: NestedStoryState | None,
    harvest: HarvestDecision | None,
    micro_scalp: MicroScalpSignal | None,
    setup_kind: str,
) -> tuple[str, str]:
    trend = "neutral"
    if market_story is not None:
        if market_story.macro_story == "trending":
            trend = "bullish" if "bull" in market_story.structure_signal.lower() else "directional"
        elif market_story.macro_story in {"distribution", "exhaustion"}:
            trend = "bearish"
        elif market_story.macro_story == "accumulation":
            trend = "bullish"

    parts: list[str] = []
    if market_story is not None:
        parts.append(market_story.primary_story.rstrip("."))
        if market_story.compression_detected:
            parts.append("price is coiling in compression")
        if market_story.rejection_detected:
            parts.append("recent rejection wicks show active defence at key levels")
        if market_story.exhaustion_detected:
            parts.append("momentum shows signs of exhaustion")
    elif story_evolution is not None:
        parts.append(
            f"the {story_evolution.macro_story or story_evolution.novel.story} narrative "
            f"is unfolding on {story_evolution.chapter_story or story_evolution.chapter.story}"
        )
    else:
        parts.append("the market is delivering mixed price action without a dominant headline")

    if setup_kind == "micro_scalp" and micro_scalp is not None:
        parts.append(f"a precision {micro_scalp.action} scalp setup is visible on the lower timeframe")
    elif harvest is not None and harvest.allowed:
        parts.append("a harvest-quality setup is forming within the broader story")

    trend_phrase = {
        "bullish": "bullish",
        "bearish": "bearish",
        "directional": "directional",
    }.get(trend, "mixed")
    headline = f"The broader picture remains {trend_phrase}. " + ". ".join(parts[:2]).capitalize()
    if not headline.endswith("."):
        headline += "."
    return trend_phrase, headline


def _why_is_it_happening(
    market_story: MarketStoryResult | None,
    story_evolution: NestedStoryState | None,
    indicator_interpretation: IndicatorInterpretation | None,
) -> str:
    reasons: list[str] = []
    if market_story is not None and market_story.synthesis is not None:
        reasons.append(market_story.synthesis.current_explanation)
        for item in market_story.synthesis.supporting_evidence[:2]:
            reasons.append(item)
    elif market_story is not None:
        reasons.append(f"{market_story.volume_signal}. {market_story.structure_signal}.")

    if story_evolution is not None:
        if story_evolution.probable_evolution == "continuation_likely":
            reasons.append("nested timeframes remain aligned for continuation")
        elif story_evolution.probable_evolution == "reversal_probable":
            reasons.append("lower-timeframe pressure is challenging the prevailing narrative")
        elif story_evolution.conflict:
            reasons.append("timeframe layers are in partial conflict as the story transitions")

    if indicator_interpretation is not None:
        for reading in indicator_interpretation.psychological_readings[:3]:
            if reading.indicator in {"Volume", "OBV", "Price Action"}:
                reasons.append(reading.reading.rstrip("."))

    if not reasons:
        return "Participants are responding to recent flow without a single dominant catalyst."
    text = reasons[0]
    if len(reasons) > 1:
        text = f"{reasons[0].rstrip('.')}. {reasons[1].rstrip('.')}."
    return text[0].upper() + text[1:] if text else text


def _what_participants_feel(
    market_psychology: MarketPsychologyResult | None,
    indicator_interpretation: IndicatorInterpretation | None,
    market_story: MarketStoryResult | None,
) -> str:
    if market_psychology is not None:
        state = market_psychology.psychology_state
        return (
            f"Participants appear driven by {state.dominant_emotion} with "
            f"{state.conviction_level} conviction. Participation quality is "
            f"{state.participation_quality.replace('_', ' ')} and confidence is "
            f"{state.confidence_shift}."
        )

    if indicator_interpretation is not None:
        bits = [r.psychology for r in indicator_interpretation.psychological_readings[:3]]
        if bits:
            return " ".join(bits[:2]).capitalize() + "."

    if market_story is not None and market_story.exhaustion_detected:
        return "Late participants show euphoria or fatigue while defenders become more selective."
    return "The crowd is cautious — neither panic nor euphoria dominates the tape."


def _what_is_likely_next(
    story_forecast: StoryForecastResult | None,
    market_story: MarketStoryResult | None,
    story_evolution: NestedStoryState | None,
) -> str:
    if story_forecast is not None:
        probs = story_forecast.scenario_probabilities
        likely, pct = probs.most_likely()
        move = story_forecast.expected_next_move
        if "Most likely:" in move:
            move = move.split("—", 1)[-1].strip() if "—" in move else move
        return (
            f"{likely.replace('_', ' ').title()} is the most probable outcome "
            f"({pct:.0f}% scenario weight). {move.rstrip('.')}."
        )

    if market_story is not None and market_story.synthesis is not None:
        return f"{market_story.synthesis.probable_next_event.rstrip('.')}."

    if story_evolution is not None:
        return (
            f"The story is likely to {story_evolution.probable_evolution.replace('_', ' ')} "
            f"with {story_evolution.confidence_trend} confidence."
        )
    return "The next impulse is unclear until participation confirms direction."


def _what_opportunity_exists(
    market_story: MarketStoryResult | None,
    story_forecast: StoryForecastResult | None,
    harvest: HarvestDecision | None,
    micro_scalp: MicroScalpSignal | None,
    setup_kind: str,
) -> str:
    if setup_kind == "micro_scalp" and micro_scalp is not None:
        return (
            f"A micro scalp opportunity exists — {micro_scalp.action} alignment "
            f"on the execution timeframe."
        )
    opp_type = None
    if market_story is not None:
        opp_type = market_story.opportunity_type
    if story_forecast is not None and story_forecast.opportunity_type:
        opp_type = story_forecast.opportunity_type
    if opp_type:
        label = opp_type.replace("_", " ")
        return f"A {label} opportunity is present within the current market story."
    if harvest is not None and harvest.allowed:
        return "A harvest opportunity exists — structured entry within the prevailing narrative."
    if market_story is not None and market_story.story_clear:
        return "An narrative-aligned opportunity exists as the story clears for action."
    return "A contextual opportunity may exist as the story develops — patience for clarity."


def _why_opportunity_attractive(
    market_story: MarketStoryResult | None,
    story_forecast: StoryForecastResult | None,
    harvest: HarvestDecision | None,
    trader_memory_recall: MemoryRecallInsight | None,
    setup_kind: str,
) -> str:
    parts: list[str] = []
    if market_story is not None and market_story.story_clear:
        parts.append(f"the story is clear ({market_story.overall_confidence:.0f}% confidence)")
    if story_forecast is not None and story_forecast.confidence >= 55:
        parts.append(
            f"forecast confidence is supportive ({story_forecast.confidence:.0f}%)"
        )
    if harvest is not None and harvest.allowed and setup_kind == "harvest":
        parts.append("harvest quality confirms a structured edge")
    if market_story is not None and market_story.volume_signal:
        if "confirm" in market_story.volume_signal.lower() or "sponsor" in market_story.volume_signal.lower():
            parts.append("volume confirms renewed participation")

    if trader_memory_recall is not None and trader_memory_recall.similar_count > 0:
        parts.append(
            f"memory recalls {trader_memory_recall.similar_count} similar narratives "
            f"({trader_memory_recall.success_rate:.0%} succeeded)"
        )

    if not parts:
        return "The setup offers learning value even where edge is modest — context is developing."
    joined = ", ".join(parts[:-1])
    if len(parts) > 1:
        return f"This is attractive because {joined}, and {parts[-1]}."
    return f"This is attractive because {parts[0]}."


def _contradicting_evidence(
    market_story: MarketStoryResult | None,
    indicator_interpretation: IndicatorInterpretation | None,
    story_evolution: NestedStoryState | None,
    story_forecast: StoryForecastResult | None,
) -> list[str]:
    items: list[str] = []
    if market_story is not None and market_story.synthesis is not None:
        items.extend(market_story.synthesis.contradicting_evidence[:3])
    if story_evolution is not None and story_evolution.conflict:
        items.append(
            f"Timeframe conflict: {story_evolution.alignment} alignment across nested layers"
        )
    if indicator_interpretation is not None and market_story is not None:
        story_lower = market_story.primary_story.lower()
        for reading in indicator_interpretation.psychological_readings:
            if reading.direction == "bearish" and "bull" in story_lower:
                items.append(f"{reading.indicator} reading leans bearish against bullish narrative")
            elif reading.direction == "bullish" and "bear" in story_lower:
                items.append(f"{reading.indicator} reading leans bullish against bearish narrative")
    if story_forecast is not None:
        probs = story_forecast.scenario_probabilities
        likely, _ = probs.most_likely()
        alt_scenarios = [
            (name, getattr(probs, name))
            for name in ("reversal", "exhaustion", "pullback")
            if name != likely and getattr(probs, name) >= 20.0
        ]
        for name, value in sorted(alt_scenarios, key=lambda x: -x[1])[:2]:
            items.append(f"Forecast assigns {value:.0f}% weight to {name} — not the base case")
    return items[:4]


def _build_trade_thesis(
    *,
    trend_label: str,
    happening: str,
    why: str,
    feel: str,
    likely_next: str,
    opportunity: str,
    attractive: str,
    contradicting: list[str],
) -> str:
    weakness_clause = ""
    if "weakness" in happening.lower() or "pullback" in likely_next.lower():
        weakness_clause = (
            "Recent weakness appears to be profit-taking rather than reversal. "
        )
    elif trend_label == "bullish" and "compression" in happening.lower():
        weakness_clause = "The pause looks like consolidation rather than distribution. "
    elif trend_label == "bearish":
        weakness_clause = "The bounce appears corrective rather than a trend change. "

    participation_clause = ""
    if "volume" in why.lower() or "sponsor" in feel.lower() or "accumulation" in feel.lower():
        participation_clause = "Volume flow confirms renewed participation. "
    elif "liquidity" in happening.lower() or "sweep" in happening.lower():
        participation_clause = (
            "Participants absorbed the liquidity sweep and defended the level. "
        )

    likely_clause = likely_next.split(".")[0].rstrip(".") + "."

    thesis_parts = [
        happening,
        weakness_clause,
        participation_clause,
        likely_clause,
    ]
    thesis = " ".join(p for p in thesis_parts if p).strip()
    thesis = " ".join(thesis.split())

    if attractive and "attractive because" in attractive.lower():
        extra = attractive.replace("This is attractive because ", "").rstrip(".")
        thesis += f" {extra.capitalize()}."
    if contradicting:
        thesis += f" Watch: {contradicting[0].rstrip('.')}."
    return thesis


__all__ = [
    "FORBIDDEN_OUTPUT",
    "HUMAN_TRADER_REASONING_DNA",
    "HumanTraderReasoningLayer",
    "TradeReasoning",
]
