"""Market Story Engine — multi-timeframe market understanding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from core.helpers import pip_size_for_symbol
from intelligence.evidence_synthesis_engine import EvidenceSynthesisEngine, MarketStorySummary
from intelligence.harvest_opportunity_score import infer_session
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult

if TYPE_CHECKING:
    from intelligence.story_evolution_engine import NestedStoryState

STORY_TIMEFRAMES = ("H8", "H4", "H1", "M15", "M5", "M1")

MacroStory = Literal[
    "trending",
    "ranging",
    "accumulation",
    "distribution",
    "compression",
    "expansion",
    "exhaustion",
]

H1Integrity = Literal["confirmed", "weakening", "changing"]

OpportunityType = Literal[
    "pullback_continuation",
    "liquidity_sweep",
    "breakout_retest",
    "failed_breakout",
    "compression_breakout",
    "trend_pause_resume",
    "mean_reversion_snapback",
    "session_transition",
]

M1Strike = Literal[
    "engulfing",
    "pin_bar",
    "rejection",
    "momentum",
    "inside_bar",
    "outside_bar",
    "none",
]


@dataclass(frozen=True)
class MacroStorySlice:
    """H8/H4 — what is the big story?"""

    timeframe: str
    story: MacroStory
    narrative: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "story": self.story,
            "narrative": self.narrative,
            "confidence": round(self.confidence, 2),
        }


@dataclass(frozen=True)
class H1StorySlice:
    """H1 — is the story intact?"""

    integrity: H1Integrity
    narrative: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "integrity": self.integrity,
            "narrative": self.narrative,
            "confidence": round(self.confidence, 2),
        }


@dataclass(frozen=True)
class OpportunitySlice:
    """M15/M5 — where is the next opportunity?"""

    timeframe: str
    opportunity_type: OpportunityType | None
    narrative: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "opportunity_type": self.opportunity_type,
            "narrative": self.narrative,
            "confidence": round(self.confidence, 2),
        }


@dataclass(frozen=True)
class StrikeSlice:
    """M1 — where exactly do we strike?"""

    strike: M1Strike
    narrative: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "strike": self.strike,
            "narrative": self.narrative,
            "confidence": round(self.confidence, 2),
        }


@dataclass(frozen=True)
class MarketStoryResult:
    """Full market story for one asset."""

    symbol: str
    macro_slices: tuple[MacroStorySlice, ...]
    macro_story: MacroStory
    h1_integrity: H1Integrity
    h1_slice: H1StorySlice
    opportunity_slices: tuple[OpportunitySlice, ...]
    opportunity_type: OpportunityType | None
    strike: StrikeSlice
    story_clear: bool
    primary_story: str
    overall_confidence: float
    volume_signal: str
    structure_signal: str
    rejection_detected: bool = False
    compression_detected: bool = False
    exhaustion_detected: bool = False
    synthesis: MarketStorySummary | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "macro_story": self.macro_story,
            "h1_integrity": self.h1_integrity,
            "opportunity_type": self.opportunity_type,
            "strike": self.strike.strike,
            "story_clear": self.story_clear,
            "primary_story": self.primary_story,
            "overall_confidence": round(self.overall_confidence, 2),
            "volume_signal": self.volume_signal,
            "structure_signal": self.structure_signal,
            "rejection_detected": self.rejection_detected,
            "compression_detected": self.compression_detected,
            "exhaustion_detected": self.exhaustion_detected,
            "macro_slices": [s.to_dict() for s in self.macro_slices],
            "h1_slice": self.h1_slice.to_dict(),
            "opportunity_slices": [s.to_dict() for s in self.opportunity_slices],
            "strike_slice": self.strike.to_dict(),
            "synthesis": self.synthesis.to_dict() if self.synthesis else None,
        }

    def to_narrative_result(self):
        """Bridge to legacy narrative types for forecast feedback and council."""
        from intelligence.market_narrative_engine import (
            MarketNarrativeResult,
            MicroNarrativeClass,
            NarrativePhase,
            TimeframeNarrative,
        )

        phase_map: dict[MacroStory, NarrativePhase] = {
            "trending": "continuation",
            "ranging": "ranging",
            "accumulation": "accumulation",
            "distribution": "distribution",
            "compression": "compression",
            "expansion": "expansion",
            "exhaustion": "exhaustion",
        }
        opp_to_micro: dict[OpportunityType, MicroNarrativeClass] = {
            "pullback_continuation": "micro_pullback_continuation",
            "liquidity_sweep": "liquidity_sweep_snapback",
            "breakout_retest": "breakout_retest_harvest",
            "failed_breakout": "failed_breakout_return",
            "compression_breakout": "compression_pop",
            "trend_pause_resume": "trend_pause_resume",
            "mean_reversion_snapback": "liquidity_sweep_snapback",
            "session_transition": "session_open_push",
        }
        slices: list[TimeframeNarrative] = []
        for ms in self.macro_slices:
            phase = phase_map.get(ms.story, "ranging")
            slices.append(
                TimeframeNarrative(
                    timeframe=ms.timeframe,
                    what=phase,
                    why=ms.narrative,
                    likely_next=f"Macro {ms.story}",
                    confidence=ms.confidence,
                )
            )
        slices.append(
            TimeframeNarrative(
                timeframe="H1",
                what=phase_map.get(self.macro_story, "ranging"),
                why=self.h1_slice.narrative,
                likely_next=f"Story {self.h1_integrity}",
                confidence=self.h1_slice.confidence,
            )
        )
        for opp in self.opportunity_slices:
            phase: NarrativePhase = "continuation"
            if opp.opportunity_type == "compression_breakout":
                phase = "compression"
            elif opp.opportunity_type == "liquidity_sweep":
                phase = "liquidity_sweep"
            elif opp.opportunity_type == "mean_reversion_snapback":
                phase = "mean_reversion"
            elif opp.opportunity_type == "failed_breakout":
                phase = "breakout_failure"
            slices.append(
                TimeframeNarrative(
                    timeframe=opp.timeframe,
                    what=phase,
                    why=opp.narrative,
                    likely_next=str(opp.opportunity_type or "watch"),
                    confidence=opp.confidence,
                )
            )
        if self.strike.strike != "none":
            slices.append(
                TimeframeNarrative(
                    timeframe="M1",
                    what="continuation",
                    why=self.strike.narrative,
                    likely_next=f"M1 {self.strike.strike}",
                    confidence=self.strike.confidence,
                )
            )
        micro = opp_to_micro.get(self.opportunity_type) if self.opportunity_type else None
        return MarketNarrativeResult(
            symbol=self.symbol,
            slices=tuple(slices),
            primary_story=self.primary_story,
            primary_phase=phase_map.get(self.macro_story, "ranging"),
            overall_confidence=self.overall_confidence,
            rejection_detected=self.rejection_detected,
            compression_detected=self.compression_detected,
            exhaustion_detected=self.exhaustion_detected,
            micro_narrative_class=micro,
        )


class MarketStoryEngine:
    """Read market story via evidence synthesis — one coherent explanation."""

    STORY_CLEAR_MIN = 38.0

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self._latest: dict[str, MarketStoryResult] = {}
        self._synthesis_engine = EvidenceSynthesisEngine(project_root)

    @property
    def synthesis_engine(self) -> EvidenceSynthesisEngine:
        return self._synthesis_engine

    def build(
        self,
        *,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        regime: RegimeResult,
        evaluation_moment: datetime | None = None,
        story_evolution_state: NestedStoryState | None = None,
        indicator_interpretation: object | None = None,
    ) -> MarketStoryResult:
        synthesis = self._synthesis_engine.synthesise(
            symbol,
            candles,
            structure=structure,
            bias=bias,
            regime=regime,
            story_evolution_state=story_evolution_state,
            evaluation_moment=evaluation_moment,
            indicator_interpretation=indicator_interpretation,
        )
        return self._build_from_synthesis(
            symbol=symbol,
            candles=candles,
            structure=structure,
            bias=bias,
            regime=regime,
            evaluation_moment=evaluation_moment,
            synthesis=synthesis,
        )

    def _build_legacy_slices(
        self,
        *,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        regime: RegimeResult,
        evaluation_moment: datetime | None = None,
    ) -> MarketStoryResult:
        macro_slices: list[MacroStorySlice] = []
        opp_slices: list[OpportunitySlice] = []
        rejection = False
        compression = False
        exhaustion = False

        for tf in ("H8", "H4"):
            frame = candles.get(tf)
            if frame is None or len(frame) < 5:
                continue
            ms = self._macro_story(tf, frame, symbol, structure, bias, regime)
            macro_slices.append(ms)
            if ms.story == "compression":
                compression = True
            if ms.story == "exhaustion":
                exhaustion = True

        if not macro_slices:
            macro_slices.append(
                MacroStorySlice("H4", "ranging", "Insufficient macro data", 30.0)
            )

        h1_frame = candles.get("H1")
        h1_slice = (
            self._h1_integrity(h1_frame, symbol, structure, bias, macro_slices)
            if h1_frame is not None and len(h1_frame) >= 5
            else H1StorySlice("changing", "H1 data unavailable", 35.0)
        )

        for tf in ("M15", "M5"):
            frame = candles.get(tf)
            if frame is None or len(frame) < 5:
                continue
            opp = self._opportunity_slice(
                tf, frame, symbol, structure, bias, macro_slices, evaluation_moment
            )
            opp_slices.append(opp)
            if opp.opportunity_type == "liquidity_sweep":
                rejection = True

        m1_frame = candles.get("M1")
        strike = (
            self._m1_strike(m1_frame, symbol, structure, bias)
            if m1_frame is not None and len(m1_frame) >= 3
            else StrikeSlice("none", "M1 unavailable", 30.0)
        )
        if strike.strike in {"pin_bar", "rejection", "engulfing"}:
            rejection = True

        macro_story = self._dominant_macro(macro_slices)
        opportunity_type = self._best_opportunity(opp_slices)
        volume_signal = self._volume_signal(candles)
        structure_signal = self._structure_signal(structure, bias)

        weights = {"H8": 0.2, "H4": 0.25, "H1": 0.25, "M15": 0.12, "M5": 0.12, "M1": 0.06}
        conf_parts = [
            (macro_slices[0].confidence, weights["H8"]),
            (macro_slices[-1].confidence, weights["H4"]),
            (h1_slice.confidence, weights["H1"]),
        ]
        if opp_slices:
            conf_parts.append((max(o.confidence for o in opp_slices), weights["M15"]))
        if strike.strike != "none":
            conf_parts.append((strike.confidence, weights["M1"]))
        overall = sum(c * w for c, w in conf_parts) / max(sum(w for _, w in conf_parts), 0.01)

        story_clear = overall >= self.STORY_CLEAR_MIN

        primary = f"{macro_story}: {macro_slices[-1].narrative}"
        if opportunity_type:
            primary = f"{opportunity_type.replace('_', ' ')} — {primary}"
        if h1_slice.integrity == "weakening":
            primary = f"[weakening] {primary}"

        result = MarketStoryResult(
            symbol=symbol,
            macro_slices=tuple(macro_slices),
            macro_story=macro_story,
            h1_integrity=h1_slice.integrity,
            h1_slice=h1_slice,
            opportunity_slices=tuple(opp_slices),
            opportunity_type=opportunity_type,
            strike=strike,
            story_clear=story_clear,
            primary_story=primary,
            overall_confidence=overall,
            volume_signal=volume_signal,
            structure_signal=structure_signal,
            rejection_detected=rejection,
            compression_detected=compression,
            exhaustion_detected=exhaustion,
        )
        return result

    def _build_from_synthesis(
        self,
        *,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        regime: RegimeResult,
        evaluation_moment: datetime | None,
        synthesis: MarketStorySummary,
    ) -> MarketStoryResult:
        """Map synthesised story to legacy MarketStoryResult for downstream consumers."""
        legacy = self._build_legacy_slices(
            symbol=symbol,
            candles=candles,
            structure=structure,
            bias=bias,
            regime=regime,
            evaluation_moment=evaluation_moment,
        )
        opp_hint = synthesis.opportunity_hint or legacy.opportunity_type
        if synthesis.opportunity_hint and legacy.opportunity_type is None:
            opp_hint = synthesis.opportunity_hint  # type: ignore[assignment]

        story_clear = synthesis.story_clear and synthesis.confidence >= self.STORY_CLEAR_MIN
        primary = synthesis.current_explanation
        if synthesis.contradicting_evidence:
            primary = f"[interpreted conflict] {primary}"

        result = MarketStoryResult(
            symbol=symbol,
            macro_slices=legacy.macro_slices,
            macro_story=legacy.macro_story,
            h1_integrity=legacy.h1_integrity,
            h1_slice=legacy.h1_slice,
            opportunity_slices=legacy.opportunity_slices,
            opportunity_type=opp_hint,  # type: ignore[arg-type]
            strike=legacy.strike,
            story_clear=story_clear,
            primary_story=primary,
            overall_confidence=synthesis.confidence,
            volume_signal=legacy.volume_signal,
            structure_signal=legacy.structure_signal,
            rejection_detected=legacy.rejection_detected,
            compression_detected=legacy.compression_detected,
            exhaustion_detected=legacy.exhaustion_detected,
            synthesis=synthesis,
        )
        self._latest[symbol] = result
        return result

    def write_report(self, path: Path | None = None) -> Path | None:
        if not self._latest or self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "market_story_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Market Story Report",
            "",
            f"**Generated:** {now}",
            "",
            "Price action + volume + structure drive story. Indicators assist only.",
            "",
        ]
        for symbol in sorted(self._latest):
            r = self._latest[symbol]
            lines.extend([
                f"## {symbol}",
                "",
                f"**Story:** {r.primary_story} ({r.overall_confidence:.0f}%)",
                f"**Clear:** {'YES' if r.story_clear else 'NO'} | "
                f"Macro: {r.macro_story} | H1: {r.h1_integrity} | "
                f"Opportunity: {r.opportunity_type or '—'} | Strike: {r.strike.strike}",
                "",
                f"- Volume: {r.volume_signal}",
                f"- Structure: {r.structure_signal}",
                "",
                "| TF | Layer | Detail | Conf |",
                "|----|-------|--------|------|",
            ])
            for ms in r.macro_slices:
                lines.append(
                    f"| {ms.timeframe} | macro | {ms.story} — {ms.narrative[:30]} | {ms.confidence:.0f} |"
                )
            lines.append(
                f"| H1 | integrity | {r.h1_integrity} — {r.h1_slice.narrative[:30]} | "
                f"{r.h1_slice.confidence:.0f} |"
            )
            for opp in r.opportunity_slices:
                lines.append(
                    f"| {opp.timeframe} | opportunity | {opp.opportunity_type or 'watch'} | "
                    f"{opp.confidence:.0f} |"
                )
            lines.append(
                f"| M1 | strike | {r.strike.strike} — {r.strike.narrative[:25]} | "
                f"{r.strike.confidence:.0f} |"
            )
            lines.append("")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def _macro_story(
        self,
        tf: str,
        frame: pd.DataFrame,
        symbol: str,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        regime: RegimeResult,
    ) -> MacroStorySlice:
        metrics = self._frame_metrics(frame, symbol)
        story, narrative, conf = self._classify_macro(
            metrics, structure, bias, regime, tf
        )
        return MacroStorySlice(tf, story, narrative, conf)

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
        body = abs(closes[-1] - frame["open"].astype(float).values[-1])
        full_range = max(highs[-1] - lows[-1], pip * 0.1)
        wick_upper = highs[-1] - max(closes[-1], frame["open"].astype(float).values[-1])
        wick_lower = min(closes[-1], frame["open"].astype(float).values[-1]) - lows[-1]
        rejection = wick_upper > body * 1.5 or wick_lower > body * 1.5
        return {
            "range_ratio": range_ratio,
            "vol_ratio": vol_ratio,
            "momentum": momentum,
            "rejection": rejection,
        }

    @staticmethod
    def _classify_macro(
        metrics: dict,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        regime: RegimeResult,
        tf: str,
    ) -> tuple[MacroStory, str, float]:
        rr = metrics["range_ratio"]
        vr = metrics["vol_ratio"]
        mom = metrics["momentum"]

        if rr < 0.65 and vr < 0.85:
            return "compression", "Range contracting — coiled energy", 68.0 if tf == "H4" else 60.0
        if rr > 1.35 and vr > 1.2:
            direction = "bullish" if mom > 0 else "bearish"
            return "expansion", f"Volatility expanding {direction}", 72.0
        if vr > 1.5 and abs(mom) < 3.0:
            return "exhaustion", "Climax volume without follow-through", 70.0
        if vr < 0.75 and abs(mom) < 2.0:
            phase = "accumulation" if bias.bias == "bullish" else "distribution"
            if bias.bias == "neutral":
                phase = "ranging"
            return phase, "Quiet volume — positioning phase", 58.0
        if regime.regime == "trending" or structure.trend in {"bullish", "bearish"}:
            conf = 65.0 + bias.confidence * 20.0
            return "trending", f"Directional {structure.trend} architecture", min(100.0, conf)
        if regime.regime == "ranging" or structure.trend == "ranging":
            return "ranging", "Balanced structure — no dominant trend", 52.0
        return "ranging", "Macro story developing", 48.0

    def _h1_integrity(
        self,
        frame: pd.DataFrame,
        symbol: str,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        macro_slices: list[MacroStorySlice],
    ) -> H1StorySlice:
        metrics = self._frame_metrics(frame, symbol)
        macro = macro_slices[-1].story if macro_slices else "ranging"
        aligned = (
            (bias.bias == "bullish" and structure.higher_lows)
            or (bias.bias == "bearish" and structure.lower_highs)
        )
        if macro in {"trending", "expansion"} and aligned and metrics["momentum"] * (
            1 if bias.bias == "bullish" else -1
        ) > 0:
            return H1StorySlice("confirmed", "H1 aligns with macro trend", 75.0)
        if metrics["range_ratio"] > 1.2 and metrics["rejection"]:
            return H1StorySlice("changing", "H1 rejection — story shifting", 55.0)
        if macro == "exhaustion" or (metrics["vol_ratio"] > 1.4 and abs(metrics["momentum"]) < 2):
            return H1StorySlice("weakening", "Momentum fading on H1", 62.0)
        if macro in {"compression", "accumulation", "distribution"}:
            return H1StorySlice("confirmed", f"H1 supports {macro} setup", 58.0)
        return H1StorySlice("changing", "H1 shifting — synthesis will interpret", 48.0)

    def _opportunity_slice(
        self,
        tf: str,
        frame: pd.DataFrame,
        symbol: str,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        macro_slices: list[MacroStorySlice],
        evaluation_moment: datetime | None,
    ) -> OpportunitySlice:
        metrics = self._frame_metrics(frame, symbol)
        macro = macro_slices[-1].story if macro_slices else "ranging"
        hour = evaluation_moment.hour if evaluation_moment else 12
        session = infer_session(hour)

        opp: OpportunityType | None = None
        narrative = "Monitoring local structure"
        conf = 50.0

        if metrics["rejection"] and structure.liquidity_zones:
            opp = "liquidity_sweep"
            narrative = "Sweep and rejection at liquidity"
            conf = 74.0
        elif macro == "compression" or metrics["range_ratio"] < 0.7:
            opp = "compression_breakout"
            narrative = "Compression pop setup"
            conf = 68.0
        elif structure.last_bos is not None and abs(metrics["momentum"]) < 4.0:
            opp = "pullback_continuation"
            narrative = "Pullback after BOS — continuation"
            conf = 72.0
        elif metrics["rejection"] and metrics["range_ratio"] > 1.1:
            opp = "failed_breakout"
            narrative = "Failed breakout — revert"
            conf = 66.0
        elif structure.last_bos is not None and metrics["momentum"] * (
            1 if bias.bias == "bullish" else -1 if bias.bias == "bearish" else 0
        ) > 2:
            opp = "breakout_retest"
            narrative = "Breakout retest entry"
            conf = 70.0
        elif macro == "exhaustion":
            opp = "mean_reversion_snapback"
            narrative = "Exhaustion snapback"
            conf = 71.0
        elif macro == "trending" and bias.bias != "neutral" and metrics["momentum"] * (
            1 if bias.bias == "bullish" else -1
        ) < 1.5:
            opp = "trend_pause_resume"
            narrative = "Trend pause — resume on momentum"
            conf = 65.0
        elif session in {"london", "london_ny_overlap"} and metrics["range_ratio"] > 1.1:
            opp = "session_transition"
            narrative = "Session transition momentum"
            conf = 67.0

        return OpportunitySlice(tf, opp, narrative, conf)

    @staticmethod
    def _m1_strike(
        frame: pd.DataFrame,
        symbol: str,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
    ) -> StrikeSlice:
        opens = frame["open"].astype(float).values
        closes = frame["close"].astype(float).values
        highs = frame["high"].astype(float).values
        lows = frame["low"].astype(float).values
        pip = pip_size_for_symbol(symbol)

        body = abs(closes[-1] - opens[-1])
        full_range = max(highs[-1] - lows[-1], pip * 0.1)
        wick_upper = highs[-1] - max(closes[-1], opens[-1])
        wick_lower = min(closes[-1], opens[-1]) - lows[-1]

        if len(closes) >= 2:
            prev_body = abs(closes[-2] - opens[-2])
            bullish_engulf = (
                closes[-1] > opens[-1]
                and closes[-2] < opens[-2]
                and body > prev_body * 1.1
            )
            bearish_engulf = (
                closes[-1] < opens[-1]
                and closes[-2] > opens[-2]
                and body > prev_body * 1.1
            )
            if bullish_engulf or bearish_engulf:
                return StrikeSlice("engulfing", "M1 engulfing bar", 78.0)

        if body < full_range * 0.35 and (wick_upper > body * 2 or wick_lower > body * 2):
            return StrikeSlice("pin_bar", "M1 pin bar rejection", 76.0)

        if wick_upper > body * 1.8 or wick_lower > body * 1.8:
            return StrikeSlice("rejection", "M1 wick rejection", 72.0)

        if body > full_range * 0.65:
            direction = "bullish" if closes[-1] > opens[-1] else "bearish"
            if direction == bias.bias or bias.bias == "neutral":
                return StrikeSlice("momentum", f"M1 momentum {direction}", 68.0)

        if len(closes) >= 2:
            prev_high = highs[-2]
            prev_low = lows[-2]
            if highs[-1] <= prev_high and lows[-1] >= prev_low:
                return StrikeSlice("inside_bar", "M1 inside bar — coil", 58.0)
            if highs[-1] > prev_high and lows[-1] < prev_low:
                return StrikeSlice("outside_bar", "M1 outside bar — expansion", 64.0)

        if structure.liquidity_zones:
            return StrikeSlice("rejection", "M1 at liquidity — strike zone", 60.0)

        return StrikeSlice("none", "No M1 strike pattern", 40.0)

    @staticmethod
    def _dominant_macro(slices: list[MacroStorySlice]) -> MacroStory:
        if not slices:
            return "ranging"
        return max(slices, key=lambda s: s.confidence).story

    @staticmethod
    def _best_opportunity(slices: list[OpportunitySlice]) -> OpportunityType | None:
        typed = [s for s in slices if s.opportunity_type is not None]
        if not typed:
            return None
        return max(typed, key=lambda s: s.confidence).opportunity_type

    @staticmethod
    def _volume_signal(candles: dict[str, pd.DataFrame]) -> str:
        m15 = candles.get("M15")
        if m15 is None or len(m15) < 10:
            return "volume neutral"
        vol = m15["tick_volume"].astype(float).values
        ratio = vol[-5:].mean() / max(vol[-15:-5].mean(), 1.0)
        if ratio > 1.3:
            return "participation expanding"
        if ratio < 0.75:
            return "accumulation — quiet bid"
        if ratio > 1.5:
            return "distribution — selling pressure"
        return "steady participation"

    @staticmethod
    def _structure_signal(structure: MarketContext, bias: MultiTimeframeBiasResult) -> str:
        parts = [f"trend {structure.trend}"]
        if structure.last_bos is not None:
            parts.append(f"BOS {structure.last_bos.kind}")
        if structure.liquidity_zones:
            parts.append("liquidity mapped")
        if bias.bias != "neutral":
            parts.append(f"bias {bias.bias}")
        return " | ".join(parts)
