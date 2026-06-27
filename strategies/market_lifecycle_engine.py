"""Market lifecycle engine — classify where the market is in its cycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategies.distribution_accumulation_engine import DistributionAccumulationEngine
from strategies.market_reading_utils import validate_candles
from strategies.reversal_pressure_engine import ReversalPressureEngine
from strategies.retracement_vs_reversal_engine import RetracementVsReversalEngine
from strategies.trend_quality_engine import TrendQualityEngine

LifecyclePhase = Literal[
    "accumulation",
    "expansion",
    "exhaustion",
    "reversal",
    "consolidation",
]


@dataclass(frozen=True)
class MarketLifecycleResult:
    """Lifecycle phase with strategy guidance."""

    symbol: str
    timeframe: str
    lifecycle_phase: LifecyclePhase
    phase_confidence: float
    trend_quality_score: int
    reversal_pressure_score: int
    retracement_probability: float
    reversal_probability: float
    wyckoff_phase: str
    explanation: str
    trade_opportunity: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "lifecycle_phase": self.lifecycle_phase,
            "phase_confidence": round(self.phase_confidence, 3),
            "trend_quality_score": self.trend_quality_score,
            "reversal_pressure_score": self.reversal_pressure_score,
            "retracement_probability": round(self.retracement_probability, 3),
            "reversal_probability": round(self.reversal_probability, 3),
            "wyckoff_phase": self.wyckoff_phase,
            "explanation": self.explanation,
            "trade_opportunity": self.trade_opportunity,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class MarketLifecycleConfig:
    min_candles: int = 50
    lookback: int = 100


class MarketLifecycleEngineError(Exception):
    pass


class MarketLifecycleEngine:
    """Classify market lifecycle and map to tradable strategy."""

    def __init__(
        self,
        config: MarketLifecycleConfig | None = None,
        *,
        trend_engine: TrendQualityEngine | None = None,
        reversal_engine: ReversalPressureEngine | None = None,
        retracement_engine: RetracementVsReversalEngine | None = None,
        wyckoff_engine: DistributionAccumulationEngine | None = None,
    ) -> None:
        self.config = config or MarketLifecycleConfig()
        self._trend = trend_engine or TrendQualityEngine()
        self._reversal = reversal_engine or ReversalPressureEngine()
        self._retracement = retracement_engine or RetracementVsReversalEngine()
        self._wyckoff = wyckoff_engine or DistributionAccumulationEngine()

    def analyze(
        self,
        candles: pd.DataFrame,
        *,
        symbol: str = "",
        timeframe: str = "H1",
    ) -> MarketLifecycleResult:
        try:
            frame = validate_candles(
                candles, min_candles=self.config.min_candles, engine="MarketLifecycleEngine"
            ).tail(self.config.lookback)
        except ValueError as exc:
            raise MarketLifecycleEngineError(str(exc)) from exc

        trend = self._trend.analyze(frame, symbol=symbol, timeframe=timeframe)
        reversal = self._reversal.analyze(frame, symbol=symbol, timeframe=timeframe)
        retracement = self._retracement.analyze(frame, symbol=symbol, timeframe=timeframe)
        wyckoff = self._wyckoff.analyze(frame, symbol=symbol, timeframe=timeframe)

        phase, confidence = self._classify_lifecycle(
            trend_phase=trend.trend_phase,
            trend_quality=trend.trend_quality_score,
            reversal_pressure=reversal.reversal_pressure_score,
            retracement_prob=retracement.retracement_probability,
            reversal_prob=retracement.reversal_probability,
            wyckoff_phase=wyckoff.phase,
        )
        opportunity = self._trade_opportunity(phase, wyckoff.phase, trend.trend_direction)
        evidence = (
            f"trend quality {trend.trend_quality_score}/100",
            f"reversal pressure {reversal.reversal_pressure_score}/100",
            f"retracement/reversal {retracement.retracement_probability:.0%}/{retracement.reversal_probability:.0%}",
            f"wyckoff {wyckoff.phase}",
            wyckoff.trade_opportunity,
        )

        return MarketLifecycleResult(
            symbol=symbol,
            timeframe=timeframe,
            lifecycle_phase=phase,
            phase_confidence=confidence,
            trend_quality_score=trend.trend_quality_score,
            reversal_pressure_score=reversal.reversal_pressure_score,
            retracement_probability=retracement.retracement_probability,
            reversal_probability=retracement.reversal_probability,
            wyckoff_phase=wyckoff.phase,
            explanation=f"Lifecycle {phase} ({confidence:.0%}) on {timeframe}",
            trade_opportunity=opportunity,
            evidence=evidence,
        )

    @staticmethod
    def _classify_lifecycle(
        *,
        trend_phase: str,
        trend_quality: int,
        reversal_pressure: int,
        retracement_prob: float,
        reversal_prob: float,
        wyckoff_phase: str,
    ) -> tuple[LifecyclePhase, float]:
        scores: dict[LifecyclePhase, float] = {
            "accumulation": 0.0,
            "expansion": 0.0,
            "exhaustion": 0.0,
            "reversal": 0.0,
            "consolidation": 0.0,
        }

        if wyckoff_phase == "accumulation":
            scores["accumulation"] += 0.40
        if wyckoff_phase in {"markup"}:
            scores["expansion"] += 0.35
        if wyckoff_phase == "distribution":
            scores["exhaustion"] += 0.35
        if wyckoff_phase == "markdown":
            scores["reversal"] += 0.30

        if trend_phase == "expansion":
            scores["expansion"] += 0.35
        elif trend_phase in {"exhaustion", "distribution"}:
            scores["exhaustion"] += 0.35
        elif trend_phase in {"reversal_warning", "confirmed_reversal"}:
            scores["reversal"] += 0.40
        elif trend_phase == "healthy_pullback":
            scores["consolidation"] += 0.25
            scores["expansion"] += 0.15

        if trend_quality >= 65:
            scores["expansion"] += 0.15
        elif trend_quality <= 40:
            scores["exhaustion"] += 0.15

        if reversal_pressure >= 60:
            scores["reversal"] += 0.25
            scores["exhaustion"] += 0.15
        elif reversal_pressure <= 25:
            scores["expansion"] += 0.10

        if reversal_prob >= 0.58:
            scores["reversal"] += 0.20
        if retracement_prob >= 0.58 and trend_quality >= 50:
            scores["expansion"] += 0.15
            scores["consolidation"] += 0.10

        if trend_phase == "healthy_pullback" and wyckoff_phase == "unclear":
            scores["consolidation"] += 0.30

        phase = max(scores, key=scores.get)  # type: ignore[arg-type]
        confidence = max(0.35, min(0.95, scores[phase]))  # type: ignore[index]
        return phase, confidence

    @staticmethod
    def _trade_opportunity(phase: LifecyclePhase, wyckoff: str, direction: str) -> str:
        opportunities = {
            "accumulation": "Build positions on support tests and liquidity sweeps below range",
            "expansion": "Trade pullbacks and breakouts in direction of trend",
            "exhaustion": "Take profits, scout reversals, fade failed extensions",
            "reversal": "Trade new directional bias — reversal entries and retests",
            "consolidation": "Range trade boundaries or prepare for breakout",
        }
        base = opportunities[phase]
        if wyckoff == "markup" and direction == "bullish":
            return f"{base} | bullish markup active"
        if wyckoff == "markdown" and direction == "bearish":
            return f"{base} | bearish markdown active"
        return base


__all__ = [
    "LifecyclePhase",
    "MarketLifecycleConfig",
    "MarketLifecycleEngine",
    "MarketLifecycleEngineError",
    "MarketLifecycleResult",
]
