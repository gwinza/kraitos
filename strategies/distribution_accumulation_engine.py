"""Distribution / accumulation engine — Wyckoff-style phase identification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategies.market_reading_utils import (
    atr_series,
    validate_candles,
    volume_participation,
)

WyckoffPhase = Literal["accumulation", "markup", "distribution", "markdown", "unclear"]
InstitutionalSignal = Literal[
    "absorption",
    "exhaustion",
    "institutional_rotation",
    "none",
]


@dataclass(frozen=True)
class DistributionAccumulationResult:
    """Phase and institutional behaviour assessment."""

    symbol: str
    timeframe: str
    phase: WyckoffPhase
    phase_confidence: float
    institutional_signal: InstitutionalSignal
    absorption_score: float
    exhaustion_score: float
    rotation_score: float
    explanation: str
    evidence: tuple[str, ...] = ()
    trade_opportunity: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "phase": self.phase,
            "phase_confidence": round(self.phase_confidence, 3),
            "institutional_signal": self.institutional_signal,
            "absorption_score": round(self.absorption_score, 3),
            "exhaustion_score": round(self.exhaustion_score, 3),
            "rotation_score": round(self.rotation_score, 3),
            "explanation": self.explanation,
            "evidence": list(self.evidence),
            "trade_opportunity": self.trade_opportunity,
        }


@dataclass(frozen=True)
class DistributionAccumulationConfig:
    min_candles: int = 50
    lookback: int = 100
    atr_period: int = 14


class DistributionAccumulationEngineError(Exception):
    pass


class DistributionAccumulationEngine:
    """Identify accumulation, markup, distribution, and markdown phases."""

    def __init__(self, config: DistributionAccumulationConfig | None = None) -> None:
        self.config = config or DistributionAccumulationConfig()

    def analyze(
        self,
        candles: pd.DataFrame,
        *,
        symbol: str = "",
        timeframe: str = "H1",
    ) -> DistributionAccumulationResult:
        try:
            frame = validate_candles(
                candles,
                min_candles=self.config.min_candles,
                engine="DistributionAccumulationEngine",
            ).tail(self.config.lookback)
        except ValueError as exc:
            raise DistributionAccumulationEngineError(str(exc)) from exc

        atr = atr_series(frame, self.config.atr_period)
        atr_value = float(atr.iloc[-1]) or float((frame["high"] - frame["low"]).median()) or 1.0
        close = frame["close"].astype(float)
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)

        support = float(low.quantile(0.10))
        resistance = float(high.quantile(0.90))
        equilibrium = (support + resistance) / 2.0
        progress = (float(close.iloc[-1]) - float(close.iloc[0])) / atr_value
        participation = volume_participation(frame)

        absorption = self._absorption(frame, support, equilibrium, atr_value)
        exhaustion = self._exhaustion(frame, resistance, equilibrium, atr_value)
        rotation = self._institutional_rotation(frame, support, resistance, atr_value)

        phase_scores = {
            "accumulation": self._accumulation_score(frame, support, equilibrium, absorption, progress),
            "markup": self._markup_score(progress, participation, absorption, exhaustion),
            "distribution": self._distribution_score(frame, resistance, equilibrium, exhaustion, progress),
            "markdown": self._markdown_score(progress, participation, exhaustion, rotation),
        }
        phase = max(phase_scores, key=phase_scores.get)  # type: ignore[arg-type]
        confidence = phase_scores[phase]  # type: ignore[index]

        if confidence < 0.35:
            phase = "unclear"
            confidence = max(phase_scores.values())

        institutional = self._dominant_institutional(absorption, exhaustion, rotation)
        evidence = self._evidence(phase, absorption, exhaustion, rotation, progress)
        opportunity = self._trade_opportunity(phase, institutional)

        return DistributionAccumulationResult(
            symbol=symbol,
            timeframe=timeframe,
            phase=phase,  # type: ignore[arg-type]
            phase_confidence=confidence,
            institutional_signal=institutional,
            absorption_score=absorption,
            exhaustion_score=exhaustion,
            rotation_score=rotation,
            explanation=(
                f"Wyckoff phase {phase} ({confidence:.0%}) — "
                f"institutional signal: {institutional.replace('_', ' ')}"
            ),
            evidence=tuple(evidence),
            trade_opportunity=opportunity,
        )

    @staticmethod
    def _absorption(
        frame: pd.DataFrame, support: float, equilibrium: float, atr_value: float
    ) -> float:
        tail = frame.tail(25)
        low = tail["low"].astype(float)
        close = tail["close"].astype(float)
        volume = tail["tick_volume"].astype(float) if "tick_volume" in tail.columns else None
        hits = int((low <= support + atr_value * 0.35).sum())
        holds = int((close > support + atr_value * 0.2).sum())
        score = min(1.0, hits / 8.0) * 0.5 + min(1.0, holds / 10.0) * 0.3
        if volume is not None and len(volume) >= 10:
            support_vol = volume[low <= support + atr_value * 0.35]
            if len(support_vol) >= 3 and float(support_vol.mean()) > float(volume.mean()) * 1.05:
                score += 0.20
        return max(0.0, min(1.0, score))

    @staticmethod
    def _exhaustion(
        frame: pd.DataFrame, resistance: float, equilibrium: float, atr_value: float
    ) -> float:
        tail = frame.tail(25)
        high = tail["high"].astype(float)
        close = tail["close"].astype(float)
        hits = int((high >= resistance - atr_value * 0.35).sum())
        rejections = int(
            ((high >= resistance - atr_value * 0.25) & (close < resistance - atr_value * 0.15)).sum()
        )
        score = min(1.0, hits / 8.0) * 0.35 + min(1.0, rejections / 6.0) * 0.45
        wick_ratio = ((high - close) / (high - tail["low"].astype(float)).replace(0, 1e-9)).mean()
        if float(wick_ratio) > 0.45:
            score += 0.15
        return max(0.0, min(1.0, score))

    @staticmethod
    def _institutional_rotation(
        frame: pd.DataFrame, support: float, resistance: float, atr_value: float
    ) -> float:
        if "tick_volume" not in frame.columns or len(frame) < 40:
            return 0.0
        volume = frame["tick_volume"].astype(float)
        close = frame["close"].astype(float)
        early = frame.iloc[: len(frame) // 2]
        late = frame.iloc[len(frame) // 2 :]
        early_vol = float(early["tick_volume"].astype(float).mean())
        late_vol = float(late["tick_volume"].astype(float).mean())
        early_mid = (float(early["high"].max()) + float(early["low"].min())) / 2
        late_mid = (float(late["high"].max()) + float(late["low"].min())) / 2
        vol_shift = abs(late_vol - early_vol) / max(early_vol, 1.0)
        price_shift = abs(late_mid - early_mid) / atr_value
        score = min(1.0, vol_shift * 0.4 + min(price_shift, 2.0) / 2.0 * 0.35)
        if float(close.iloc[-1]) > resistance - atr_value and late_vol > early_vol * 1.1:
            score += 0.15
        if float(close.iloc[-1]) < support + atr_value and late_vol > early_vol * 1.1:
            score += 0.15
        return max(0.0, min(1.0, score))

    @staticmethod
    def _accumulation_score(
        frame: pd.DataFrame,
        support: float,
        equilibrium: float,
        absorption: float,
        progress: float,
    ) -> float:
        close = float(frame["close"].iloc[-1])
        in_range = abs(close - equilibrium) / max(equilibrium, 1e-9) < 0.008
        return max(
            0.0,
            min(1.0, absorption * 0.45 + (0.25 if in_range else 0.0) + (0.20 if abs(progress) < 1.5 else 0.0)),
        )

    @staticmethod
    def _markup_score(
        progress: float, participation: float, absorption: float, exhaustion: float
    ) -> float:
        if progress <= 1.0:
            return 0.0
        return max(
            0.0,
            min(1.0, min(progress / 6.0, 0.45) + participation * 0.30 + absorption * 0.15 - exhaustion * 0.20),
        )

    @staticmethod
    def _distribution_score(
        frame: pd.DataFrame,
        resistance: float,
        equilibrium: float,
        exhaustion: float,
        progress: float,
    ) -> float:
        close = float(frame["close"].iloc[-1])
        near_top = close >= resistance * 0.998 if resistance > 0 else False
        return max(
            0.0,
            min(1.0, exhaustion * 0.50 + (0.25 if near_top else 0.0) + (0.15 if progress > 2.0 else 0.0)),
        )

    @staticmethod
    def _markdown_score(
        progress: float, participation: float, exhaustion: float, rotation: float
    ) -> float:
        if progress >= -1.0:
            return 0.0
        return max(
            0.0,
            min(1.0, min(abs(progress) / 6.0, 0.45) + participation * 0.20 + rotation * 0.20),
        )

    @staticmethod
    def _dominant_institutional(
        absorption: float, exhaustion: float, rotation: float
    ) -> InstitutionalSignal:
        scores = {
            "absorption": absorption,
            "exhaustion": exhaustion,
            "institutional_rotation": rotation,
        }
        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        if scores[best] < 0.25:  # type: ignore[index]
            return "none"
        return best  # type: ignore[return-value]

    @staticmethod
    def _evidence(
        phase: str,
        absorption: float,
        exhaustion: float,
        rotation: float,
        progress: float,
    ) -> list[str]:
        evidence: list[str] = []
        if absorption >= 0.35:
            evidence.append(f"absorption at support ({absorption:.0%})")
        if exhaustion >= 0.35:
            evidence.append(f"selling exhaustion at resistance ({exhaustion:.0%})")
        if rotation >= 0.35:
            evidence.append(f"institutional rotation ({rotation:.0%})")
        evidence.append(f"net progress {progress:.1f} ATR")
        evidence.append(f"dominant phase: {phase}")
        return evidence

    @staticmethod
    def _trade_opportunity(phase: str, institutional: InstitutionalSignal) -> str:
        mapping = {
            "accumulation": "Scout longs near support — spring and reclaim setups",
            "markup": "Trend continuation and pullback entries with trend",
            "distribution": "Fade failed highs or prepare reversal shorts",
            "markdown": "Trend shorts and rally fades in downtrend",
            "unclear": "Range scout — trade boundaries until phase clarifies",
        }
        base = mapping.get(phase, mapping["unclear"])
        if institutional == "absorption":
            return f"{base} | absorption favours dip-buying"
        if institutional == "exhaustion":
            return f"{base} | exhaustion favours fade/reversal"
        if institutional == "institutional_rotation":
            return f"{base} | rotation favours new directional bias"
        return base


__all__ = [
    "DistributionAccumulationConfig",
    "DistributionAccumulationEngine",
    "DistributionAccumulationEngineError",
    "DistributionAccumulationResult",
    "InstitutionalSignal",
    "WyckoffPhase",
]
