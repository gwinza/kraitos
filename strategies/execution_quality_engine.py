"""Execution quality engine — entry timing and exit management by market regime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from execution.atr_timing_engine import should_enter
from strategies.fast_failure_engine import FastFailureEngine, FastFailureResult
from strategies.false_breakout_engine import FalseBreakoutEngine
from strategies.liquidity_sweep_engine import LiquiditySweepEngine
from strategies.market_reading_utils import validate_candles
from strategies.models import MarketContext, MicroScalpSignal
from strategies.opportunity_repair_engine import OpportunityRepairEngine, OpportunityRepairResult
from strategies.tradability_engine_v2 import TradabilityEngineV2, TradabilityResultV2

MarketMode = Literal["trending", "ranging", "chaos"]
EntryStyle = Literal[
    "continuation",
    "pullback",
    "breakout",
    "reversal",
    "support_reversal",
    "resistance_reversal",
    "mean_reversion",
    "liquidity_sweep",
    "failed_breakout",
    "volatility_imbalance",
    "wait",
]
ExitStyle = Literal[
    "hold",
    "protect_winner",
    "tighten_trail",
    "scale_out",
    "repair",
    "fast_failure_exit",
    "thesis_invalidation",
]


@dataclass(frozen=True)
class EntryQualityResult:
    """Entry timing and style recommendation."""

    entry_style: EntryStyle
    entry_allowed: bool
    timing_score: int
    size_multiplier: float
    explanation: str
    evidence: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExitQualityResult:
    """Exit management recommendation."""

    exit_style: ExitStyle
    exit_allowed: bool
    protect_winner: bool
    premature_exit_risk: float
    explanation: str
    evidence: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExecutionQualityResult:
    """Complete execution quality assessment."""

    symbol: str
    side: str
    market_mode: MarketMode
    tradability: TradabilityResultV2 | None
    entry: EntryQualityResult
    exit: ExitQualityResult | None
    fast_failure: FastFailureResult | None
    repair: OpportunityRepairResult | None
    execution_score: int
    explanation: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "market_mode": self.market_mode,
            "tradability_score": self.tradability.tradability_score if self.tradability else None,
            "entry_style": self.entry.entry_style,
            "entry_allowed": self.entry.entry_allowed,
            "timing_score": self.entry.timing_score,
            "execution_score": self.execution_score,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class ExecutionQualityConfig:
    min_execution_probe: int = 40
    premature_exit_r_threshold: float = 0.50


class ExecutionQualityEngine:
    """Improve entry timing and exit management — better execution, not fewer trades."""

    def __init__(
        self,
        config: ExecutionQualityConfig | None = None,
        *,
        tradability: TradabilityEngineV2 | None = None,
        fast_failure: FastFailureEngine | None = None,
        repair: OpportunityRepairEngine | None = None,
    ) -> None:
        self.config = config or ExecutionQualityConfig()
        self._tradability = tradability or TradabilityEngineV2()
        self._fast_failure = fast_failure or FastFailureEngine()
        self._repair = repair or OpportunityRepairEngine()
        self._sweep = LiquiditySweepEngine()
        self._false_breakout = FalseBreakoutEngine()

    def evaluate_entry(
        self,
        *,
        symbol: str,
        side: str,
        spread_pips: float,
        spread_limit: float,
        stop_pips: float,
        target_pips: float,
        candles: pd.DataFrame | None = None,
        structure: MarketContext | None = None,
        momentum: MicroScalpSignal | None = None,
        primary_regime: str | None = None,
        range_location: str | None = None,
    ) -> ExecutionQualityResult:
        mode = self._market_mode(primary_regime, structure)
        trad = self._tradability.evaluate(
            symbol=symbol,
            spread_pips=spread_pips,
            spread_limit=spread_limit,
            stop_pips=stop_pips,
            target_pips=target_pips,
            candles=candles,
        )

        entry_style, timing_score, evidence = self._entry_logic(
            mode=mode,
            side=side,
            candles=candles,
            structure=structure,
            momentum=momentum,
            range_location=range_location,
        )

        timing_ok = self._timing_confirms(side, candles, entry_style)
        entry_allowed = trad.executable and (timing_ok or entry_style in {"liquidity_sweep", "failed_breakout"})
        size_mult = self._entry_size(trad.tradability_score, timing_score, entry_allowed)

        entry = EntryQualityResult(
            entry_style=entry_style,
            entry_allowed=entry_allowed,
            timing_score=timing_score,
            size_multiplier=size_mult,
            explanation=f"{mode} market — {entry_style} entry (timing {timing_score}/100)",
            evidence=tuple(evidence),
        )

        exec_score = int(
            (trad.tradability_score if trad else 50) * 0.45
            + timing_score * 0.35
            + (20 if entry_allowed else 5)
        )

        return ExecutionQualityResult(
            symbol=symbol,
            side=side,
            market_mode=mode,
            tradability=trad,
            entry=entry,
            exit=None,
            fast_failure=None,
            repair=None,
            execution_score=min(100, exec_score),
            explanation=f"Execution quality {exec_score}/100 — {entry.explanation}",
        )

    def evaluate_exit(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        current_price: float,
        candles: pd.DataFrame | None = None,
        structure: MarketContext | None = None,
        momentum: MicroScalpSignal | None = None,
        invalidation_level: float | None = None,
        trend_quality_score: int | None = None,
        reversal_pressure_score: int | None = None,
        partial_taken: bool = False,
    ) -> ExecutionQualityResult:
        risk = abs(entry_price - stop_loss) or 1e-9
        current_r = (
            (current_price - entry_price) / risk
            if side == "buy"
            else (entry_price - current_price) / risk
        )

        ff = self._fast_failure.evaluate(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            current_price=current_price,
            candles=candles,
            structure=structure,
            momentum=momentum,
            invalidation_level=invalidation_level,
        )
        repair = self._repair.evaluate(
            symbol=symbol,
            side=side,
            current_r=current_r,
            trend_quality_score=trend_quality_score,
            reversal_pressure_score=reversal_pressure_score,
            partial_taken=partial_taken,
        )

        exit_style, protect, premature_risk, evidence = self._exit_logic(
            current_r=current_r,
            fast_failure=ff,
            repair=repair,
            trend_quality_score=trend_quality_score,
            reversal_pressure_score=reversal_pressure_score,
        )

        exit_result = ExitQualityResult(
            exit_style=exit_style,
            exit_allowed=exit_style in {"fast_failure_exit", "thesis_invalidation", "scale_out"},
            protect_winner=protect,
            premature_exit_risk=premature_risk,
            explanation=f"Exit: {exit_style.replace('_', ' ')} at {current_r:.2f}R",
            evidence=tuple(evidence),
        )

        exec_score = int(70 if protect else 50)
        if ff.recommended_action == "exit_early" and current_r < 0:
            exec_score = 85

        return ExecutionQualityResult(
            symbol=symbol,
            side=side,
            market_mode="trending",
            tradability=None,
            entry=EntryQualityResult(
                entry_style="wait",
                entry_allowed=False,
                timing_score=0,
                size_multiplier=0.0,
                explanation="exit evaluation",
            ),
            exit=exit_result,
            fast_failure=ff,
            repair=repair,
            execution_score=exec_score,
            explanation=exit_result.explanation,
        )

    def _market_mode(
        self, primary_regime: str | None, structure: MarketContext | None
    ) -> MarketMode:
        if primary_regime == "chaos":
            return "chaos"
        if primary_regime in {"ranging", "mean_reversion", "compression"}:
            return "ranging"
        if primary_regime in {"trending", "breakout"}:
            return "trending"
        if structure is not None:
            if structure.trend == "ranging":
                return "ranging"
            if structure.trend in {"bullish", "bearish"}:
                return "trending"
        return "ranging"

    def _entry_logic(
        self,
        *,
        mode: MarketMode,
        side: str,
        candles: pd.DataFrame | None,
        structure: MarketContext | None,
        momentum: MicroScalpSignal | None,
        range_location: str | None,
    ) -> tuple[EntryStyle, int, list[str]]:
        evidence: list[str] = []

        if mode == "trending":
            style, score = self._trending_entry(side, candles, structure, momentum, evidence)
        elif mode == "ranging":
            style, score = self._ranging_entry(side, range_location, candles, evidence)
        else:
            style, score = self._chaos_entry(side, candles, evidence)

        return style, score, evidence

    def _trending_entry(
        self,
        side: str,
        candles: pd.DataFrame | None,
        structure: MarketContext | None,
        momentum: MicroScalpSignal | None,
        evidence: list[str],
    ) -> tuple[EntryStyle, int]:
        if candles is not None:
            timing = should_enter(side=side, candles=candles)
            if timing.trigger == "retracement":
                evidence.append("pullback retracement trigger")
                return "pullback", 78
            if timing.trigger == "consolidation":
                evidence.append("consolidation before continuation")
                return "continuation", 72
        if structure is not None and structure.last_bos is not None:
            evidence.append("BOS present — breakout/continuation")
            return "breakout", 70
        if momentum is not None and momentum.action == side:
            evidence.append("momentum aligned — continuation")
            return "continuation", 68
        evidence.append("trending — default pullback scout")
        return "pullback", 55

    def _ranging_entry(
        self,
        side: str,
        range_location: str | None,
        candles: pd.DataFrame | None,
        evidence: list[str],
    ) -> tuple[EntryStyle, int]:
        loc = range_location or ""
        if side == "buy" and "support" in loc:
            evidence.append("support reversal in range")
            return "support_reversal", 75
        if side == "sell" and "resistance" in loc:
            evidence.append("resistance reversal in range")
            return "resistance_reversal", 75
        if "equilibrium" in loc:
            evidence.append("mean reversion from equilibrium")
            return "mean_reversion", 62
        if side == "buy":
            return "support_reversal", 58
        return "resistance_reversal", 58

    def _chaos_entry(
        self,
        side: str,
        candles: pd.DataFrame | None,
        evidence: list[str],
    ) -> tuple[EntryStyle, int]:
        if candles is not None and not candles.empty:
            try:
                frame = validate_candles(candles, min_candles=40, engine="ExecutionQualityEngine")
                sweep = self._sweep.analyze(frame)
                if sweep.liquidity_sweep_probability >= 0.55:
                    evidence.append(f"liquidity sweep {sweep.liquidity_sweep_probability:.0%}")
                    return "liquidity_sweep", 72
                fb = self._false_breakout.analyze(frame)
                if fb.breakout_class == "failed":
                    evidence.append("failed breakout — trapped traders")
                    return "failed_breakout", 70
            except ValueError:
                pass
        evidence.append("chaos — volatility imbalance scout")
        return "volatility_imbalance", 55

    @staticmethod
    def _timing_confirms(side: str, candles: pd.DataFrame | None, style: EntryStyle) -> bool:
        if candles is None or style in {"liquidity_sweep", "failed_breakout", "volatility_imbalance"}:
            return True
        timing = should_enter(side=side, candles=candles)
        return timing.allowed

    @staticmethod
    def _entry_size(tradability: int, timing: int, allowed: bool) -> float:
        if not allowed:
            return 0.35
        base = min(1.0, (tradability / 100.0) * 0.6 + (timing / 100.0) * 0.4)
        return max(0.35, round(base, 3))

    def _exit_logic(
        self,
        *,
        current_r: float,
        fast_failure: FastFailureResult,
        repair: OpportunityRepairResult,
        trend_quality_score: int | None,
        reversal_pressure_score: int | None,
    ) -> tuple[ExitStyle, bool, float, list[str]]:
        evidence: list[str] = []
        premature_risk = 0.0

        if fast_failure.thesis_failure and current_r < 0:
            evidence.append("thesis invalidation — fast failure exit")
            return "thesis_invalidation", False, 0.0, evidence

        if fast_failure.recommended_action == "exit_early" and current_r <= -0.35:
            evidence.append("fast failure — exit loser early")
            return "fast_failure_exit", False, 0.0, evidence

        if current_r >= self.config.premature_exit_r_threshold:
            if reversal_pressure_score is not None and reversal_pressure_score >= 65:
                premature_risk = 0.35
                evidence.append("reversal pressure rising — avoid premature exit")
            else:
                evidence.append(f"protect winner at {current_r:.2f}R")
            return "protect_winner", True, premature_risk, evidence

        if repair.repair_action != "monitor":
            evidence.append(f"repair: {repair.repair_action}")
            return "repair", True, 0.15, evidence

        if trend_quality_score is not None and trend_quality_score < 45 and current_r > 0.25:
            evidence.append("trend deteriorating — tighten trail")
            return "tighten_trail", True, 0.25, evidence

        if current_r >= 1.0 and not repair.instant_close:
            evidence.append("scale out partial — protect profit")
            return "scale_out", True, 0.10, evidence

        evidence.append("hold — thesis intact")
        return "hold", True, 0.05, evidence


__all__ = [
    "EntryQualityResult",
    "EntryStyle",
    "ExecutionQualityConfig",
    "ExecutionQualityEngine",
    "ExecutionQualityResult",
    "ExitQualityResult",
    "ExitStyle",
    "MarketMode",
]
