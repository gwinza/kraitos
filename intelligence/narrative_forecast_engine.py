"""Narrative Forecast Engine — predict next move from story, not indicators."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd

from core.helpers import pip_size_for_symbol
from intelligence.market_narrative_engine import (
    MarketNarrativeResult,
    MicroNarrativeClass,
    NarrativePhase,
)
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult

ForecastStrategy = Literal[
    "pullback_harvest",
    "liquidity_sweep_fade",
    "compression_breakout",
    "trend_continuation",
    "mean_reversion_snapback",
    "session_momentum",
    "range_scalp",
    "micro_harvest",
    "wait",
]

MICRO_CLASS_STRATEGY: dict[MicroNarrativeClass, tuple[ForecastStrategy, float, float]] = {
    "micro_pullback_continuation": ("micro_harvest", 2.0, 4.0),
    "liquidity_sweep_snapback": ("liquidity_sweep_fade", 1.5, 3.0),
    "breakout_retest_harvest": ("pullback_harvest", 2.0, 4.0),
    "compression_pop": ("compression_breakout", 2.5, 5.0),
    "session_open_push": ("session_momentum", 2.5, 4.5),
    "failed_breakout_return": ("mean_reversion_snapback", 1.5, 3.5),
    "trend_pause_resume": ("trend_continuation", 2.5, 5.0),
}

TrailTimeframe = Literal["M1", "M5", "H1", "none"]


@dataclass(frozen=True)
class NarrativeExitProfile:
    """Per-narrative exit behaviour for targets, partials, and runners."""

    micro_class: MicroNarrativeClass | None
    hold_factor: float
    exit_speed: float
    target_multiplier: float
    allow_runner: bool
    partial_fraction: float
    trail_timeframe: TrailTimeframe
    move_stop_to_breakeven: bool

    def to_dict(self) -> dict:
        return {
            "micro_class": self.micro_class,
            "hold_factor": round(self.hold_factor, 2),
            "exit_speed": round(self.exit_speed, 2),
            "target_multiplier": round(self.target_multiplier, 2),
            "allow_runner": self.allow_runner,
            "partial_fraction": round(self.partial_fraction, 2),
            "trail_timeframe": self.trail_timeframe,
            "move_stop_to_breakeven": self.move_stop_to_breakeven,
        }


MICRO_CLASS_EXIT_PROFILE: dict[MicroNarrativeClass, NarrativeExitProfile] = {
    "micro_pullback_continuation": NarrativeExitProfile(
        micro_class="micro_pullback_continuation",
        hold_factor=1.0,
        exit_speed=1.0,
        target_multiplier=1.05,
        allow_runner=True,
        partial_fraction=0.5,
        trail_timeframe="M5",
        move_stop_to_breakeven=True,
    ),
    "liquidity_sweep_snapback": NarrativeExitProfile(
        micro_class="liquidity_sweep_snapback",
        hold_factor=0.9,
        exit_speed=1.15,
        target_multiplier=1.12,
        allow_runner=False,
        partial_fraction=0.65,
        trail_timeframe="none",
        move_stop_to_breakeven=False,
    ),
    "breakout_retest_harvest": NarrativeExitProfile(
        micro_class="breakout_retest_harvest",
        hold_factor=1.05,
        exit_speed=0.95,
        target_multiplier=1.1,
        allow_runner=True,
        partial_fraction=0.5,
        trail_timeframe="M5",
        move_stop_to_breakeven=True,
    ),
    "compression_pop": NarrativeExitProfile(
        micro_class="compression_pop",
        hold_factor=1.1,
        exit_speed=0.85,
        target_multiplier=1.25,
        allow_runner=True,
        partial_fraction=0.4,
        trail_timeframe="M5",
        move_stop_to_breakeven=True,
    ),
    "session_open_push": NarrativeExitProfile(
        micro_class="session_open_push",
        hold_factor=1.05,
        exit_speed=1.0,
        target_multiplier=1.1,
        allow_runner=True,
        partial_fraction=0.45,
        trail_timeframe="M1",
        move_stop_to_breakeven=True,
    ),
    "failed_breakout_return": NarrativeExitProfile(
        micro_class="failed_breakout_return",
        hold_factor=0.9,
        exit_speed=1.15,
        target_multiplier=0.95,
        allow_runner=False,
        partial_fraction=0.55,
        trail_timeframe="none",
        move_stop_to_breakeven=False,
    ),
    "trend_pause_resume": NarrativeExitProfile(
        micro_class="trend_pause_resume",
        hold_factor=1.2,
        exit_speed=0.8,
        target_multiplier=1.15,
        allow_runner=True,
        partial_fraction=0.45,
        trail_timeframe="M5",
        move_stop_to_breakeven=True,
    ),
}

DEFAULT_EXIT_PROFILE = NarrativeExitProfile(
    micro_class=None,
    hold_factor=1.0,
    exit_speed=1.0,
    target_multiplier=1.0,
    allow_runner=False,
    partial_fraction=0.5,
    trail_timeframe="none",
    move_stop_to_breakeven=False,
)


@dataclass(frozen=True)
class NarrativeForecastResult:
    """Per-asset narrative-driven forecast."""

    symbol: str
    current_story: str
    expected_next_move: str
    expected_pip_range: float
    confidence: float
    invalidation: str
    recommended_strategy: ForecastStrategy
    direction: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "current_story": self.current_story,
            "expected_next_move": self.expected_next_move,
            "expected_pip_range": round(self.expected_pip_range, 2),
            "confidence": round(self.confidence, 2),
            "invalidation": self.invalidation,
            "recommended_strategy": self.recommended_strategy,
            "direction": self.direction,
        }


class NarrativeForecastEngine:
    """Forecast next move from narrative — indicators refine range only."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self._latest: dict[str, NarrativeForecastResult] = {}
        self._exit_profiles: dict[str, NarrativeExitProfile] = {}

    @staticmethod
    def exit_profile_for(
        micro_class: MicroNarrativeClass | None,
        *,
        phase: NarrativePhase | None = None,
    ) -> NarrativeExitProfile:
        """Map narrative class/phase to exit behaviour."""
        if micro_class and micro_class in MICRO_CLASS_EXIT_PROFILE:
            return MICRO_CLASS_EXIT_PROFILE[micro_class]
        if phase == "continuation":
            return NarrativeExitProfile(
                micro_class=None,
                hold_factor=1.15,
                exit_speed=0.85,
                target_multiplier=1.1,
                allow_runner=True,
                partial_fraction=0.45,
                trail_timeframe="M5",
                move_stop_to_breakeven=True,
            )
        if phase in {"liquidity_sweep", "breakout_failure", "mean_reversion"}:
            return NarrativeExitProfile(
                micro_class=None,
                hold_factor=0.8,
                exit_speed=1.25,
                target_multiplier=0.9,
                allow_runner=False,
                partial_fraction=0.6,
                trail_timeframe="none",
                move_stop_to_breakeven=False,
            )
        if phase == "compression":
            return NarrativeExitProfile(
                micro_class=None,
                hold_factor=1.1,
                exit_speed=0.9,
                target_multiplier=1.2,
                allow_runner=True,
                partial_fraction=0.4,
                trail_timeframe="M5",
                move_stop_to_breakeven=True,
            )
        return DEFAULT_EXIT_PROFILE

    def forecast(
        self,
        *,
        symbol: str,
        narrative: MarketNarrativeResult,
        candles: dict[str, pd.DataFrame],
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        regime: RegimeResult,
        indicator_atr_ratio: float | None = None,
        indicator_confirmation_boost: float = 0.0,
    ) -> NarrativeForecastResult:
        phase = narrative.primary_phase
        direction = self._resolve_direction(bias, structure, narrative)
        micro_class = narrative.micro_narrative_class
        if micro_class and micro_class in MICRO_CLASS_STRATEGY:
            strategy, pip_low, pip_high = MICRO_CLASS_STRATEGY[micro_class]
            pip_range = (pip_low + pip_high) / 2
            next_move = f"Micro harvest {micro_class.replace('_', ' ')} ({direction})"
            invalidation = "Close through invalidation swing"
        else:
            pip_range = self._estimate_pip_range(
                symbol=symbol,
                candles=candles,
                phase=phase,
                atr_ratio=indicator_atr_ratio,
            )
            strategy, next_move, invalidation = self._strategy_for_phase(
                phase=phase,
                direction=direction,
                narrative=narrative,
                structure=structure,
            )
        conf = narrative.overall_confidence + indicator_confirmation_boost
        if micro_class:
            conf = min(100.0, conf + 6.0)
        conf = max(0.0, min(100.0, conf))

        exit_profile = self.exit_profile_for(micro_class, phase=phase)
        pip_range *= exit_profile.target_multiplier
        if exit_profile.exit_speed > 1.0:
            pip_range /= exit_profile.exit_speed
        elif exit_profile.hold_factor > 1.0:
            pip_range *= min(1.25, exit_profile.hold_factor)

        result = NarrativeForecastResult(
            symbol=symbol,
            current_story=narrative.primary_story,
            expected_next_move=next_move,
            expected_pip_range=pip_range,
            confidence=conf,
            invalidation=invalidation,
            recommended_strategy=strategy,
            direction=direction,
        )
        self._latest[symbol] = result
        self._exit_profiles[symbol] = exit_profile
        return result

    def exit_profile(self, symbol: str) -> NarrativeExitProfile | None:
        return self._exit_profiles.get(symbol)

    def write_report(self, path: Path | None = None) -> Path | None:
        if not self._latest or self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "narrative_forecast_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Narrative Forecast Report",
            "",
            f"**Generated:** {now}",
            "",
            "| Symbol | Story | Next move | Pip range | Conf | Strategy |",
            "|--------|-------|-----------|-----------|------|----------|",
        ]
        for symbol in sorted(self._latest):
            f = self._latest[symbol]
            lines.append(
                f"| {symbol} | {f.current_story[:30]} | {f.expected_next_move[:25]} | "
                f"{f.expected_pip_range:.1f} | {f.confidence:.0f} | {f.recommended_strategy} |"
            )
        lines.extend(["", "## Invalidation levels", ""])
        for symbol in sorted(self._latest):
            f = self._latest[symbol]
            lines.append(f"- **{symbol}:** {f.invalidation}")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    @staticmethod
    def _resolve_direction(
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
        narrative: MarketNarrativeResult,
    ) -> str:
        macro_bias = "neutral"
        for layer in bias.layers:
            if layer.role == "macro" and layer.bias != "neutral":
                macro_bias = layer.bias
                break
        m15 = narrative.slice_for("M15")
        m5 = narrative.slice_for("M5")
        local_dir = "neutral"
        if m5 and m5.what in {"continuation", "breakout", "expansion"}:
            if "higher" in m5.likely_next.lower():
                local_dir = "bullish"
            elif "lower" in m5.likely_next.lower():
                local_dir = "bearish"
        if macro_bias != "neutral" and local_dir == macro_bias:
            return macro_bias
        if macro_bias != "neutral" and narrative.micro_narrative_class:
            return macro_bias
        if bias.bias != "neutral":
            return bias.bias
        if structure.trend != "ranging":
            return structure.trend
        h1 = narrative.slice_for("H1")
        if h1 and "higher" in h1.likely_next.lower():
            return "bullish"
        if h1 and "lower" in h1.likely_next.lower():
            return "bearish"
        if m15 and local_dir != "neutral":
            return local_dir
        return "neutral"

    @staticmethod
    def _estimate_pip_range(
        *,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        phase: NarrativePhase,
        atr_ratio: float | None,
    ) -> float:
        h1 = candles.get("H1")
        base = 8.0
        if h1 is not None and len(h1) >= 14:
            highs = h1["high"].astype(float)
            lows = h1["low"].astype(float)
            tr = (highs - lows).tail(14)
            pip = pip_size_for_symbol(symbol)
            atr_pips = tr.mean() / pip
            base = max(4.0, min(25.0, float(atr_pips) * 1.2))
        if atr_ratio is not None:
            base *= max(0.7, min(1.5, atr_ratio))
        multipliers = {
            "compression": 0.55,
            "expansion": 1.2,
            "exhaustion": 0.9,
            "breakout": 1.0,
            "liquidity_sweep": 0.75,
            "mean_reversion": 0.7,
            "continuation": 0.8,
        }
        pip_range = base * multipliers.get(phase, 0.85)
        return max(1.5, min(pip_range, 25.0))

    @staticmethod
    def _strategy_for_phase(
        *,
        phase: NarrativePhase,
        direction: str,
        narrative: MarketNarrativeResult,
        structure: MarketContext,
    ) -> tuple[ForecastStrategy, str, str]:
        inv_bull = "Close below recent swing low"
        inv_bear = "Close above recent swing high"
        inv_neutral = "Break of compression range"

        mapping: dict[NarrativePhase, tuple[ForecastStrategy, str, str]] = {
            "accumulation": (
                "compression_breakout",
                f"Quiet bid — breakout {direction}",
                inv_neutral,
            ),
            "distribution": (
                "mean_reversion_snapback",
                f"Selling pressure — fade to mean",
                inv_bear if direction == "bearish" else inv_bull,
            ),
            "continuation": (
                "trend_continuation",
                f"Pullback in {direction} trend then resume",
                inv_bear if direction == "bullish" else inv_bull,
            ),
            "exhaustion": (
                "mean_reversion_snapback",
                "Climax volume — snapback trade",
                inv_neutral,
            ),
            "compression": (
                "compression_breakout",
                "Squeeze release — directional break",
                inv_neutral,
            ),
            "expansion": (
                "session_momentum",
                f"Ride expansion {direction}",
                inv_bear if direction == "bullish" else inv_bull,
            ),
            "ranging": (
                "range_scalp",
                "Fade range extremes",
                inv_neutral,
            ),
            "breakout": (
                "trend_continuation",
                "Retest breakout then continue",
                inv_neutral,
            ),
            "breakout_failure": (
                "mean_reversion_snapback",
                "Failed break — revert to range",
                inv_neutral,
            ),
            "liquidity_sweep": (
                "liquidity_sweep_fade",
                "Sweep complete — rejection entry",
                inv_neutral,
            ),
            "mean_reversion": (
                "mean_reversion_snapback",
                "Revert to range midpoint",
                inv_neutral,
            ),
        }
        strategy, move, inv = mapping.get(phase, ("wait", "No clear edge", inv_neutral))
        if narrative.exhaustion_detected and strategy == "wait":
            strategy = "mean_reversion_snapback"
            move = "Exhaustion snapback"
        if structure.last_bos is not None and phase in {"continuation", "breakout"}:
            strategy = "pullback_harvest"
            move = f"Harvest pullback after BOS ({structure.last_bos.kind})"
        return strategy, move, inv
