"""Story Evolution Engine — market as living narrative with nested TF propagation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from core.helpers import pip_size_for_symbol

EVOLUTION_TIMEFRAMES = ("H8", "H4", "H1", "M15", "M5", "M1")

NovelStory = Literal[
    "bullish_campaign",
    "bearish_campaign",
    "accumulation",
    "distribution",
    "exhaustion",
    "compression",
    "expansion",
]

ChapterStory = Literal[
    "continuation",
    "pullback",
    "acceleration",
    "weakening",
    "reversal_attempt",
    "transition",
]

ParagraphStory = Literal[
    "buyers_defending",
    "sellers_defending",
    "liquidity_sweep",
    "compression",
    "breakout_attempt",
    "failed_breakout",
    "momentum_shift",
    "trend_pause",
]

SentenceStory = Literal[
    "bullish_engulfing",
    "bearish_engulfing",
    "rejection_wick",
    "momentum_burst",
    "absorption",
    "exhaustion_candle",
    "inside_bar",
    "outside_bar",
    "failed_break",
    "neutral",
]

AlignmentState = Literal["aligned", "partial", "conflict", "transition"]
ConfidenceTrend = Literal["strengthening", "stable", "deteriorating"]
ProbableEvolution = Literal[
    "strengthening",
    "deteriorating",
    "transition",
    "reversal_probable",
    "continuation_likely",
    "uncertain",
]

IMPACT_STRENGTHEN = 2
IMPACT_SUPPORT = 1
IMPACT_NEUTRAL = 0
IMPACT_WEAKEN = -1
IMPACT_STRONG_WEAKEN = -2
IMPACT_INVALIDATE = -3

LAYER_BY_TF: dict[str, str] = {
    "H8": "novel",
    "H4": "novel",
    "H1": "chapter",
    "M15": "paragraph",
    "M5": "paragraph",
    "M1": "sentence",
}

PROPAGATION_CHAIN = ("M1", "M5", "M15", "H1", "H4")


@dataclass(frozen=True)
class CandleImpact:
    """Evidence contributed by a single candle."""

    timeframe: str
    layer: str
    detection: str
    score: int
    narrative: str

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "layer": self.layer,
            "detection": self.detection,
            "score": self.score,
            "narrative": self.narrative,
        }


@dataclass(frozen=True)
class StoryTransition:
    """Recorded story change on a timeframe layer."""

    symbol: str
    timeframe: str
    layer: str
    old_story: str
    new_story: str
    impact_source: str
    confidence_before: float
    confidence_after: float
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "layer": self.layer,
            "old_story": self.old_story,
            "new_story": self.new_story,
            "impact_source": self.impact_source,
            "confidence_change": round(self.confidence_after - self.confidence_before, 2),
            "confidence_before": round(self.confidence_before, 2),
            "confidence_after": round(self.confidence_after, 2),
            "timestamp": self.timestamp,
        }


@dataclass
class StoryLayerState:
    """Per-timeframe evolving story state."""

    layer: str
    timeframe: str
    story: str
    confidence: float
    strength_score: float
    age: int
    recent_impacts: tuple[int, ...]
    evidence_count: int

    def to_dict(self) -> dict:
        return {
            "layer": self.layer,
            "timeframe": self.timeframe,
            "story": self.story,
            "confidence": round(self.confidence, 2),
            "strength_score": round(self.strength_score, 2),
            "age": self.age,
            "recent_impacts": list(self.recent_impacts),
            "evidence_count": self.evidence_count,
        }


@dataclass
class NestedStoryState:
    """Full nested story evolution for one symbol."""

    symbol: str
    novel: StoryLayerState
    chapter: StoryLayerState
    paragraph: StoryLayerState
    sentence: StoryLayerState
    alignment: AlignmentState
    transition: bool
    conflict: bool
    probable_evolution: ProbableEvolution
    impact_accumulation: float
    confidence_trend: ConfidenceTrend
    latest_impact: CandleImpact | None = None
    macro_story: str = ""
    chapter_story: str = ""
    paragraph_story: str = ""
    sentence_story: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "novel": self.novel.to_dict(),
            "chapter": self.chapter.to_dict(),
            "paragraph": self.paragraph.to_dict(),
            "sentence": self.sentence.to_dict(),
            "alignment": self.alignment,
            "transition": self.transition,
            "conflict": self.conflict,
            "probable_evolution": self.probable_evolution,
            "impact_accumulation": round(self.impact_accumulation, 2),
            "confidence_trend": self.confidence_trend,
            "macro_story": self.macro_story,
            "chapter_story": self.chapter_story,
            "paragraph_story": self.paragraph_story,
            "sentence_story": self.sentence_story,
            "latest_impact": self.latest_impact.to_dict() if self.latest_impact else None,
        }


@dataclass
class EvolutionStats:
    """Accumulated evolution metrics for validation reporting."""

    transitions_detected: int = 0
    impacts_recorded: int = 0
    forecast_adjustments: int = 0
    opportunity_informed: int = 0
    adaptation_events: int = 0


class StoryEvolutionEngine:
    """Evolve nested market stories candle-by-candle with TF propagation."""

    RECENT_IMPACTS_MAX = 8
    CONFIDENCE_BASE = 50.0

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self._latest: dict[str, NestedStoryState] = {}
        self._prior_layers: dict[str, dict[str, StoryLayerState]] = {}
        self._transitions: list[StoryTransition] = []
        self._impacts: list[tuple[str, CandleImpact]] = []
        self._forecast_adjustments: list[dict] = []
        self.stats = EvolutionStats()

    def update(
        self,
        symbol: str,
        candles_by_tf: dict[str, pd.DataFrame],
    ) -> NestedStoryState:
        """Update nested story state from multi-timeframe candles."""
        symbol = symbol.strip().upper()
        prior = self._prior_layers.get(symbol, {})
        now = datetime.now(timezone.utc).isoformat()

        sentence_impact = self._detect_sentence(candles_by_tf.get("M1"), symbol)
        paragraph_impact = self._detect_paragraph(
            candles_by_tf.get("M15"), candles_by_tf.get("M5"), symbol
        )
        chapter_impact = self._detect_chapter(candles_by_tf.get("H1"), symbol)
        novel_impact = self._detect_novel(
            candles_by_tf.get("H8"), candles_by_tf.get("H4"), symbol
        )

        impacts_by_tf: dict[str, CandleImpact] = {}
        if sentence_impact:
            impacts_by_tf["M1"] = sentence_impact
        if paragraph_impact:
            impacts_by_tf["M15"] = paragraph_impact
            impacts_by_tf.setdefault("M5", paragraph_impact)
        if chapter_impact:
            impacts_by_tf["H1"] = chapter_impact
        if novel_impact:
            impacts_by_tf["H4"] = novel_impact
            impacts_by_tf.setdefault("H8", novel_impact)

        propagated = self._propagate_impacts(impacts_by_tf, candles_by_tf, symbol)

        sentence = self._build_layer(
            symbol=symbol,
            layer="sentence",
            timeframe="M1",
            story=self._sentence_story(candles_by_tf.get("M1"), symbol),
            prior=prior.get("M1"),
            impact=propagated.get("M1"),
            context_story=None,
        )
        paragraph = self._build_layer(
            symbol=symbol,
            layer="paragraph",
            timeframe="M15",
            story=self._paragraph_story(
                candles_by_tf.get("M15"), candles_by_tf.get("M5"), symbol
            ),
            prior=prior.get("M15"),
            impact=propagated.get("M15"),
            context_story=sentence.story,
        )
        chapter = self._build_layer(
            symbol=symbol,
            layer="chapter",
            timeframe="H1",
            story=self._chapter_story(candles_by_tf.get("H1"), symbol),
            prior=prior.get("H1"),
            impact=propagated.get("H1"),
            context_story=paragraph.story,
        )
        novel = self._build_layer(
            symbol=symbol,
            layer="novel",
            timeframe="H4",
            story=self._novel_story(
                candles_by_tf.get("H8"), candles_by_tf.get("H4"), symbol
            ),
            prior=prior.get("H4"),
            impact=propagated.get("H4"),
            context_story=chapter.story,
        )

        self._record_transitions(symbol, prior, {
            "M1": sentence,
            "M15": paragraph,
            "H1": chapter,
            "H4": novel,
        }, now)

        alignment, transition, conflict = self._assess_alignment(
            novel, chapter, paragraph, sentence
        )
        impact_accumulation = self._impact_accumulation(
            novel, chapter, paragraph, sentence
        )
        confidence_trend = self._confidence_trend(novel, chapter, paragraph, sentence)
        probable = self._probable_evolution(
            alignment, transition, conflict, confidence_trend, impact_accumulation
        )

        latest = propagated.get("M1") or propagated.get("M15") or propagated.get("H1")

        state = NestedStoryState(
            symbol=symbol,
            novel=novel,
            chapter=chapter,
            paragraph=paragraph,
            sentence=sentence,
            alignment=alignment,
            transition=transition,
            conflict=conflict,
            probable_evolution=probable,
            impact_accumulation=impact_accumulation,
            confidence_trend=confidence_trend,
            latest_impact=latest,
            macro_story=novel.story,
            chapter_story=chapter.story,
            paragraph_story=paragraph.story,
            sentence_story=sentence.story,
        )
        self._latest[symbol] = state
        self._prior_layers[symbol] = {
            "M1": sentence,
            "M15": paragraph,
            "H1": chapter,
            "H4": novel,
        }
        for impact in propagated.values():
            self._impacts.append((symbol, impact))
            self.stats.impacts_recorded += 1
        if transition:
            self.stats.transitions_detected += 1
        self.stats.adaptation_events += 1
        return state

    def record_forecast_adjustment(
        self,
        symbol: str,
        *,
        adjustment: str,
        confidence_delta: float,
    ) -> None:
        """Track forecast adaptations driven by evolution state."""
        self._forecast_adjustments.append({
            "symbol": symbol,
            "adjustment": adjustment,
            "confidence_delta": confidence_delta,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.stats.forecast_adjustments += 1

    def record_opportunity_informed(self) -> None:
        self.stats.opportunity_informed += 1

    def write_evolution_report(self, path: Path | None = None) -> Path | None:
        if not self._latest or self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "story_evolution_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Story Evolution Report",
            "",
            f"**Generated:** {now}",
            "",
            "Nested story layers — novel → chapter → paragraph → sentence.",
            "",
        ]
        for symbol in sorted(self._latest):
            s = self._latest[symbol]
            lines.extend([
                f"## {symbol}",
                "",
                f"**Alignment:** {s.alignment} | **Evolution:** {s.probable_evolution} | "
                f"**Trend:** {s.confidence_trend} | **Impact acc:** {s.impact_accumulation:+.1f}",
                "",
                "| Layer | TF | Story | Conf | Strength | Age | Evidence |",
                "|-------|-----|-------|------|----------|-----|----------|",
                self._layer_row(s.novel),
                self._layer_row(s.chapter),
                self._layer_row(s.paragraph),
                self._layer_row(s.sentence),
                "",
            ])
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_transition_report(self, path: Path | None = None) -> Path | None:
        if self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "story_transition_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Story Transition Report",
            "",
            f"**Generated:** {now}",
            f"**Transitions:** {len(self._transitions)}",
            "",
            "| Symbol | TF | Layer | Old → New | Impact source | Conf Δ |",
            "|--------|-----|-------|-----------|---------------|--------|",
        ]
        for t in self._transitions[-200:]:
            delta = t.confidence_after - t.confidence_before
            lines.append(
                f"| {t.symbol} | {t.timeframe} | {t.layer} | "
                f"{t.old_story} → {t.new_story} | {t.impact_source} | {delta:+.1f} |"
            )
        if not self._transitions:
            lines.append("| — | — | — | — | — | — |")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_impact_report(self, path: Path | None = None) -> Path | None:
        if self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "story_impact_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Story Impact Report",
            "",
            f"**Generated:** {now}",
            f"**Impacts recorded:** {len(self._impacts)}",
            f"**Forecast adjustments:** {len(self._forecast_adjustments)}",
            "",
            "## Recent impacts",
            "",
            "| Symbol | TF | Detection | Score | Narrative |",
            "|--------|-----|-----------|-------|-----------|",
        ]
        for sym, impact in self._impacts[-150:]:
            lines.append(
                f"| {sym} | {impact.timeframe} | {impact.detection} | "
                f"{impact.score:+d} | {impact.narrative[:40]} |"
            )
        if not self._impacts:
            lines.append("| — | — | — | — | — |")
        lines.extend(["", "## Forecast adjustments", ""])
        for adj in self._forecast_adjustments[-50:]:
            lines.append(
                f"- **{adj['symbol']}:** {adj['adjustment']} "
                f"({adj['confidence_delta']:+.1f} conf)"
            )
        if not self._forecast_adjustments:
            lines.append("- None recorded")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_all_reports(self) -> tuple[Path | None, Path | None, Path | None]:
        return (
            self.write_evolution_report(),
            self.write_transition_report(),
            self.write_impact_report(),
        )

    @staticmethod
    def _layer_row(layer: StoryLayerState) -> str:
        return (
            f"| {layer.layer} | {layer.timeframe} | {layer.story} | "
            f"{layer.confidence:.0f} | {layer.strength_score:.1f} | "
            f"{layer.age} | {layer.evidence_count} |"
        )

    def _propagate_impacts(
        self,
        impacts: dict[str, CandleImpact],
        candles_by_tf: dict[str, pd.DataFrame],
        symbol: str,
    ) -> dict[str, CandleImpact]:
        """Lower TF impacts accumulate upward; higher TF context modulates lower."""
        result = dict(impacts)
        novel_story = self._novel_story(
            candles_by_tf.get("H8"), candles_by_tf.get("H4"), symbol
        )
        chapter_story = self._chapter_story(candles_by_tf.get("H1"), symbol)

        for tf in PROPAGATION_CHAIN:
            if tf not in result and tf != "M1":
                lower = self._lower_tf(tf)
                if lower and lower in result:
                    lower_impact = result[lower]
                    accumulated = self._accumulate_upward(lower_impact, tf)
                    if accumulated:
                        result[tf] = accumulated

        if "M1" in result:
            result["M1"] = self._modulate_by_context(
                result["M1"], novel_story, chapter_story
            )
        if "M5" in result or "M15" in result:
            for ptf in ("M5", "M15"):
                if ptf in result:
                    result[ptf] = self._modulate_by_context(
                        result[ptf], novel_story, chapter_story
                    )
        return result

    @staticmethod
    def _lower_tf(tf: str) -> str | None:
        chain = list(PROPAGATION_CHAIN)
        if tf not in chain:
            return None
        idx = chain.index(tf)
        return chain[idx - 1] if idx > 0 else None

    def _accumulate_upward(self, lower: CandleImpact, target_tf: str) -> CandleImpact | None:
        layer = LAYER_BY_TF.get(target_tf, "paragraph")
        if lower.score >= IMPACT_SUPPORT:
            detection = "momentum_shift" if target_tf in {"M5", "M15"} else "continuation"
            score = min(lower.score, IMPACT_SUPPORT)
        elif lower.score <= IMPACT_WEAKEN:
            detection = "momentum_shift" if target_tf in {"M5", "M15"} else "weakening"
            score = max(lower.score, IMPACT_WEAKEN)
        else:
            return None
        return CandleImpact(
            timeframe=target_tf,
            layer=layer,
            detection=detection,
            score=score,
            narrative=f"Propagated from {lower.timeframe}: {lower.detection}",
        )

    @staticmethod
    def _modulate_by_context(
        impact: CandleImpact,
        novel_story: str,
        chapter_story: str,
    ) -> CandleImpact:
        """Higher TF context dampens counter-trend lower TF signals."""
        bullish_novel = novel_story in {"bullish_campaign", "accumulation", "expansion"}
        bearish_novel = novel_story in {"bearish_campaign", "distribution", "exhaustion"}
        bearish_sentence = impact.detection in {
            "bearish_engulfing", "rejection_wick", "failed_break"
        }
        bullish_sentence = impact.detection in {"bullish_engulfing", "momentum_burst"}

        if bullish_novel and bearish_sentence and impact.score < 0:
            if chapter_story in {"continuation", "pullback", "acceleration"}:
                dampened = max(impact.score + 1, IMPACT_WEAKEN)
                return CandleImpact(
                    timeframe=impact.timeframe,
                    layer=impact.layer,
                    detection=impact.detection,
                    score=dampened,
                    narrative=f"{impact.narrative} (H4 bullish — likely pullback)",
                )
        if bearish_novel and bullish_sentence and impact.score > 0:
            if chapter_story in {"continuation", "pullback"}:
                dampened = min(impact.score - 1, IMPACT_SUPPORT)
                return CandleImpact(
                    timeframe=impact.timeframe,
                    layer=impact.layer,
                    detection=impact.detection,
                    score=dampened,
                    narrative=f"{impact.narrative} (H4 bearish — likely pullback)",
                )
        return impact

    def _build_layer(
        self,
        *,
        symbol: str,
        layer: str,
        timeframe: str,
        story: str,
        prior: StoryLayerState | None,
        impact: CandleImpact | None,
        context_story: str | None,
    ) -> StoryLayerState:
        impacts: list[int] = list(prior.recent_impacts) if prior else []
        if impact is not None:
            impacts.append(impact.score)
        impacts = impacts[-self.RECENT_IMPACTS_MAX :]

        age = 0 if prior is None or prior.story != story else prior.age + 1
        evidence = (prior.evidence_count if prior else 0) + (1 if impact else 0)

        conf = self.CONFIDENCE_BASE
        if prior is not None:
            conf = prior.confidence
        if impact is not None:
            conf += impact.score * 3.5
        conf = max(5.0, min(98.0, conf))

        strength = sum(impacts) / max(len(impacts), 1) * 10.0
        if context_story and story != context_story:
            strength *= 0.85

        return StoryLayerState(
            layer=layer,
            timeframe=timeframe,
            story=story,
            confidence=conf,
            strength_score=strength,
            age=age,
            recent_impacts=tuple(impacts),
            evidence_count=evidence,
        )

    def _record_transitions(
        self,
        symbol: str,
        prior: dict[str, StoryLayerState],
        current: dict[str, StoryLayerState],
        timestamp: str,
    ) -> None:
        for tf, layer_state in current.items():
            old = prior.get(tf)
            if old is None or old.story == layer_state.story:
                continue
            source = "candle_evidence"
            if layer_state.recent_impacts:
                source = f"impact_{layer_state.recent_impacts[-1]:+d}"
            transition = StoryTransition(
                symbol=symbol,
                timeframe=tf,
                layer=layer_state.layer,
                old_story=old.story,
                new_story=layer_state.story,
                impact_source=source,
                confidence_before=old.confidence,
                confidence_after=layer_state.confidence,
                timestamp=timestamp,
            )
            self._transitions.append(transition)

    @staticmethod
    def _assess_alignment(
        novel: StoryLayerState,
        chapter: StoryLayerState,
        paragraph: StoryLayerState,
        sentence: StoryLayerState,
    ) -> tuple[AlignmentState, bool, bool]:
        bullish = {"bullish_campaign", "accumulation", "expansion", "bullish_engulfing",
                   "buyers_defending", "continuation", "acceleration", "momentum_burst"}
        bearish = {"bearish_campaign", "distribution", "exhaustion", "bearish_engulfing",
                   "sellers_defending", "reversal_attempt", "failed_breakout"}

        stories = (novel.story, chapter.story, paragraph.story, sentence.story)
        bull_count = sum(1 for s in stories if s in bullish)
        bear_count = sum(1 for s in stories if s in bearish)

        transition = chapter.story in {"transition", "reversal_attempt", "weakening"}
        conflict = bull_count >= 2 and bear_count >= 2

        if conflict:
            return "conflict", transition, True
        if transition:
            return "transition", True, False
        if bull_count >= 3 or bear_count >= 3:
            return "aligned", transition, False
        return "partial", transition, False

    @staticmethod
    def _impact_accumulation(
        novel: StoryLayerState,
        chapter: StoryLayerState,
        paragraph: StoryLayerState,
        sentence: StoryLayerState,
    ) -> float:
        all_impacts = (
            list(novel.recent_impacts)
            + list(chapter.recent_impacts)
            + list(paragraph.recent_impacts)
            + list(sentence.recent_impacts)
        )
        return float(sum(all_impacts))

    @staticmethod
    def _confidence_trend(
        novel: StoryLayerState,
        chapter: StoryLayerState,
        paragraph: StoryLayerState,
        sentence: StoryLayerState,
    ) -> ConfidenceTrend:
        layers = (novel, chapter, paragraph, sentence)
        deltas = []
        for layer in layers:
            if len(layer.recent_impacts) >= 2:
                deltas.append(layer.recent_impacts[-1] - layer.recent_impacts[-2])
        if not deltas:
            return "stable"
        avg = sum(deltas) / len(deltas)
        if avg >= 1:
            return "strengthening"
        if avg <= -1:
            return "deteriorating"
        return "stable"

    @staticmethod
    def _probable_evolution(
        alignment: AlignmentState,
        transition: bool,
        conflict: bool,
        confidence_trend: ConfidenceTrend,
        impact_accumulation: float,
    ) -> ProbableEvolution:
        if conflict and transition:
            return "reversal_probable"
        if transition:
            return "transition"
        if confidence_trend == "strengthening" and impact_accumulation > 2:
            return "strengthening"
        if confidence_trend == "deteriorating" and impact_accumulation < -2:
            return "deteriorating"
        if alignment == "aligned":
            return "continuation_likely"
        return "uncertain"

    @staticmethod
    def _frame_metrics(frame: pd.DataFrame, symbol: str) -> dict:
        closes = frame["close"].astype(float).values
        highs = frame["high"].astype(float).values
        lows = frame["low"].astype(float).values
        volumes = (
            frame["tick_volume"].astype(float).values
            if "tick_volume" in frame.columns
            else np.ones(len(closes))
        )
        pip = pip_size_for_symbol(symbol)
        recent_range = (highs[-8:].max() - lows[-8:].min()) / pip
        prior_range = (
            (highs[-20:-8].max() - lows[-20:-8].min()) / pip
            if len(closes) >= 20
            else recent_range
        )
        range_ratio = recent_range / max(prior_range, 0.1)
        vol_recent = volumes[-5:].mean()
        vol_prior = volumes[-15:-5].mean() if len(volumes) >= 15 else vol_recent
        vol_ratio = vol_recent / max(vol_prior, 1.0)
        momentum = (closes[-1] - closes[-8]) / pip if len(closes) >= 8 else 0.0
        opens = frame["open"].astype(float).values
        body = abs(closes[-1] - opens[-1])
        wick_upper = highs[-1] - max(closes[-1], opens[-1])
        wick_lower = min(closes[-1], opens[-1]) - lows[-1]
        rejection = wick_upper > body * 1.5 or wick_lower > body * 1.5
        return {
            "range_ratio": range_ratio,
            "vol_ratio": vol_ratio,
            "momentum": momentum,
            "rejection": rejection,
            "body": body,
            "wick_upper": wick_upper,
            "wick_lower": wick_lower,
            "closes": closes,
            "opens": opens,
            "highs": highs,
            "lows": lows,
            "pip": pip,
        }

    def _novel_story(
        self,
        h8: pd.DataFrame | None,
        h4: pd.DataFrame | None,
        symbol: str,
    ) -> str:
        frame = h4 if h4 is not None and len(h4) >= 5 else h8
        if frame is None or len(frame) < 5:
            return "accumulation"
        m = self._frame_metrics(frame, symbol)
        if m["range_ratio"] < 0.65 and m["vol_ratio"] < 0.85:
            return "compression"
        if m["range_ratio"] > 1.35 and m["vol_ratio"] > 1.2:
            return "bullish_campaign" if m["momentum"] > 0 else "bearish_campaign"
        if m["vol_ratio"] > 1.5 and abs(m["momentum"]) < 3.0:
            return "exhaustion"
        if m["vol_ratio"] < 0.75:
            return "accumulation" if m["momentum"] >= 0 else "distribution"
        if abs(m["momentum"]) > 4.0:
            return "expansion"
        return "bullish_campaign" if m["momentum"] > 0 else "bearish_campaign"

    def _chapter_story(self, h1: pd.DataFrame | None, symbol: str) -> str:
        if h1 is None or len(h1) < 5:
            return "transition"
        m = self._frame_metrics(h1, symbol)
        if m["range_ratio"] > 1.2 and m["rejection"]:
            return "reversal_attempt"
        if abs(m["momentum"]) > 5.0 and m["vol_ratio"] > 1.1:
            return "acceleration"
        if m["vol_ratio"] > 1.3 and abs(m["momentum"]) < 2.0:
            return "weakening"
        if abs(m["momentum"]) < 2.0 and m["range_ratio"] < 0.9:
            return "pullback"
        if m["range_ratio"] > 1.1:
            return "continuation"
        return "transition"

    def _paragraph_story(
        self,
        m15: pd.DataFrame | None,
        m5: pd.DataFrame | None,
        symbol: str,
    ) -> str:
        frame = m15 if m15 is not None and len(m15) >= 5 else m5
        if frame is None or len(frame) < 5:
            return "trend_pause"
        m = self._frame_metrics(frame, symbol)
        if m["rejection"] and m["range_ratio"] > 1.0:
            return "liquidity_sweep"
        if m["range_ratio"] < 0.7:
            return "compression"
        if m["range_ratio"] > 1.2 and m["momentum"] > 2:
            return "breakout_attempt"
        if m["range_ratio"] > 1.1 and m["rejection"]:
            return "failed_breakout"
        if m["momentum"] > 1.5:
            return "buyers_defending"
        if m["momentum"] < -1.5:
            return "sellers_defending"
        if abs(m["momentum"]) < 1.0:
            return "trend_pause"
        return "momentum_shift"

    def _sentence_story(self, m1: pd.DataFrame | None, symbol: str) -> str:
        if m1 is None or len(m1) < 3:
            return "neutral"
        m = self._frame_metrics(m1, symbol)
        closes, opens = m["closes"], m["opens"]
        if len(closes) >= 2:
            prev_body = abs(closes[-2] - opens[-2])
            body = m["body"]
            if closes[-1] > opens[-1] and closes[-2] < opens[-2] and body > prev_body * 1.1:
                return "bullish_engulfing"
            if closes[-1] < opens[-1] and closes[-2] > opens[-2] and body > prev_body * 1.1:
                return "bearish_engulfing"
        full_range = max(m["highs"][-1] - m["lows"][-1], m["pip"] * 0.1)
        if m["body"] < full_range * 0.35 and (
            m["wick_upper"] > m["body"] * 2 or m["wick_lower"] > m["body"] * 2
        ):
            return "rejection_wick"
        if m["body"] > full_range * 0.65:
            return "momentum_burst"
        if m["vol_ratio"] > 1.4 and m["body"] < full_range * 0.3:
            return "absorption"
        if m["vol_ratio"] > 1.5 and abs(m["momentum"]) < 1.0:
            return "exhaustion_candle"
        if len(closes) >= 2:
            if m["highs"][-1] <= m["highs"][-2] and m["lows"][-1] >= m["lows"][-2]:
                return "inside_bar"
            if m["highs"][-1] > m["highs"][-2] and m["lows"][-1] < m["lows"][-2]:
                return "outside_bar"
        if m["rejection"] and m["range_ratio"] > 1.0:
            return "failed_break"
        return "neutral"

    def _detect_sentence(
        self, m1: pd.DataFrame | None, symbol: str
    ) -> CandleImpact | None:
        story = self._sentence_story(m1, symbol)
        if story == "neutral" or m1 is None:
            return None
        score_map: dict[str, int] = {
            "bullish_engulfing": IMPACT_STRENGTHEN,
            "bearish_engulfing": IMPACT_STRONG_WEAKEN,
            "rejection_wick": IMPACT_WEAKEN,
            "momentum_burst": IMPACT_STRENGTHEN,
            "absorption": IMPACT_SUPPORT,
            "exhaustion_candle": IMPACT_STRONG_WEAKEN,
            "inside_bar": IMPACT_NEUTRAL,
            "outside_bar": IMPACT_SUPPORT,
            "failed_break": IMPACT_INVALIDATE,
        }
        return CandleImpact(
            timeframe="M1",
            layer="sentence",
            detection=story,
            score=score_map.get(story, IMPACT_NEUTRAL),
            narrative=f"M1 {story.replace('_', ' ')}",
        )

    def _detect_paragraph(
        self,
        m15: pd.DataFrame | None,
        m5: pd.DataFrame | None,
        symbol: str,
    ) -> CandleImpact | None:
        story = self._paragraph_story(m15, m5, symbol)
        score_map: dict[str, int] = {
            "buyers_defending": IMPACT_STRENGTHEN,
            "sellers_defending": IMPACT_STRONG_WEAKEN,
            "liquidity_sweep": IMPACT_SUPPORT,
            "compression": IMPACT_NEUTRAL,
            "breakout_attempt": IMPACT_STRENGTHEN,
            "failed_breakout": IMPACT_INVALIDATE,
            "momentum_shift": IMPACT_WEAKEN,
            "trend_pause": IMPACT_NEUTRAL,
        }
        tf = "M15" if m15 is not None and len(m15) >= 5 else "M5"
        return CandleImpact(
            timeframe=tf,
            layer="paragraph",
            detection=story,
            score=score_map.get(story, IMPACT_NEUTRAL),
            narrative=f"{tf} {story.replace('_', ' ')}",
        )

    def _detect_chapter(self, h1: pd.DataFrame | None, symbol: str) -> CandleImpact | None:
        story = self._chapter_story(h1, symbol)
        score_map: dict[str, int] = {
            "continuation": IMPACT_STRENGTHEN,
            "pullback": IMPACT_SUPPORT,
            "acceleration": IMPACT_STRENGTHEN,
            "weakening": IMPACT_WEAKEN,
            "reversal_attempt": IMPACT_STRONG_WEAKEN,
            "transition": IMPACT_NEUTRAL,
        }
        return CandleImpact(
            timeframe="H1",
            layer="chapter",
            detection=story,
            score=score_map.get(story, IMPACT_NEUTRAL),
            narrative=f"H1 {story.replace('_', ' ')}",
        )

    def _detect_novel(
        self,
        h8: pd.DataFrame | None,
        h4: pd.DataFrame | None,
        symbol: str,
    ) -> CandleImpact | None:
        story = self._novel_story(h8, h4, symbol)
        score_map: dict[str, int] = {
            "bullish_campaign": IMPACT_STRENGTHEN,
            "bearish_campaign": IMPACT_STRONG_WEAKEN,
            "accumulation": IMPACT_SUPPORT,
            "distribution": IMPACT_WEAKEN,
            "exhaustion": IMPACT_STRONG_WEAKEN,
            "compression": IMPACT_NEUTRAL,
            "expansion": IMPACT_STRENGTHEN,
        }
        return CandleImpact(
            timeframe="H4",
            layer="novel",
            detection=story,
            score=score_map.get(story, IMPACT_NEUTRAL),
            narrative=f"H4 {story.replace('_', ' ')}",
        )
