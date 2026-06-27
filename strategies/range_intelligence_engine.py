"""Range intelligence for regime-correct trading decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import pandas as pd

RangeStatus = Literal[
    "horizontal_range",
    "diagonal_range",
    "triangular_range",
    "range_breaking",
    "not_range",
    "unclear",
    "range_continuation",
    "breakout_preparation",
]

REQUIRED_COLUMNS = ("open", "high", "low", "close", "tick_volume", "spread")


@dataclass(frozen=True)
class RangeIntelligenceResult:
    range_status: RangeStatus
    support_level: float
    resistance_level: float
    range_width: float
    equilibrium_zone: float
    range_quality_score: int
    breakout_risk_score: int
    price_location: str
    likely_breakout_direction: str
    explanation: str
    mean_reversion_score: int = 0
    range_continuation_probability: float = 0.0
    range_breakout_preparation_score: int = 0
    trade_opportunity: str = ""
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["evidence"] = tuple(self.evidence)
        return data


@dataclass(frozen=True)
class RangeIntelligenceConfig:
    min_candles: int = 50
    lookback: int = 80
    boundary_tolerance_atr: float = 0.55


class RangeIntelligenceEngineError(Exception):
    pass


class RangeIntelligenceEngine:
    """Identify range shape, boundaries, quality, and breakout risk."""

    def __init__(self, config: RangeIntelligenceConfig | None = None) -> None:
        self.config = config or RangeIntelligenceConfig()

    def analyze(self, candles: pd.DataFrame, *, symbol: str = "") -> RangeIntelligenceResult:
        frame = self._prepare(candles)
        frame = frame.tail(self.config.lookback)
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        close = frame["close"].astype(float)
        volume = frame["tick_volume"].astype(float)
        atr = self._atr(frame)
        atr_now = float(atr.iloc[-1]) or float((high - low).median()) or 1.0

        support = float(low.quantile(0.12))
        resistance = float(high.quantile(0.88))
        width = max(resistance - support, 0.0)
        equilibrium = (support + resistance) / 2.0 if width > 0 else float(close.iloc[-1])
        tolerance = atr_now * self.config.boundary_tolerance_atr
        support_tests = int((low <= support + tolerance).sum())
        resistance_tests = int((high >= resistance - tolerance).sum())
        false_up = int(((high > resistance + tolerance) & (close < resistance)).sum())
        false_down = int(((low < support - tolerance) & (close > support)).sum())
        slope = float((close.iloc[-1] - close.iloc[0]) / max(len(close), 1))
        early_width = float(high.iloc[: len(high) // 2].max() - low.iloc[: len(low) // 2].min())
        late_width = float(high.iloc[len(high) // 2 :].max() - low.iloc[len(low) // 2 :].min())
        narrowing = late_width < early_width * 0.78 if early_width > 0 else False
        atr_ratio = float(atr.iloc[-1] / max(atr.rolling(40, min_periods=10).mean().iloc[-1], atr_now))
        current = float(close.iloc[-1])
        near_support = abs(current - support) <= tolerance
        near_resistance = abs(current - resistance) <= tolerance
        if near_support:
            location = "near_support"
        elif near_resistance:
            location = "near_resistance"
        elif abs(current - equilibrium) <= width * 0.15:
            location = "near_equilibrium"
        elif current > equilibrium:
            location = "upper_half"
        else:
            location = "lower_half"

        rejection_quality = min(1.0, (support_tests + resistance_tests) / 10.0)
        boundary_balance = 1.0 - min(1.0, abs(support_tests - resistance_tests) / 8.0)
        false_break_penalty = min(0.35, (false_up + false_down) * 0.05)
        volatility_stability = max(0.0, 1.0 - abs(atr_ratio - 1.0))
        range_quality = max(
            0.0,
            min(1.0, 0.35 * rejection_quality + 0.25 * boundary_balance + 0.25 * volatility_stability + 0.15 * (1.0 - false_break_penalty)),
        )
        duration_pressure = min(1.0, len(frame) / 120.0)
        test_pressure = min(1.0, (support_tests + resistance_tests) / 14.0)
        compression_pressure = max(0.0, min(1.0, 1.0 - atr_ratio))
        breakout_risk = max(0.0, min(1.0, 0.35 * duration_pressure + 0.30 * test_pressure + 0.25 * compression_pressure + 0.10 * (1.0 if narrowing else 0.0)))
        likely_direction = "neutral"
        if resistance_tests > support_tests + 2 or false_down > false_up:
            likely_direction = "up"
        elif support_tests > resistance_tests + 2 or false_up > false_down:
            likely_direction = "down"

        evidence: list[str] = []
        if support_tests >= 3:
            evidence.append(f"support respected {support_tests} times")
        if resistance_tests >= 3:
            evidence.append(f"resistance respected {resistance_tests} times")
        if false_up:
            evidence.append(f"{false_up} failed upside breakouts")
        if false_down:
            evidence.append(f"{false_down} failed downside breakdowns")
        if narrowing:
            evidence.append("range width narrowing")
        if atr_ratio < 0.8:
            evidence.append("volatility contracting inside range")

        if range_quality < 0.35:
            status: RangeStatus = "not_range"
        elif narrowing and range_quality >= 0.50 and breakout_risk >= 0.55:
            status = "breakout_preparation"
        elif narrowing and range_quality >= 0.50:
            status = "triangular_range"
        elif abs(slope) > atr_now * 0.03:
            status = "diagonal_range"
        elif range_quality >= 0.50 and location in {"near_support", "near_resistance"}:
            status = "range_continuation"
        else:
            status = "horizontal_range"
        if current > resistance + tolerance or current < support - tolerance:
            status = "range_breaking"

        mean_reversion = self._mean_reversion_score(
            current, support, resistance, equilibrium, width, tolerance, location
        )
        continuation_prob = self._range_continuation_probability(
            range_quality, false_up, false_down, location, narrowing
        )
        breakout_prep = int(round(breakout_risk * 100))
        trade_opportunity = self._trade_opportunity(
            status, location, mean_reversion, breakout_prep, likely_direction
        )

        explanation = (
            f"Range {status}: support {support:.5f}, resistance {resistance:.5f}, "
            f"quality {round(range_quality * 100)}, mean reversion {mean_reversion}, "
            f"continuation {continuation_prob:.0%}, breakout prep {breakout_prep}."
        )
        return RangeIntelligenceResult(
            range_status=status,
            support_level=round(support, 5),
            resistance_level=round(resistance, 5),
            range_width=round(width, 5),
            equilibrium_zone=round(equilibrium, 5),
            range_quality_score=int(round(range_quality * 100)),
            breakout_risk_score=int(round(breakout_risk * 100)),
            price_location=location,
            likely_breakout_direction=likely_direction,
            explanation=explanation,
            mean_reversion_score=mean_reversion,
            range_continuation_probability=continuation_prob,
            range_breakout_preparation_score=breakout_prep,
            trade_opportunity=trade_opportunity,
            evidence=tuple(evidence),
        )

    def _prepare(self, candles: pd.DataFrame) -> pd.DataFrame:
        if candles is None or candles.empty:
            raise RangeIntelligenceEngineError("candle data is empty")
        missing = [column for column in REQUIRED_COLUMNS if column not in candles.columns]
        if missing:
            raise RangeIntelligenceEngineError(f"missing columns: {', '.join(missing)}")
        frame = candles.copy()
        if "time" in frame.columns:
            frame["time"] = pd.to_datetime(frame["time"], utc=True)
            frame = frame.sort_values("time")
        frame = frame.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        if len(frame) < self.config.min_candles:
            raise RangeIntelligenceEngineError(f"need at least {self.config.min_candles} candles")
        return frame

    @staticmethod
    def _atr(frame: pd.DataFrame) -> pd.Series:
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        close = frame["close"].astype(float)
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        return tr.rolling(14, min_periods=3).mean().bfill()

    @staticmethod
    def _mean_reversion_score(
        current: float,
        support: float,
        resistance: float,
        equilibrium: float,
        width: float,
        tolerance: float,
        location: str,
    ) -> int:
        if width <= 0:
            return 0
        if location == "near_support":
            return int(min(95, 70 + (support + tolerance - current) / width * 50))
        if location == "near_resistance":
            return int(min(95, 70 + (current - (resistance - tolerance)) / width * 50))
        if location == "near_equilibrium":
            return 25
        dist_from_eq = abs(current - equilibrium) / width
        return int(max(20, min(65, dist_from_eq * 120)))

    @staticmethod
    def _range_continuation_probability(
        range_quality: float,
        false_up: int,
        false_down: int,
        location: str,
        narrowing: bool,
    ) -> float:
        prob = range_quality * 0.55
        if location in {"near_support", "near_resistance"}:
            prob += 0.20
        if false_up + false_down >= 2:
            prob += 0.10
        if narrowing:
            prob -= 0.12
        return round(max(0.05, min(0.95, prob)), 3)

    @staticmethod
    def _trade_opportunity(
        status: str,
        location: str,
        mean_reversion: int,
        breakout_prep: int,
        likely_direction: str,
    ) -> str:
        if status == "range_breaking":
            return f"Breakout active — trade {likely_direction} continuation or retest"
        if status == "breakout_preparation":
            return "Range compressing — scout breakout with bracket logic"
        if mean_reversion >= 65:
            if location == "near_support":
                return "Mean reversion long from support — fade to equilibrium"
            if location == "near_resistance":
                return "Mean reversion short from resistance — fade to equilibrium"
        if status == "range_continuation":
            return "Range continuation — fade extremes back toward equilibrium"
        return "Map range boundaries — trade support/resistance reactions"


__all__ = [
    "RangeIntelligenceConfig",
    "RangeIntelligenceEngine",
    "RangeIntelligenceEngineError",
    "RangeIntelligenceResult",
]
