"""Market Narrative Engine — story-first analysis per asset and timeframe."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from core.helpers import pip_size_for_symbol
from intelligence.harvest_opportunity_score import infer_session
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult

NARRATIVE_TIMEFRAMES = ("H8", "H4", "H1", "M15", "M5", "M1")

NarrativePhase = Literal[
    "accumulation",
    "distribution",
    "continuation",
    "exhaustion",
    "compression",
    "expansion",
    "ranging",
    "breakout",
    "breakout_failure",
    "liquidity_sweep",
    "mean_reversion",
]

MicroNarrativeClass = Literal[
    "micro_pullback_continuation",
    "liquidity_sweep_snapback",
    "breakout_retest_harvest",
    "compression_pop",
    "session_open_push",
    "failed_breakout_return",
    "trend_pause_resume",
]


@dataclass(frozen=True)
class TimeframeNarrative:
    """Narrative slice for one timeframe."""

    timeframe: str
    what: NarrativePhase
    why: str
    likely_next: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "what": self.what,
            "why": self.why,
            "likely_next": self.likely_next,
            "confidence": round(self.confidence, 2),
        }


@dataclass(frozen=True)
class MarketNarrativeResult:
    """Full multi-timeframe narrative for one symbol."""

    symbol: str
    slices: tuple[TimeframeNarrative, ...]
    primary_story: str
    primary_phase: NarrativePhase
    overall_confidence: float
    rejection_detected: bool = False
    compression_detected: bool = False
    exhaustion_detected: bool = False
    micro_narrative_class: MicroNarrativeClass | None = None

    def slice_for(self, timeframe: str) -> TimeframeNarrative | None:
        for s in self.slices:
            if s.timeframe == timeframe:
                return s
        return None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "primary_story": self.primary_story,
            "primary_phase": self.primary_phase,
            "overall_confidence": round(self.overall_confidence, 2),
            "rejection_detected": self.rejection_detected,
            "compression_detected": self.compression_detected,
            "exhaustion_detected": self.exhaustion_detected,
            "micro_narrative_class": self.micro_narrative_class,
            "slices": [s.to_dict() for s in self.slices],
        }


class MarketNarrativeEngine:
    """Build market story from price action and structure — indicators secondary."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self._latest: dict[str, MarketNarrativeResult] = {}

    def build(
        self,
        *,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        regime: RegimeResult,
        evaluation_moment: datetime | None = None,
    ) -> MarketNarrativeResult:
        slices: list[TimeframeNarrative] = []
        rejection = False
        compression = False
        exhaustion = False

        for tf in NARRATIVE_TIMEFRAMES:
            frame = candles.get(tf)
            if frame is None or len(frame) < 5:
                continue
            slice_narr = self._analyze_timeframe(
                timeframe=tf,
                frame=frame,
                symbol=symbol,
                structure=structure,
                bias=bias,
                regime=regime,
            )
            slices.append(slice_narr)
            if "rejection" in slice_narr.why.lower() or slice_narr.what == "liquidity_sweep":
                rejection = True
            if slice_narr.what == "compression":
                compression = True
            if slice_narr.what == "exhaustion":
                exhaustion = True

        if not slices:
            fallback = TimeframeNarrative(
                timeframe="H1",
                what="ranging",
                why="Insufficient candle data",
                likely_next="Wait for structure",
                confidence=30.0,
            )
            slices = [fallback]

        h1 = next((s for s in slices if s.timeframe == "H1"), slices[0])
        m15 = next((s for s in slices if s.timeframe == "M15"), None)
        weights = {"H8": 0.15, "H4": 0.2, "H1": 0.25, "M15": 0.15, "M5": 0.15, "M1": 0.1}
        conf_sum = sum(s.confidence * weights.get(s.timeframe, 0.1) for s in slices)
        weight_sum = sum(weights.get(s.timeframe, 0.1) for s in slices)
        overall = conf_sum / max(weight_sum, 0.01)

        primary_phase = h1.what
        primary_story = f"{h1.what}: {h1.why}"
        if m15 and m15.confidence > h1.confidence:
            primary_phase = m15.what
            primary_story = f"{m15.what} (M15 lead): {m15.why}"

        micro_class = self._detect_micro_class(
            slices=slices,
            structure=structure,
            bias=bias,
            rejection=rejection,
            compression=compression,
            evaluation_moment=evaluation_moment,
        )

        result = MarketNarrativeResult(
            symbol=symbol,
            slices=tuple(slices),
            primary_story=primary_story,
            primary_phase=primary_phase,
            overall_confidence=overall,
            rejection_detected=rejection,
            compression_detected=compression,
            exhaustion_detected=exhaustion,
            micro_narrative_class=micro_class,
        )
        self._latest[symbol] = result
        return result

    def write_report(self, path: Path | None = None) -> Path | None:
        if not self._latest or self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "market_narrative_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Market Narrative Report",
            "",
            f"**Generated:** {now}",
            "",
            "Story-first analysis — indicators confirm only.",
            "",
        ]
        for symbol in sorted(self._latest):
            r = self._latest[symbol]
            lines.extend([
                f"## {symbol}",
                "",
                f"**Primary:** {r.primary_story} ({r.overall_confidence:.0f}%)",
                "",
                "| TF | What | Why | Next | Conf |",
                "|----|------|-----|------|------|",
            ])
            for s in r.slices:
                lines.append(
                    f"| {s.timeframe} | {s.what} | {s.why[:35]} | "
                    f"{s.likely_next[:25]} | {s.confidence:.0f} |"
                )
            lines.append("")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def _analyze_timeframe(
        self,
        *,
        timeframe: str,
        frame: pd.DataFrame,
        symbol: str,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        regime: RegimeResult,
    ) -> TimeframeNarrative:
        closes = frame["close"].astype(float).values
        highs = frame["high"].astype(float).values
        lows = frame["low"].astype(float).values
        volumes = (
            frame["tick_volume"].astype(float).values
            if "tick_volume" in frame.columns
            else np.ones(len(closes))
        )

        pip = pip_size_for_symbol(symbol)
        recent_range = (highs[-5:].max() - lows[-5:].min()) / pip
        prior_range = (highs[-15:-5].max() - lows[-15:-5].min()) / pip if len(closes) >= 15 else recent_range
        range_ratio = recent_range / max(prior_range, 0.1)

        body = abs(closes[-1] - frame["open"].astype(float).values[-1])
        full_range = max(highs[-1] - lows[-1], pip * 0.1)
        wick_upper = highs[-1] - max(closes[-1], frame["open"].astype(float).values[-1])
        wick_lower = min(closes[-1], frame["open"].astype(float).values[-1]) - lows[-1]
        rejection = wick_upper > body * 1.5 or wick_lower > body * 1.5

        vol_recent = volumes[-5:].mean()
        vol_prior = volumes[-15:-5].mean() if len(volumes) >= 15 else vol_recent
        vol_ratio = vol_recent / max(vol_prior, 1.0)

        momentum = (closes[-1] - closes[-5]) / pip if len(closes) >= 5 else 0.0

        phase, why, likely, conf = self._classify_phase(
            range_ratio=range_ratio,
            vol_ratio=vol_ratio,
            momentum=momentum,
            rejection=rejection,
            structure=structure,
            bias=bias,
            regime=regime,
            timeframe=timeframe,
        )
        return TimeframeNarrative(
            timeframe=timeframe,
            what=phase,
            why=why,
            likely_next=likely,
            confidence=conf,
        )

    @staticmethod
    def _classify_phase(
        *,
        range_ratio: float,
        vol_ratio: float,
        momentum: float,
        rejection: bool,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        regime: RegimeResult,
        timeframe: str,
    ) -> tuple[NarrativePhase, str, str, float]:
        conf = 50.0

        if rejection and structure.liquidity_zones:
            return (
                "liquidity_sweep",
                "Wick rejection at liquidity zone — stop hunt complete",
                "Fade sweep or continuation after absorption",
                72.0,
            )

        if range_ratio < 0.65 and vol_ratio < 0.85:
            conf = 65.0 if timeframe in {"M5", "M15", "H1"} else 55.0
            return (
                "compression",
                "Range contracting with declining participation",
                "Breakout harvest on expansion",
                conf,
            )

        if range_ratio > 1.35 and vol_ratio > 1.2:
            conf = 70.0
            direction = "higher" if momentum > 0 else "lower"
            return (
                "expansion",
                f"Volatility expanding — {direction} impulse",
                f"Continuation {direction} or pullback entry",
                conf,
            )

        if vol_ratio > 1.5 and abs(momentum) < 3.0:
            return (
                "exhaustion",
                "High volume without directional follow-through",
                "Mean reversion snapback",
                68.0,
            )

        if vol_ratio < 0.7 and abs(momentum) < 2.0:
            phase: NarrativePhase = "accumulation" if bias.bias == "bullish" else "distribution"
            if bias.bias == "neutral":
                phase = "ranging"
            return (
                phase,
                "Quiet volume — positioning before move",
                "Breakout when volume returns",
                58.0,
            )

        if structure.last_bos is not None and abs(momentum) > 2.0:
            return (
                "continuation",
                f"BOS confirmed — {structure.last_bos.description}",
                "Pullback then trend continuation",
                75.0,
            )

        if regime.regime == "ranging" or structure.trend == "ranging":
            return (
                "ranging",
                "Structure balanced — no dominant trend",
                "Fade extremes or wait compression break",
                52.0,
            )

        if abs(momentum) > 5.0 and range_ratio > 1.1:
            if rejection:
                return (
                    "breakout_failure",
                    "Failed breakout with rejection wick",
                    "Revert to range midpoint",
                    64.0,
                )
            return (
                "breakout",
                "Momentum thrust through recent range",
                "Retest breakout level then continue",
                66.0,
            )

        if abs(momentum) < 1.5 and rejection:
            return (
                "mean_reversion",
                "Price rejected at range extreme",
                "Snap back to mean",
                60.0,
            )

        direction = bias.bias if bias.bias != "neutral" else structure.trend
        if direction in {"bullish", "bearish"}:
            conf = 55.0 + bias.confidence * 25.0
            return (
                "continuation",
                f"Aligned {direction} bias on {timeframe}",
                f"Continue {direction} on pullback",
                min(100.0, conf),
            )

        return (
            "ranging",
            "No clear narrative edge",
            "Monitor for compression or sweep",
            45.0,
        )

    @staticmethod
    def _detect_micro_class(
        *,
        slices: list[TimeframeNarrative],
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        rejection: bool,
        compression: bool,
        evaluation_moment: datetime | None,
    ) -> MicroNarrativeClass | None:
        """Map local price/volume story to micro-harvest narrative class."""
        m1 = next((s for s in slices if s.timeframe == "M1"), None)
        m5 = next((s for s in slices if s.timeframe == "M5"), None)
        h1 = next((s for s in slices if s.timeframe == "H1"), None)

        hour = evaluation_moment.hour if evaluation_moment else 12
        session = infer_session(hour)

        if rejection and (structure.liquidity_zones or (m1 and m1.what == "liquidity_sweep")):
            return "liquidity_sweep_snapback"

        if compression or (m5 and m5.what == "compression"):
            return "compression_pop"

        if m5 and m5.what == "breakout_failure":
            return "failed_breakout_return"

        if m5 and m5.what == "breakout" and structure.last_bos is not None:
            return "breakout_retest_harvest"

        if session in {"london", "london_ny_overlap"} and m5 and m5.what == "expansion":
            return "session_open_push"

        if h1 and h1.what == "continuation" and m5 and abs(m5.confidence - h1.confidence) < 15:
            macro = bias.bias if bias.bias != "neutral" else structure.trend
            local = m5.what
            if macro in {"bullish", "bearish"} and local == "continuation":
                return "micro_pullback_continuation"

        if h1 and h1.what == "ranging" and bias.bias != "neutral":
            return "trend_pause_resume"

        if m1 and m1.what == "continuation" and structure.higher_lows:
            return "micro_pullback_continuation"

        return None
