"""Trend quality and reversal supervisor for Kraitos.

This module sits above entry timing. It answers whether the active trend is
healthy enough to express, deteriorating, or already reversing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategies.market_reading_utils import (
    atr_series,
    swing_points,
    trend_direction_from_swings,
    volume_participation,
)

TrendDirection = Literal["bullish", "bearish", "neutral"]
TrendPhase = Literal[
    "expansion",
    "healthy_pullback",
    "exhaustion",
    "distribution",
    "reversal_warning",
    "confirmed_reversal",
]
TrendRegime = Literal[
    "trending",
    "ranging",
    "distribution",
    "accumulation",
    "reversal",
]


@dataclass(frozen=True)
class TrendQualityMetrics:
    """Granular trend quality components (0–100 unless noted)."""

    hh_hl_quality: int
    ll_lh_quality: int
    trend_acceleration: float
    trend_exhaustion: float
    trend_health: float
    trend_participation: float

    def to_dict(self) -> dict:
        return {
            "hh_hl_quality": self.hh_hl_quality,
            "ll_lh_quality": self.ll_lh_quality,
            "trend_acceleration": round(self.trend_acceleration, 3),
            "trend_exhaustion": round(self.trend_exhaustion, 3),
            "trend_health": round(self.trend_health, 3),
            "trend_participation": round(self.trend_participation, 3),
        }


@dataclass(frozen=True)
class TradeStory:
    """Narrative record of how the market thesis changed."""

    previous_thesis: str
    current_thesis: str
    what_changed: str
    trend_state: Literal["improving", "stable", "deteriorating", "reversing"]
    action: Literal["continue", "reduce_size", "pause", "reverse_bias"]
    explanation: str


@dataclass(frozen=True)
class TrendQualityResult:
    """Trend quality assessment for one symbol/timeframe."""

    symbol: str
    timeframe: str
    trend_direction: TrendDirection
    trend_quality_score: int
    trend_phase: TrendPhase
    continuation_probability: float
    reversal_probability: float
    regime: TrendRegime
    explanation: str
    trade_story: TradeStory
    metrics: TrendQualityMetrics

    @property
    def deteriorating(self) -> bool:
        return self.trend_phase in {
            "exhaustion",
            "distribution",
            "reversal_warning",
            "confirmed_reversal",
        }


@dataclass(frozen=True)
class TrendQualityConfig:
    """Parameters for volatility-normalized trend quality analysis."""

    min_candles: int = 40
    swing_window: int = 2
    atr_period: int = 14
    lookback: int = 80


class TrendQualityEngineError(Exception):
    """Raised when trend quality inputs are invalid."""


class TrendQualityEngine:
    """Measure trend health, deterioration, and reversal pressure."""

    def __init__(self, config: TrendQualityConfig | None = None) -> None:
        self.config = config or TrendQualityConfig()

    def analyze_all(
        self,
        candles: dict[str, pd.DataFrame],
        *,
        symbol: str,
    ) -> dict[str, TrendQualityResult]:
        """Analyze every provided timeframe for a symbol."""
        return {
            timeframe: self.analyze(frame, symbol=symbol, timeframe=timeframe)
            for timeframe, frame in candles.items()
            if frame is not None and not frame.empty
        }

    def analyze(
        self,
        candles: pd.DataFrame,
        *,
        symbol: str,
        timeframe: str,
        previous_thesis: str = "",
    ) -> TrendQualityResult:
        """Return trend quality and reversal risk for one symbol/timeframe."""
        self._validate(candles)
        frame = candles.tail(self.config.lookback).copy()
        atr = self._atr(frame)
        atr_value = float(atr.iloc[-1]) if not atr.empty else 0.0
        if atr_value <= 0:
            atr_value = float((frame["high"] - frame["low"]).median()) or 1.0

        swing_highs, swing_lows = self._swings(frame)
        direction = self._direction(frame, swing_highs, swing_lows, atr_value)
        prior_direction = self._prior_direction(frame, atr_value)
        metrics = self._compute_metrics(
            frame, swing_highs, swing_lows, direction, atr_value
        )
        structure = self._structure_state(frame, swing_highs, swing_lows, direction, atr_value)
        momentum = self._momentum_state(frame, direction, atr_value)
        pullback = self._pullback_state(frame, direction, atr_value)
        failed = self._failed_continuation(frame, direction, atr_value)
        divergence = self._divergence_state(frame, direction, atr_value)

        reversal_pressure = (
            structure["reversal"]
            + momentum["deterioration"]
            + pullback["danger"]
            + failed["pressure"]
            + divergence["pressure"]
        )
        continuation_strength = (
            structure["continuation"]
            + momentum["continuation"]
            + pullback["health"]
            - failed["pressure"] * 0.5
            - divergence["pressure"] * 0.4
        )

        phase = self._phase(
            direction=direction,
            prior_direction=prior_direction,
            structure=structure,
            momentum=momentum,
            pullback=pullback,
            failed=failed,
            divergence=divergence,
            reversal_pressure=reversal_pressure,
            continuation_strength=continuation_strength,
        )
        regime = self._regime(phase, direction, frame, atr_value)
        quality = self._score(continuation_strength, reversal_pressure, phase, metrics)
        continuation_probability, reversal_probability = self._probabilities(
            quality,
            continuation_strength,
            reversal_pressure,
            phase,
        )
        story = self._trade_story(
            previous_thesis=previous_thesis,
            direction=direction,
            phase=phase,
            continuation_probability=continuation_probability,
            reversal_probability=reversal_probability,
            structure=structure,
            momentum=momentum,
            pullback=pullback,
            failed=failed,
            divergence=divergence,
        )
        explanation = (
            f"{timeframe} {direction} trend quality {quality}/100: {phase}. "
            f"Continuation {continuation_probability:.0%}, reversal {reversal_probability:.0%}. "
            f"{story.explanation}"
        )
        return TrendQualityResult(
            symbol=symbol,
            timeframe=timeframe,
            trend_direction=direction,
            trend_quality_score=quality,
            trend_phase=phase,
            continuation_probability=continuation_probability,
            reversal_probability=reversal_probability,
            regime=regime,
            explanation=explanation,
            trade_story=story,
            metrics=metrics,
        )

    def _compute_metrics(
        self,
        frame: pd.DataFrame,
        highs: list[tuple[int, float]],
        lows: list[tuple[int, float]],
        direction: TrendDirection,
        atr_value: float,
    ) -> TrendQualityMetrics:
        hh_hl = self._hh_hl_quality(highs, lows, direction, atr_value)
        ll_lh = self._ll_lh_quality(highs, lows, direction, atr_value)
        acceleration = self._trend_acceleration(frame, atr_value)
        exhaustion = self._trend_exhaustion(frame, direction, atr_value)
        participation = volume_participation(frame)
        health = self._trend_health(hh_hl, ll_lh, acceleration, exhaustion, participation, direction)
        return TrendQualityMetrics(
            hh_hl_quality=hh_hl,
            ll_lh_quality=ll_lh,
            trend_acceleration=acceleration,
            trend_exhaustion=exhaustion,
            trend_health=health,
            trend_participation=participation,
        )

    @staticmethod
    def _hh_hl_quality(
        highs: list[tuple[int, float]],
        lows: list[tuple[int, float]],
        direction: TrendDirection,
        atr_value: float,
    ) -> int:
        if len(highs) < 2 or len(lows) < 2:
            return 40
        high_delta = (highs[-1][1] - highs[-2][1]) / atr_value
        low_delta = (lows[-1][1] - lows[-2][1]) / atr_value
        score = 35.0
        if high_delta > 0:
            score += min(30.0, high_delta * 25.0)
        if low_delta > 0:
            score += min(30.0, low_delta * 25.0)
        if direction == "bullish" and high_delta > 0 and low_delta > 0:
            score += 10.0
        return int(max(0, min(100, round(score))))

    @staticmethod
    def _ll_lh_quality(
        highs: list[tuple[int, float]],
        lows: list[tuple[int, float]],
        direction: TrendDirection,
        atr_value: float,
    ) -> int:
        if len(highs) < 2 or len(lows) < 2:
            return 40
        high_delta = (highs[-1][1] - highs[-2][1]) / atr_value
        low_delta = (lows[-1][1] - lows[-2][1]) / atr_value
        score = 35.0
        if high_delta < 0:
            score += min(30.0, abs(high_delta) * 25.0)
        if low_delta < 0:
            score += min(30.0, abs(low_delta) * 25.0)
        if direction == "bearish" and high_delta < 0 and low_delta < 0:
            score += 10.0
        return int(max(0, min(100, round(score))))

    @staticmethod
    def _trend_acceleration(frame: pd.DataFrame, atr_value: float) -> float:
        close = frame["close"].astype(float)
        if len(close) < 30:
            return 0.5
        early = close.iloc[-30:-15]
        late = close.iloc[-15:]
        early_move = abs(float(early.iloc[-1]) - float(early.iloc[0])) / atr_value
        late_move = abs(float(late.iloc[-1]) - float(late.iloc[0])) / atr_value
        if early_move <= 0:
            return 0.5
        ratio = late_move / early_move
        return max(0.0, min(1.0, ratio / 1.5))

    @staticmethod
    def _trend_exhaustion(frame: pd.DataFrame, direction: TrendDirection, atr_value: float) -> float:
        recent = frame.tail(20)
        previous = frame.iloc[-40:-20] if len(frame) >= 40 else frame.head(0)
        if previous.empty:
            return 0.0
        recent_move = abs(float(recent["close"].iloc[-1]) - float(recent["close"].iloc[0])) / atr_value
        previous_move = abs(float(previous["close"].iloc[-1]) - float(previous["close"].iloc[0])) / atr_value
        exhaustion = 0.0
        if previous_move > 0 and recent_move < previous_move * 0.65:
            exhaustion += 0.45
        ranges = (recent["high"] - recent["low"]).astype(float)
        if float(ranges.std()) > float(ranges.mean()) * 1.2:
            exhaustion += 0.25
        if direction == "bullish":
            wicks = ((recent["high"] - recent["close"]) > 0.55 * (recent["high"] - recent["low"])).mean()
            exhaustion += float(wicks) * 0.30
        elif direction == "bearish":
            wicks = ((recent["close"] - recent["low"]) > 0.55 * (recent["high"] - recent["low"])).mean()
            exhaustion += float(wicks) * 0.30
        return max(0.0, min(1.0, exhaustion))

    @staticmethod
    def _trend_health(
        hh_hl: int,
        ll_lh: int,
        acceleration: float,
        exhaustion: float,
        participation: float,
        direction: TrendDirection,
    ) -> float:
        structure = hh_hl if direction == "bullish" else ll_lh if direction == "bearish" else (hh_hl + ll_lh) // 2
        score = structure / 100.0 * 0.35 + acceleration * 0.25 + participation * 0.20 + (1.0 - exhaustion) * 0.20
        return max(0.0, min(1.0, score))

    def _validate(self, candles: pd.DataFrame) -> None:
        missing = {"open", "high", "low", "close"} - set(candles.columns)
        if missing:
            raise TrendQualityEngineError(f"Missing columns: {', '.join(sorted(missing))}")
        if len(candles) < self.config.min_candles:
            raise TrendQualityEngineError(
                f"Need at least {self.config.min_candles} candles for trend quality"
            )

    def _atr(self, frame: pd.DataFrame) -> pd.Series:
        prev_close = frame["close"].shift(1)
        tr = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - prev_close).abs(),
                (frame["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return tr.rolling(self.config.atr_period, min_periods=3).mean().bfill()

    def _swings(self, frame: pd.DataFrame) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
        window = self.config.swing_window
        highs: list[tuple[int, float]] = []
        lows: list[tuple[int, float]] = []
        for index in range(window, len(frame) - window):
            high = float(frame["high"].iloc[index])
            low = float(frame["low"].iloc[index])
            high_slice = frame["high"].iloc[index - window : index + window + 1]
            low_slice = frame["low"].iloc[index - window : index + window + 1]
            if high >= float(high_slice.max()):
                highs.append((index, high))
            if low <= float(low_slice.min()):
                lows.append((index, low))
        return highs, lows

    def _direction(
        self,
        frame: pd.DataFrame,
        highs: list[tuple[int, float]],
        lows: list[tuple[int, float]],
        atr_value: float,
    ) -> TrendDirection:
        if len(highs) >= 2 and len(lows) >= 2:
            higher_highs = highs[-1][1] > highs[-2][1]
            higher_lows = lows[-1][1] > lows[-2][1]
            lower_highs = highs[-1][1] < highs[-2][1]
            lower_lows = lows[-1][1] < lows[-2][1]
            if higher_highs and higher_lows:
                return "bullish"
            if lower_highs and lower_lows:
                return "bearish"

        slope = (float(frame["close"].iloc[-1]) - float(frame["close"].iloc[-20])) / atr_value
        if slope > 1.0:
            return "bullish"
        if slope < -1.0:
            return "bearish"
        return "neutral"

    def _prior_direction(self, frame: pd.DataFrame, atr_value: float) -> TrendDirection:
        if len(frame) < 30:
            return "neutral"
        prior = frame.iloc[-60:-20] if len(frame) >= 60 else frame.iloc[: len(frame) // 2]
        if len(prior) < 20:
            return "neutral"
        slope = (float(prior["close"].iloc[-1]) - float(prior["close"].iloc[0])) / atr_value
        early = frame.iloc[: max(len(frame) - 12, 20)]
        broad_slope = (float(early["close"].iloc[-1]) - float(early["close"].iloc[0])) / atr_value
        if slope > 1.0:
            return "bullish"
        if slope < -1.0:
            return "bearish"
        if broad_slope > 1.5:
            return "bullish"
        if broad_slope < -1.5:
            return "bearish"
        return "neutral"

    def _structure_state(
        self,
        frame: pd.DataFrame,
        highs: list[tuple[int, float]],
        lows: list[tuple[int, float]],
        direction: TrendDirection,
        atr_value: float,
    ) -> dict[str, float]:
        continuation = 0.0
        reversal = 0.0
        weak_new_extreme = 0.0
        if len(highs) >= 2 and len(lows) >= 2:
            high_delta = (highs[-1][1] - highs[-2][1]) / atr_value
            low_delta = (lows[-1][1] - lows[-2][1]) / atr_value
            last_close = float(frame["close"].iloc[-1])
            if direction == "bullish":
                if high_delta > 0 and low_delta > 0:
                    continuation += 0.35
                if lows[-1][1] < lows[-2][1] or last_close < lows[-2][1]:
                    reversal += 0.45
                if 0 < high_delta < 0.35:
                    weak_new_extreme = 0.2
            elif direction == "bearish":
                if high_delta < 0 and low_delta < 0:
                    continuation += 0.35
                if highs[-1][1] > highs[-2][1] or last_close > highs[-2][1]:
                    reversal += 0.45
                if -0.35 < low_delta < 0:
                    weak_new_extreme = 0.2
        return {
            "continuation": continuation,
            "reversal": reversal + weak_new_extreme,
            "weak_new_extreme": weak_new_extreme,
        }

    def _momentum_state(
        self,
        frame: pd.DataFrame,
        direction: TrendDirection,
        atr_value: float,
    ) -> dict[str, float]:
        closes = frame["close"].astype(float)
        chunks = [closes.iloc[-40:-30], closes.iloc[-30:-20], closes.iloc[-20:-10], closes.iloc[-10:]]
        moves = [(float(chunk.iloc[-1]) - float(chunk.iloc[0])) / atr_value for chunk in chunks if len(chunk) > 2]
        if len(moves) < 3:
            return {"continuation": 0.0, "deterioration": 0.0}
        recent = moves[-1]
        prior = moves[-2]
        older = moves[-3]
        continuation = 0.0
        deterioration = 0.0
        if direction == "bullish":
            if recent > prior and recent > 0:
                continuation += 0.25
            if recent < prior < older or recent < 0:
                deterioration += 0.35
        elif direction == "bearish":
            if recent < prior and recent < 0:
                continuation += 0.25
            if recent > prior > older or recent > 0:
                deterioration += 0.35
        return {"continuation": continuation, "deterioration": deterioration}

    def _pullback_state(
        self,
        frame: pd.DataFrame,
        direction: TrendDirection,
        atr_value: float,
    ) -> dict[str, float]:
        closes = frame["close"].astype(float)
        recent_high = float(frame["high"].tail(20).max())
        recent_low = float(frame["low"].tail(20).min())
        last_close = float(closes.iloc[-1])
        span_atr = max((recent_high - recent_low) / atr_value, 0.01)
        health = 0.0
        danger = 0.0
        if direction == "bullish":
            pullback_depth = (recent_high - last_close) / atr_value
            if pullback_depth < max(0.45 * span_atr, 0.8):
                health += 0.25
            elif pullback_depth > max(0.7 * span_atr, 1.4):
                danger += 0.3
        elif direction == "bearish":
            pullback_depth = (last_close - recent_low) / atr_value
            if pullback_depth < max(0.45 * span_atr, 0.8):
                health += 0.25
            elif pullback_depth > max(0.7 * span_atr, 1.4):
                danger += 0.3
        return {"health": health, "danger": danger}

    def _failed_continuation(
        self,
        frame: pd.DataFrame,
        direction: TrendDirection,
        atr_value: float,
    ) -> dict[str, float]:
        tail = frame.tail(12)
        closes = tail["close"].astype(float)
        highs = tail["high"].astype(float)
        lows = tail["low"].astype(float)
        pressure = 0.0
        net_progress = abs(float(closes.iloc[-1]) - float(closes.iloc[0])) / atr_value
        if direction == "bullish":
            extreme = float(highs.max())
            extreme_index = int(highs.reset_index(drop=True).idxmax())
            close_failures = int((closes < extreme - 0.25 * atr_value).sum())
            wick_rejections = int(((highs - closes) > 0.6 * (highs - lows)).sum())
            if extreme_index < len(tail) // 2 and close_failures >= 8:
                pressure += 0.25
            if net_progress < 0.8 and wick_rejections >= 4:
                pressure += 0.2
        elif direction == "bearish":
            extreme = float(lows.min())
            extreme_index = int(lows.reset_index(drop=True).idxmin())
            close_failures = int((closes > extreme + 0.25 * atr_value).sum())
            wick_rejections = int(((closes - lows) > 0.6 * (highs - lows)).sum())
            if extreme_index < len(tail) // 2 and close_failures >= 8:
                pressure += 0.25
            if net_progress < 0.8 and wick_rejections >= 4:
                pressure += 0.2
        overlap = ((tail["high"].shift(1) >= tail["low"]) & (tail["low"].shift(1) <= tail["high"])).mean()
        if overlap > 0.8 and net_progress < 0.8:
            pressure += 0.15
        return {"pressure": min(pressure, 0.55)}

    def _divergence_state(
        self,
        frame: pd.DataFrame,
        direction: TrendDirection,
        atr_value: float,
    ) -> dict[str, float]:
        recent = frame.tail(20)
        previous = frame.iloc[-40:-20] if len(frame) >= 40 else frame.head(0)
        if previous.empty:
            return {"pressure": 0.0}
        recent_range = float((recent["high"] - recent["low"]).mean()) / atr_value
        previous_range = float((previous["high"] - previous["low"]).mean()) / atr_value
        recent_move = abs(float(recent["close"].iloc[-1]) - float(recent["close"].iloc[0])) / atr_value
        previous_move = abs(float(previous["close"].iloc[-1]) - float(previous["close"].iloc[0])) / atr_value
        pressure = 0.0
        if recent_move < previous_move * 0.7:
            pressure += 0.2
        if recent_range < previous_range * 0.8:
            pressure += 0.15
        if "tick_volume" in frame.columns:
            recent_vol = float(recent["tick_volume"].mean())
            previous_vol = float(previous["tick_volume"].mean())
            if recent_vol < previous_vol * 0.85:
                pressure += 0.15
        return {"pressure": min(pressure, 0.45)}

    def _phase(
        self,
        *,
        direction: TrendDirection,
        prior_direction: TrendDirection,
        structure: dict[str, float],
        momentum: dict[str, float],
        pullback: dict[str, float],
        failed: dict[str, float],
        divergence: dict[str, float],
        reversal_pressure: float,
        continuation_strength: float,
    ) -> TrendPhase:
        if (
            prior_direction in {"bullish", "bearish"}
            and direction in {"bullish", "bearish"}
            and prior_direction != direction
        ):
            return "confirmed_reversal"
        if direction == "neutral":
            return "distribution" if failed["pressure"] + divergence["pressure"] >= 0.30 else "healthy_pullback"
        if structure["reversal"] >= 0.45 and momentum["deterioration"] >= 0.25:
            return "confirmed_reversal"
        if reversal_pressure >= 1.0:
            return "reversal_warning"
        if failed["pressure"] >= 0.4:
            return "distribution"
        if momentum["deterioration"] >= 0.3 or divergence["pressure"] >= 0.3:
            return "exhaustion"
        if pullback["health"] > 0 and continuation_strength < 0.55:
            return "healthy_pullback"
        return "expansion"

    def _regime(
        self,
        phase: TrendPhase,
        direction: TrendDirection,
        frame: pd.DataFrame,
        atr_value: float,
    ) -> TrendRegime:
        if phase in {"confirmed_reversal", "reversal_warning"}:
            return "reversal"
        if phase == "distribution":
            return "distribution" if direction == "bullish" else "accumulation"
        if direction == "neutral":
            return "ranging"
        slope = abs(float(frame["close"].iloc[-1]) - float(frame["close"].iloc[-20])) / atr_value
        return "trending" if slope > 1.0 else "ranging"

    def _score(
        self,
        continuation_strength: float,
        reversal_pressure: float,
        phase: TrendPhase,
        metrics: TrendQualityMetrics,
    ) -> int:
        score = 50 + continuation_strength * 45 - reversal_pressure * 35
        score += metrics.trend_health * 15 - metrics.trend_exhaustion * 20
        if phase == "expansion":
            score += 10
        elif phase in {"exhaustion", "distribution"}:
            score -= 15
        elif phase in {"reversal_warning", "confirmed_reversal"}:
            score -= 25
        return int(max(0, min(100, round(score))))

    def _probabilities(
        self,
        quality: int,
        continuation_strength: float,
        reversal_pressure: float,
        phase: TrendPhase,
    ) -> tuple[float, float]:
        continuation = quality / 100 * 0.65 + min(continuation_strength, 1.0) * 0.25
        reversal = min(reversal_pressure, 1.4) / 1.4 * 0.7 + (1 - quality / 100) * 0.25
        if phase == "confirmed_reversal":
            reversal = max(reversal, 0.72)
            continuation = min(continuation, 0.35)
        return round(min(max(continuation, 0.05), 0.95), 3), round(min(max(reversal, 0.05), 0.95), 3)

    def _trade_story(
        self,
        *,
        previous_thesis: str,
        direction: TrendDirection,
        phase: TrendPhase,
        continuation_probability: float,
        reversal_probability: float,
        structure: dict[str, float],
        momentum: dict[str, float],
        pullback: dict[str, float],
        failed: dict[str, float],
        divergence: dict[str, float],
    ) -> TradeStory:
        current = f"{direction} {phase}"
        if phase == "confirmed_reversal":
            trend_state: Literal["improving", "stable", "deteriorating", "reversing"] = "reversing"
            action: Literal["continue", "reduce_size", "pause", "reverse_bias"] = "reverse_bias"
        elif phase in {"reversal_warning", "distribution", "exhaustion"}:
            trend_state = "deteriorating"
            action = "pause" if reversal_probability >= continuation_probability else "reduce_size"
        elif phase == "expansion":
            trend_state = "improving"
            action = "continue"
        else:
            trend_state = "stable"
            action = "reduce_size"

        changed = []
        if structure["reversal"] > 0:
            changed.append("structure is breaking")
        if momentum["deterioration"] > 0:
            changed.append("impulses are deteriorating")
        if pullback["danger"] > 0:
            changed.append("pullbacks are dangerous")
        if failed["pressure"] > 0:
            changed.append("continuation is failing")
        if divergence["pressure"] > 0:
            changed.append("divergence pressure is rising")
        what_changed = ", ".join(changed) if changed else "trend remains orderly"
        explanation = (
            f"{what_changed}; action={action}; "
            f"continuation/reversal={continuation_probability:.0%}/{reversal_probability:.0%}"
        )
        return TradeStory(
            previous_thesis=previous_thesis or "not recorded",
            current_thesis=current,
            what_changed=what_changed,
            trend_state=trend_state,
            action=action,
            explanation=explanation,
        )
