"""Timing quality — reaction, reclaim, rejection; not zone touch alone."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from strategies.market_reading_utils import atr_series, validate_candles

Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class TimingQualityResult:
    timing_quality_score: int
    reaction_detected: bool
    reclaim_detected: bool
    rejection_detected: bool
    momentum_restart_detected: bool
    entry_too_early: bool
    entry_too_late: bool
    explanation: str
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "timing_quality_score": self.timing_quality_score,
            "reaction_detected": self.reaction_detected,
            "reclaim_detected": self.reclaim_detected,
            "rejection_detected": self.rejection_detected,
            "momentum_restart_detected": self.momentum_restart_detected,
            "entry_too_early": self.entry_too_early,
            "entry_too_late": self.entry_too_late,
            "explanation": self.explanation,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class TimingQualityConfig:
    min_candles: int = 12
    reaction_wick_atr: float = 0.35
    late_displacement_atr: float = 2.2


class TimingQualityEngine:
    """Wait for market behaviour — zone touch is not entry."""

    def __init__(self, config: TimingQualityConfig | None = None) -> None:
        self.config = config or TimingQualityConfig()

    def evaluate(
        self,
        *,
        side: str,
        candles: pd.DataFrame | None = None,
        key_level: float | None = None,
    ) -> TimingQualityResult:
        evidence: list[str] = []
        reaction = reclaim = rejection = momentum_restart = False
        too_early = too_late = False
        score = 45

        if candles is None or candles.empty:
            return TimingQualityResult(
                timing_quality_score=40,
                reaction_detected=False,
                reclaim_detected=False,
                rejection_detected=False,
                momentum_restart_detected=False,
                entry_too_early=True,
                entry_too_late=False,
                explanation="No entry-timeframe candles — timing unconfirmed",
                evidence=("insufficient timing data",),
            )

        try:
            frame = validate_candles(
                candles, min_candles=self.config.min_candles, engine="TimingQualityEngine"
            ).tail(20)
        except ValueError as exc:
            return TimingQualityResult(
                timing_quality_score=38,
                reaction_detected=False,
                reclaim_detected=False,
                rejection_detected=False,
                momentum_restart_detected=False,
                entry_too_early=True,
                entry_too_late=False,
                explanation=str(exc),
                evidence=("timing data invalid",),
            )

        atr = float(atr_series(frame).iloc[-1]) or 1e-9
        last = frame.iloc[-1]
        prev = frame.iloc[-2]
        o, h, l, c = (
            float(last["open"]),
            float(last["high"]),
            float(last["low"]),
            float(last["close"]),
        )
        body = abs(c - o)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l

        if side == "buy":
            if lower_wick >= atr * self.config.reaction_wick_atr and c > o:
                rejection = True
                reaction = True
                evidence.append("bullish rejection wick with close up")
            if key_level and prev["close"] < key_level <= c:
                reclaim = True
                reaction = True
                evidence.append("reclaim above key level")
            impulse = c - float(frame["close"].iloc[-4])
            if impulse > atr * 0.4 and c > o:
                momentum_restart = True
                evidence.append("bullish momentum restart")
        else:
            if upper_wick >= atr * self.config.reaction_wick_atr and c < o:
                rejection = True
                reaction = True
                evidence.append("bearish rejection wick with close down")
            if key_level and prev["close"] > key_level >= c:
                reclaim = True
                reaction = True
                evidence.append("reclaim below key level")
            impulse = float(frame["close"].iloc[-4]) - c
            if impulse > atr * 0.4 and c < o:
                momentum_restart = True
                evidence.append("bearish momentum restart")

        recent_range = float(frame["high"].tail(5).max()) - float(frame["low"].tail(5).min())
        if recent_range > atr * self.config.late_displacement_atr and not reaction:
            too_late = True
            evidence.append("move already extended — late entry risk")
        if not reaction and not reclaim and not momentum_restart:
            too_early = True
            evidence.append("no reaction yet — zone touch without behaviour")

        if reaction:
            score += 22
        if reclaim:
            score += 18
        if rejection:
            score += 12
        if momentum_restart:
            score += 15
        if too_early:
            score -= 20
        if too_late:
            score -= 18

        score = max(0, min(100, score))
        explanation = (
            f"Timing {score}/100 — "
            f"{'reaction' if reaction else 'no reaction'}, "
            f"{'reclaim' if reclaim else 'no reclaim'}"
        )
        if too_early:
            explanation += " | too early"
        if too_late:
            explanation += " | too late — do not chase"

        return TimingQualityResult(
            timing_quality_score=score,
            reaction_detected=reaction,
            reclaim_detected=reclaim,
            rejection_detected=rejection,
            momentum_restart_detected=momentum_restart,
            entry_too_early=too_early,
            entry_too_late=too_late,
            explanation=explanation,
            evidence=tuple(evidence),
        )
