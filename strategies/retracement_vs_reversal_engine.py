"""Retracement vs reversal engine — distinguish pullback from regime change."""

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

Classification = Literal["retracement", "reversal", "unclear"]


@dataclass(frozen=True)
class RetracementVsReversalResult:
    """Probability-weighted pullback vs reversal assessment."""

    symbol: str
    timeframe: str
    retracement_probability: float
    reversal_probability: float
    classification: Classification
    trend_direction: Literal["bullish", "bearish", "neutral"]
    structure_break: bool
    trendline_break: bool
    explanation: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "retracement_probability": round(self.retracement_probability, 3),
            "reversal_probability": round(self.reversal_probability, 3),
            "classification": self.classification,
            "trend_direction": self.trend_direction,
            "structure_break": self.structure_break,
            "trendline_break": self.trendline_break,
            "explanation": self.explanation,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class RetracementVsReversalConfig:
    min_candles: int = 40
    lookback: int = 80
    atr_period: int = 14
    swing_window: int = 2


class RetracementVsReversalEngineError(Exception):
    pass


class RetracementVsReversalEngine:
    """Distinguish temporary pullback from actual reversal."""

    def __init__(self, config: RetracementVsReversalConfig | None = None) -> None:
        self.config = config or RetracementVsReversalConfig()

    def analyze(
        self,
        candles: pd.DataFrame,
        *,
        symbol: str = "",
        timeframe: str = "H1",
    ) -> RetracementVsReversalResult:
        try:
            frame = validate_candles(
                candles,
                min_candles=self.config.min_candles,
                engine="RetracementVsReversalEngine",
            ).tail(self.config.lookback)
        except ValueError as exc:
            raise RetracementVsReversalEngineError(str(exc)) from exc

        atr = atr_series(frame, self.config.atr_period)
        atr_value = float(atr.iloc[-1]) or float((frame["high"] - frame["low"]).median()) or 1.0
        highs, lows = swing_points(frame, window=self.config.swing_window)
        direction = trend_direction_from_swings(highs, lows, frame, atr_value)

        evidence: list[str] = []
        retracement_score = 0.0
        reversal_score = 0.0

        struct_score, struct_break, struct_ev = self._structure_signal(
            highs, lows, direction, frame, atr_value
        )
        retracement_score += struct_score["retracement"]
        reversal_score += struct_score["reversal"]
        evidence.extend(struct_ev)

        mom_score, mom_ev = self._momentum_signal(frame, direction, atr_value)
        retracement_score += mom_score["retracement"]
        reversal_score += mom_score["reversal"]
        evidence.extend(mom_ev)

        vol_score, vol_ev = self._volume_signal(frame, direction)
        retracement_score += vol_score["retracement"]
        reversal_score += vol_score["reversal"]
        evidence.extend(vol_ev)

        volty_score, volty_ev = self._volatility_signal(frame, atr, atr_value)
        retracement_score += volty_score["retracement"]
        reversal_score += volty_score["reversal"]
        evidence.extend(volty_ev)

        tl_break, tl_score, tl_ev = self._trendline_break(frame, direction, atr_value)
        retracement_score += tl_score["retracement"]
        reversal_score += tl_score["reversal"]
        evidence.extend(tl_ev)

        msb_score, msb_ev = self._market_structure_break(highs, lows, direction, frame, atr_value)
        retracement_score += msb_score["retracement"]
        reversal_score += msb_score["reversal"]
        evidence.extend(msb_ev)
        structure_break = struct_break or msb_score["reversal"] > 0.35

        total = retracement_score + reversal_score
        if total <= 0:
            retracement_probability = 0.55
            reversal_probability = 0.45
        else:
            retracement_probability = round(retracement_score / total, 3)
            reversal_probability = round(reversal_score / total, 3)

        if reversal_probability >= 0.58:
            classification: Classification = "reversal"
        elif retracement_probability >= 0.58:
            classification = "retracement"
        else:
            classification = "unclear"

        return RetracementVsReversalResult(
            symbol=symbol,
            timeframe=timeframe,
            retracement_probability=retracement_probability,
            reversal_probability=reversal_probability,
            classification=classification,
            trend_direction=direction,  # type: ignore[arg-type]
            structure_break=structure_break,
            trendline_break=tl_break,
            explanation=(
                f"{classification}: retracement {retracement_probability:.0%} vs "
                f"reversal {reversal_probability:.0%}"
            ),
            evidence=tuple(evidence),
        )

    @staticmethod
    def _structure_signal(
        highs: list[tuple[int, float]],
        lows: list[tuple[int, float]],
        direction: str,
        frame: pd.DataFrame,
        atr_value: float,
    ) -> tuple[dict[str, float], bool, list[str]]:
        score = {"retracement": 0.0, "reversal": 0.0}
        evidence: list[str] = []
        structure_break = False
        last_close = float(frame["close"].iloc[-1])

        if direction == "bullish" and len(lows) >= 2:
            if lows[-1][1] >= lows[-2][1]:
                score["retracement"] += 0.35
                evidence.append("higher low holds — pullback not reversal")
            elif last_close < lows[-2][1]:
                score["reversal"] += 0.45
                structure_break = True
                evidence.append("bullish structure break — prior swing low lost")
        elif direction == "bearish" and len(highs) >= 2:
            if highs[-1][1] <= highs[-2][1]:
                score["retracement"] += 0.35
                evidence.append("lower high holds — pullback not reversal")
            elif last_close > highs[-2][1]:
                score["reversal"] += 0.45
                structure_break = True
                evidence.append("bearish structure break — prior swing high lost")

        depth = 0.0
        if direction == "bullish":
            recent_high = float(frame["high"].tail(20).max())
            depth = (recent_high - last_close) / atr_value
        elif direction == "bearish":
            recent_low = float(frame["low"].tail(20).min())
            depth = (last_close - recent_low) / atr_value
        if 0.3 < depth < 1.2:
            score["retracement"] += 0.20
            evidence.append("pullback depth within normal retracement zone")
        elif depth >= 1.5:
            score["reversal"] += 0.25
            evidence.append("deep retracement threatens trend integrity")

        return score, structure_break, evidence

    @staticmethod
    def _momentum_signal(
        frame: pd.DataFrame, direction: str, atr_value: float
    ) -> tuple[dict[str, float], list[str]]:
        score = {"retracement": 0.0, "reversal": 0.0}
        evidence: list[str] = []
        close = frame["close"].astype(float)
        recent = (float(close.iloc[-1]) - float(close.iloc[-5])) / atr_value
        prior = (float(close.iloc[-5]) - float(close.iloc[-10])) / atr_value if len(close) >= 10 else 0.0

        if direction == "bullish":
            if recent < 0 and prior > 0 and abs(recent) < abs(prior):
                score["retracement"] += 0.30
                evidence.append("momentum cooling within prior impulse")
            if recent < 0 and prior < 0:
                score["reversal"] += 0.30
                evidence.append("momentum flipped bearish")
        elif direction == "bearish":
            if recent > 0 and prior < 0 and abs(recent) < abs(prior):
                score["retracement"] += 0.30
                evidence.append("momentum cooling within prior impulse")
            if recent > 0 and prior > 0:
                score["reversal"] += 0.30
                evidence.append("momentum flipped bullish")
        return score, evidence

    @staticmethod
    def _volume_signal(frame: pd.DataFrame, direction: str) -> tuple[dict[str, float], list[str]]:
        score = {"retracement": 0.0, "reversal": 0.0}
        evidence: list[str] = []
        if "tick_volume" not in frame.columns:
            return score, evidence
        volume = frame["tick_volume"].astype(float)
        recent_vol = float(volume.tail(5).mean())
        counter_move = frame.tail(5)
        if direction == "bullish":
            down_bars = counter_move[counter_move["close"] < counter_move["open"]]
        elif direction == "bearish":
            down_bars = counter_move[counter_move["close"] > counter_move["open"]]
        else:
            return score, evidence
        if not down_bars.empty and "tick_volume" in down_bars.columns:
            counter_vol = float(down_bars["tick_volume"].mean())
            if counter_vol < recent_vol * 0.85:
                score["retracement"] += 0.25
                evidence.append("counter-move on lighter volume — likely retracement")
            elif counter_vol > recent_vol * 1.15:
                score["reversal"] += 0.25
                evidence.append("counter-move on rising volume — reversal risk")
        return score, evidence

    @staticmethod
    def _volatility_signal(
        frame: pd.DataFrame, atr: pd.Series, atr_value: float
    ) -> tuple[dict[str, float], list[str]]:
        score = {"retracement": 0.0, "reversal": 0.0}
        evidence: list[str] = []
        baseline = float(atr.rolling(30, min_periods=5).mean().iloc[-1]) or atr_value
        if atr_value < baseline * 0.85:
            score["retracement"] += 0.20
            evidence.append("volatility compressing — orderly pullback")
        elif atr_value > baseline * 1.25:
            score["reversal"] += 0.20
            evidence.append("volatility expanding — regime shift risk")
        return score, evidence

    @staticmethod
    def _trendline_break(
        frame: pd.DataFrame, direction: str, atr_value: float
    ) -> tuple[bool, dict[str, float], list[str]]:
        score = {"retracement": 0.0, "reversal": 0.0}
        evidence: list[str] = []
        close = frame["close"].astype(float)
        if len(close) < 25:
            return False, score, evidence
        x = range(20)
        y = close.iloc[-20:].values
        n = len(x)
        slope = (n * sum(i * v for i, v in zip(x, y)) - sum(x) * sum(y)) / (
            n * sum(i * i for i in x) - sum(x) ** 2
        )
        projected = float(y[-1] + slope)
        last_close = float(close.iloc[-1])
        break_threshold = atr_value * 0.35
        tl_break = False
        if direction == "bullish" and last_close < projected - break_threshold:
            tl_break = True
            score["reversal"] += 0.30
            evidence.append("trendline support broken")
        elif direction == "bearish" and last_close > projected + break_threshold:
            tl_break = True
            score["reversal"] += 0.30
            evidence.append("trendline resistance broken")
        elif direction in {"bullish", "bearish"}:
            score["retracement"] += 0.15
            evidence.append("price respecting trendline")
        return tl_break, score, evidence

    @staticmethod
    def _market_structure_break(
        highs: list[tuple[int, float]],
        lows: list[tuple[int, float]],
        direction: str,
        frame: pd.DataFrame,
        atr_value: float,
    ) -> tuple[dict[str, float], list[str]]:
        score = {"retracement": 0.0, "reversal": 0.0}
        evidence: list[str] = []
        last_close = float(frame["close"].iloc[-1])
        if direction == "bullish" and len(lows) >= 2:
            key_low = lows[-2][1]
            if last_close < key_low - atr_value * 0.1:
                score["reversal"] += 0.40
                evidence.append("market structure break — CHoCH bearish")
            else:
                score["retracement"] += 0.15
        elif direction == "bearish" and len(highs) >= 2:
            key_high = highs[-2][1]
            if last_close > key_high + atr_value * 0.1:
                score["reversal"] += 0.40
                evidence.append("market structure break — CHoCH bullish")
            else:
                score["retracement"] += 0.15
        return score, evidence


__all__ = [
    "Classification",
    "RetracementVsReversalConfig",
    "RetracementVsReversalEngine",
    "RetracementVsReversalEngineError",
    "RetracementVsReversalResult",
]
