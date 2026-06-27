"""Reversal pressure engine — detect when trend control is shifting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategies.market_reading_utils import (
    atr_series,
    swing_points,
    trend_direction_from_swings,
    validate_candles,
    volume_participation,
)

ReversalSignal = Literal[
    "momentum_divergence",
    "weakening_trend",
    "lower_highs",
    "higher_lows",
    "volume_exhaustion",
    "distribution",
    "accumulation",
    "none",
]


@dataclass(frozen=True)
class ReversalPressureResult:
    """Reversal pressure assessment for one symbol/timeframe."""

    symbol: str
    timeframe: str
    reversal_pressure_score: int
    dominant_signal: ReversalSignal
    signals: tuple[ReversalSignal, ...]
    trend_direction: Literal["bullish", "bearish", "neutral"]
    explanation: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "reversal_pressure_score": self.reversal_pressure_score,
            "dominant_signal": self.dominant_signal,
            "signals": list(self.signals),
            "trend_direction": self.trend_direction,
            "explanation": self.explanation,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class ReversalPressureConfig:
    min_candles: int = 40
    lookback: int = 80
    atr_period: int = 14
    swing_window: int = 2


class ReversalPressureEngineError(Exception):
    pass


class ReversalPressureEngine:
    """Detect momentum divergence, structure breaks, and volume exhaustion."""

    def __init__(self, config: ReversalPressureConfig | None = None) -> None:
        self.config = config or ReversalPressureConfig()

    def analyze(
        self,
        candles: pd.DataFrame,
        *,
        symbol: str = "",
        timeframe: str = "H1",
    ) -> ReversalPressureResult:
        try:
            frame = validate_candles(
                candles, min_candles=self.config.min_candles, engine="ReversalPressureEngine"
            ).tail(self.config.lookback)
        except ValueError as exc:
            raise ReversalPressureEngineError(str(exc)) from exc

        atr = atr_series(frame, self.config.atr_period)
        atr_value = float(atr.iloc[-1]) or float((frame["high"] - frame["low"]).median()) or 1.0
        highs, lows = swing_points(frame, window=self.config.swing_window)
        direction = trend_direction_from_swings(highs, lows, frame, atr_value)

        scores: dict[ReversalSignal, float] = {}
        evidence: list[str] = []

        div_score, div_ev = self._momentum_divergence(frame, direction, atr_value)
        if div_score > 0.15:
            scores["momentum_divergence"] = div_score
            evidence.extend(div_ev)

        weak_score, weak_ev = self._weakening_trend(frame, direction, atr_value)
        if weak_score > 0.15:
            scores["weakening_trend"] = weak_score
            evidence.extend(weak_ev)

        if direction == "bullish" and len(highs) >= 2 and highs[-1][1] < highs[-2][1]:
            scores["lower_highs"] = 0.55
            evidence.append("lower high forming in bullish trend")
        if direction == "bearish" and len(lows) >= 2 and lows[-1][1] > lows[-2][1]:
            scores["higher_lows"] = 0.55
            evidence.append("higher low forming in bearish trend")

        vol_score, vol_ev = self._volume_exhaustion(frame)
        if vol_score > 0.15:
            scores["volume_exhaustion"] = vol_score
            evidence.extend(vol_ev)

        dist_score, dist_ev = self._distribution_signal(frame, atr_value)
        if dist_score > 0.20:
            scores["distribution"] = dist_score
            evidence.extend(dist_ev)

        acc_score, acc_ev = self._accumulation_signal(frame, atr_value)
        if acc_score > 0.20:
            scores["accumulation"] = acc_score
            evidence.extend(acc_ev)

        if not scores:
            return ReversalPressureResult(
                symbol=symbol,
                timeframe=timeframe,
                reversal_pressure_score=15,
                dominant_signal="none",
                signals=(),
                trend_direction=direction,  # type: ignore[arg-type]
                explanation="Low reversal pressure — trend control stable",
                evidence=tuple(evidence or ("No reversal signals detected",)),
            )

        total = sum(scores.values())
        pressure = int(max(0, min(100, round(total / max(len(scores), 1) * 100))))
        dominant = max(scores, key=scores.get)  # type: ignore[arg-type]
        active_signals = tuple(sorted(scores, key=scores.get, reverse=True))  # type: ignore[arg-type]

        return ReversalPressureResult(
            symbol=symbol,
            timeframe=timeframe,
            reversal_pressure_score=pressure,
            dominant_signal=dominant,
            signals=active_signals,
            trend_direction=direction,  # type: ignore[arg-type]
            explanation=(
                f"Reversal pressure {pressure}/100 — dominant signal: {dominant.replace('_', ' ')}"
            ),
            evidence=tuple(evidence),
        )

    @staticmethod
    def _momentum_divergence(
        frame: pd.DataFrame, direction: str, atr_value: float
    ) -> tuple[float, list[str]]:
        recent = frame.tail(15)
        previous = frame.iloc[-30:-15] if len(frame) >= 30 else frame.head(0)
        if previous.empty:
            return 0.0, []
        recent_high = float(recent["high"].max())
        prev_high = float(previous["high"].max())
        recent_low = float(recent["low"].min())
        prev_low = float(previous["low"].min())
        recent_move = abs(float(recent["close"].iloc[-1]) - float(recent["close"].iloc[0])) / atr_value
        prev_move = abs(float(previous["close"].iloc[-1]) - float(previous["close"].iloc[0])) / atr_value
        score = 0.0
        evidence: list[str] = []
        if direction == "bullish" and recent_high >= prev_high and recent_move < prev_move * 0.7:
            score = 0.50
            evidence.append("bullish momentum divergence — new high, weaker impulse")
        if direction == "bearish" and recent_low <= prev_low and recent_move < prev_move * 0.7:
            score = 0.50
            evidence.append("bearish momentum divergence — new low, weaker impulse")
        return score, evidence

    @staticmethod
    def _weakening_trend(
        frame: pd.DataFrame, direction: str, atr_value: float
    ) -> tuple[float, list[str]]:
        close = frame["close"].astype(float)
        chunks = [close.iloc[-40:-30], close.iloc[-30:-20], close.iloc[-20:-10], close.iloc[-10:]]
        moves = [
            (float(c.iloc[-1]) - float(c.iloc[0])) / atr_value for c in chunks if len(c) > 2
        ]
        if len(moves) < 3:
            return 0.0, []
        if direction == "bullish" and moves[-1] < moves[-2] < moves[-3]:
            return 0.45, ["bullish impulses sequentially weakening"]
        if direction == "bearish" and moves[-1] > moves[-2] > moves[-3]:
            return 0.45, ["bearish impulses sequentially weakening"]
        return 0.0, []

    @staticmethod
    def _volume_exhaustion(frame: pd.DataFrame) -> tuple[float, list[str]]:
        if "tick_volume" not in frame.columns:
            return 0.0, []
        volume = frame["tick_volume"].astype(float)
        if len(volume) < 30:
            return 0.0, []
        recent = float(volume.tail(10).mean())
        peak = float(volume.iloc[-30:-10].max())
        baseline = float(volume.iloc[-30:-10].mean())
        if peak > baseline * 1.3 and recent < peak * 0.65:
            return 0.40, ["volume peaked and is exhausting"]
        if recent < baseline * 0.75:
            return 0.25, ["participation declining on recent bars"]
        return 0.0, []

    @staticmethod
    def _distribution_signal(frame: pd.DataFrame, atr_value: float) -> tuple[float, list[str]]:
        tail = frame.tail(20)
        high = float(tail["high"].max())
        close = tail["close"].astype(float)
        rejections = int(((tail["high"] >= high - atr_value * 0.15) & (close < high - atr_value * 0.25)).sum())
        overlap = ((tail["high"].shift(1) >= tail["low"]) & (tail["low"].shift(1) <= tail["high"])).mean()
        score = 0.0
        evidence: list[str] = []
        if rejections >= 4:
            score += 0.35
            evidence.append(f"{rejections} upper rejections near range high")
        if overlap > 0.75:
            score += 0.20
            evidence.append("overlapping bars suggest distribution")
        return min(0.70, score), evidence

    @staticmethod
    def _accumulation_signal(frame: pd.DataFrame, atr_value: float) -> tuple[float, list[str]]:
        tail = frame.tail(20)
        low = float(tail["low"].min())
        close = tail["close"].astype(float)
        absorptions = int(((tail["low"] <= low + atr_value * 0.15) & (close > low + atr_value * 0.25)).sum())
        score = 0.0
        evidence: list[str] = []
        if absorptions >= 4:
            score = 0.35
            evidence.append(f"{absorptions} support absorptions near range low")
        return score, evidence


__all__ = [
    "ReversalPressureConfig",
    "ReversalPressureEngine",
    "ReversalPressureEngineError",
    "ReversalPressureResult",
    "ReversalSignal",
]
