"""False breakout engine — distinguish genuine breaks from traps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategies.market_reading_utils import atr_series, validate_candles

BreakoutClass = Literal["genuine", "failed", "developing", "none"]


@dataclass(frozen=True)
class FalseBreakoutResult:
    """Breakout quality and trap detection."""

    symbol: str
    timeframe: str
    breakout_quality_score: int
    breakout_class: BreakoutClass
    direction: Literal["up", "down", "neutral"]
    trapped_traders: Literal["longs", "shorts", "none"]
    false_breakout_probability: float
    explanation: str
    evidence: tuple[str, ...] = ()
    trade_opportunity: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "breakout_quality_score": self.breakout_quality_score,
            "breakout_class": self.breakout_class,
            "direction": self.direction,
            "trapped_traders": self.trapped_traders,
            "false_breakout_probability": round(self.false_breakout_probability, 3),
            "explanation": self.explanation,
            "evidence": list(self.evidence),
            "trade_opportunity": self.trade_opportunity,
        }


@dataclass(frozen=True)
class FalseBreakoutConfig:
    min_candles: int = 50
    lookback: int = 80
    boundary_quantile: float = 0.12


class FalseBreakoutEngineError(Exception):
    pass


class FalseBreakoutEngine:
    """Identify genuine breakouts, failed breakouts, and trapped traders."""

    def __init__(self, config: FalseBreakoutConfig | None = None) -> None:
        self.config = config or FalseBreakoutConfig()

    def analyze(
        self,
        candles: pd.DataFrame,
        *,
        symbol: str = "",
        timeframe: str = "H1",
    ) -> FalseBreakoutResult:
        try:
            frame = validate_candles(
                candles, min_candles=self.config.min_candles, engine="FalseBreakoutEngine"
            ).tail(self.config.lookback)
        except ValueError as exc:
            raise FalseBreakoutEngineError(str(exc)) from exc

        atr = atr_series(frame)
        atr_value = float(atr.iloc[-1]) or float((frame["high"] - frame["low"]).median()) or 1.0
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        close = frame["close"].astype(float)
        volume = frame["tick_volume"].astype(float) if "tick_volume" in frame.columns else None

        support = float(low.quantile(self.config.boundary_quantile))
        resistance = float(high.quantile(1.0 - self.config.boundary_quantile))
        tolerance = atr_value * 0.35
        current = float(close.iloc[-1])

        broke_up = current > resistance + tolerance
        broke_down = current < support - tolerance
        false_up = bool(((high.iloc[-8:] > resistance + tolerance) & (close.iloc[-8:] < resistance)).any())
        false_down = bool(((low.iloc[-8:] < support - tolerance) & (close.iloc[-8:] > support)).any())

        evidence: list[str] = []
        quality = 50
        breakout_class: BreakoutClass = "none"
        direction: Literal["up", "down", "neutral"] = "neutral"
        trapped: Literal["longs", "shorts", "none"] = "none"
        false_prob = 0.25

        follow_through = abs(current - float(close.iloc[-4])) / atr_value
        vol_ratio = 1.0
        if volume is not None and len(volume) >= 20:
            vol_ratio = float(volume.iloc[-1] / max(volume.rolling(20, min_periods=5).mean().iloc[-1], 1.0))

        if false_up:
            breakout_class = "failed"
            direction = "up"
            trapped = "longs"
            false_prob = 0.78
            quality = 28
            evidence.append("failed upside breakout — longs trapped")
        elif false_down:
            breakout_class = "failed"
            direction = "down"
            trapped = "shorts"
            false_prob = 0.78
            quality = 28
            evidence.append("failed downside breakout — shorts trapped")
        elif broke_up:
            breakout_class = "genuine" if follow_through >= 0.6 and vol_ratio >= 1.0 else "developing"
            direction = "up"
            quality = int(min(95, 55 + follow_through * 20 + (vol_ratio - 1.0) * 15))
            false_prob = max(0.10, 0.45 - follow_through * 0.15)
            evidence.append(f"upside break — follow-through {follow_through:.1f} ATR")
            if vol_ratio >= 1.05:
                evidence.append("volume confirms breakout")
        elif broke_down:
            breakout_class = "genuine" if follow_through >= 0.6 and vol_ratio >= 1.0 else "developing"
            direction = "down"
            quality = int(min(95, 55 + follow_through * 20 + (vol_ratio - 1.0) * 15))
            false_prob = max(0.10, 0.45 - follow_through * 0.15)
            evidence.append(f"downside break — follow-through {follow_through:.1f} ATR")
            if vol_ratio >= 1.05:
                evidence.append("volume confirms breakout")
        else:
            near_res = abs(current - resistance) <= tolerance
            near_sup = abs(current - support) <= tolerance
            if near_res or near_sup:
                breakout_class = "developing"
                direction = "up" if near_res else "down"
                quality = 42
                false_prob = 0.40
                evidence.append("price testing range boundary — breakout developing")

        opportunity = self._trade_opportunity(breakout_class, direction, trapped)

        return FalseBreakoutResult(
            symbol=symbol,
            timeframe=timeframe,
            breakout_quality_score=quality,
            breakout_class=breakout_class,
            direction=direction,
            trapped_traders=trapped,
            false_breakout_probability=false_prob,
            explanation=(
                f"Breakout quality {quality}/100 — {breakout_class} "
                f"({direction}), false break prob {false_prob:.0%}"
            ),
            evidence=tuple(evidence or ("No breakout activity",)),
            trade_opportunity=opportunity,
        )

    @staticmethod
    def _trade_opportunity(
        breakout_class: BreakoutClass,
        direction: str,
        trapped: str,
    ) -> str:
        if breakout_class == "genuine":
            if direction == "up":
                return "Trade breakout continuation or retest of broken resistance"
            return "Trade breakdown continuation or retest of broken support"
        if breakout_class == "failed":
            if trapped == "longs":
                return "Fade failed breakout — short trapped longs"
            if trapped == "shorts":
                return "Fade failed breakdown — long trapped shorts"
        if breakout_class == "developing":
            return "Prepare bracket — scout break/retest with reduced size until confirmed"
        return "No breakout edge — trade range logic until boundary breaks"


__all__ = [
    "BreakoutClass",
    "FalseBreakoutConfig",
    "FalseBreakoutEngine",
    "FalseBreakoutEngineError",
    "FalseBreakoutResult",
]
