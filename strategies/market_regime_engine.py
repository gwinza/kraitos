"""Rich market regime detection for thesis-first trading."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import pandas as pd

from strategies.range_intelligence_engine import RangeIntelligenceEngine, RangeIntelligenceResult

MarketRegimeLabel = Literal[
    "strong_uptrend",
    "strong_downtrend",
    "healthy_uptrend",
    "healthy_downtrend",
    "mature_uptrend",
    "mature_downtrend",
    "ranging_market",
    "compression",
    "breakout_preparation",
    "breakout_in_progress",
    "accumulation",
    "distribution",
    "transition",
    "unclear",
]

PrimaryRegime = Literal[
    "trending",
    "ranging",
    "breakout",
    "mean_reversion",
    "compression",
    "chaos",
]

REQUIRED_COLUMNS = ("open", "high", "low", "close", "tick_volume", "spread")


@dataclass(frozen=True)
class MarketRegimeResult:
    market_regime: MarketRegimeLabel
    primary_regime: PrimaryRegime
    confidence: float
    explanation: str
    evidence: tuple[str, ...]
    compression_probability: float
    breakout_preparation_score: int
    range_quality_score: int
    regime_confidence: float
    trend_strength_score: int
    breakout_quality_score: int
    false_breakout_probability: float
    likely_breakout_direction: str
    likely_next_regime: str
    strategy_bias: str
    trade_opportunity: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["evidence"] = tuple(self.evidence)
        return data


@dataclass(frozen=True)
class MarketRegimeEngineConfig:
    min_candles: int = 80
    lookback: int = 120
    atr_period: int = 14


class MarketRegimeEngineError(Exception):
    pass


class MarketRegimeEngine:
    """Classify trend/range/compression/breakout environments before trade logic."""

    def __init__(
        self,
        config: MarketRegimeEngineConfig | None = None,
        range_engine: RangeIntelligenceEngine | None = None,
    ) -> None:
        self.config = config or MarketRegimeEngineConfig()
        self._range_engine = range_engine or RangeIntelligenceEngine()

    def analyze(
        self,
        candles: pd.DataFrame,
        *,
        symbol: str = "",
        range_intelligence: RangeIntelligenceResult | None = None,
    ) -> MarketRegimeResult:
        frame = self._prepare(candles).tail(self.config.lookback)
        range_result = range_intelligence or self._range_engine.analyze(frame, symbol=symbol)
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        close = frame["close"].astype(float)
        open_ = frame["open"].astype(float)
        volume = frame["tick_volume"].astype(float)
        atr = self._atr(frame)
        atr_now = float(atr.iloc[-1]) or float((high - low).median()) or 1.0
        atr_baseline = float(atr.rolling(50, min_periods=10).mean().iloc[-1]) or atr_now
        atr_ratio = atr_now / atr_baseline if atr_baseline > 0 else 1.0

        trend = self._trend_features(frame, atr_now)
        compression_probability = self._compression_probability(frame, atr, atr_now)
        breakout_quality, false_breakout_probability, breakout_evidence = self._breakout_quality(
            frame, range_result, atr_now
        )
        breakout_preparation = self._breakout_preparation_score(
            range_result,
            compression_probability=compression_probability,
            frame_len=len(frame),
        )
        accumulation_score, distribution_score, ad_evidence = self._accumulation_distribution(
            frame, range_result, atr_now
        )

        evidence = list(trend["evidence"])
        evidence.extend(range_result.evidence)
        evidence.extend(breakout_evidence)
        evidence.extend(ad_evidence)
        if compression_probability >= 0.55:
            evidence.append(f"compression probability {compression_probability:.0%}")
        if breakout_preparation >= 60:
            evidence.append(f"breakout preparation score {breakout_preparation}/100")

        regime = self._select_regime(
            trend_direction=str(trend["direction"]),
            trend_strength=float(trend["strength"]),
            trend_maturity=float(trend["maturity"]),
            range_quality=range_result.range_quality_score,
            compression_probability=compression_probability,
            breakout_preparation=breakout_preparation,
            breakout_quality=breakout_quality,
            accumulation_score=accumulation_score,
            distribution_score=distribution_score,
            atr_ratio=atr_ratio,
        )
        confidence = self._confidence(
            regime,
            trend_strength=float(trend["strength"]),
            range_quality=range_result.range_quality_score,
            compression_probability=compression_probability,
            breakout_quality=breakout_quality,
            accumulation_score=accumulation_score,
            distribution_score=distribution_score,
        )
        likely_next = self._likely_next_regime(
            regime,
            breakout_preparation=breakout_preparation,
            compression_probability=compression_probability,
            likely_breakout_direction=range_result.likely_breakout_direction,
        )
        strategy_bias = self._strategy_bias(regime)
        primary_regime = self._primary_regime(
            regime=regime,
            trend_strength=float(trend["strength"]),
            range_quality=range_result.range_quality_score,
            compression_probability=compression_probability,
            breakout_quality=breakout_quality,
            atr_ratio=atr_ratio,
            accumulation_score=accumulation_score,
            distribution_score=distribution_score,
        )
        trade_opportunity = self._trade_opportunity(primary_regime, regime, strategy_bias)
        explanation = (
            f"Market regime {regime} / {primary_regime} ({confidence:.0%}): trend strength "
            f"{int(round(float(trend['strength']) * 100))}/100, range quality "
            f"{range_result.range_quality_score}/100, compression "
            f"{compression_probability:.0%}, breakout prep {breakout_preparation}/100. "
            f"Opportunity: {trade_opportunity}"
        )
        return MarketRegimeResult(
            market_regime=regime,
            primary_regime=primary_regime,
            confidence=confidence,
            explanation=explanation,
            evidence=tuple(evidence),
            compression_probability=round(compression_probability, 4),
            breakout_preparation_score=breakout_preparation,
            range_quality_score=range_result.range_quality_score,
            regime_confidence=confidence,
            trend_strength_score=int(round(float(trend["strength"]) * 100)),
            breakout_quality_score=breakout_quality,
            false_breakout_probability=round(false_breakout_probability, 4),
            likely_breakout_direction=range_result.likely_breakout_direction,
            likely_next_regime=likely_next,
            strategy_bias=strategy_bias,
            trade_opportunity=trade_opportunity,
        )

    def _prepare(self, candles: pd.DataFrame) -> pd.DataFrame:
        if candles is None or candles.empty:
            raise MarketRegimeEngineError("candle data is empty")
        missing = [column for column in REQUIRED_COLUMNS if column not in candles.columns]
        if missing:
            raise MarketRegimeEngineError(f"missing columns: {', '.join(missing)}")
        frame = candles.copy()
        if "time" in frame.columns:
            frame["time"] = pd.to_datetime(frame["time"], utc=True)
            frame = frame.sort_values("time")
        frame = frame.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        if len(frame) < self.config.min_candles:
            raise MarketRegimeEngineError(f"need at least {self.config.min_candles} candles")
        return frame

    def _atr(self, frame: pd.DataFrame) -> pd.Series:
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        close = frame["close"].astype(float)
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        return tr.rolling(self.config.atr_period, min_periods=3).mean().bfill()

    def _trend_features(self, frame: pd.DataFrame, atr_now: float) -> dict[str, object]:
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        close = frame["close"].astype(float)
        early = close.iloc[: len(close) // 2]
        late = close.iloc[len(close) // 2 :]
        progress = (close.iloc[-1] - close.iloc[0]) / atr_now
        persistence = abs(float((close.diff().tail(30) > 0).mean()) - 0.5) * 2.0
        acceleration = abs((late.iloc[-1] - late.iloc[0]) / atr_now) > abs((early.iloc[-1] - early.iloc[0]) / atr_now)
        higher_highs = high.iloc[-1] > high.iloc[: len(high) // 2].max()
        higher_lows = low.iloc[-1] > low.iloc[: len(low) // 2].min()
        lower_highs = high.iloc[-1] < high.iloc[: len(high) // 2].max()
        lower_lows = low.iloc[-1] < low.iloc[: len(low) // 2].min()
        direction = "up" if progress > 1.2 else "down" if progress < -1.2 else "neutral"
        structure_score = 0.0
        evidence: list[str] = []
        if higher_highs:
            structure_score += 0.2
            evidence.append("higher highs")
        if higher_lows:
            structure_score += 0.2
            evidence.append("higher lows")
        if lower_highs:
            structure_score += 0.2
            evidence.append("lower highs")
        if lower_lows:
            structure_score += 0.2
            evidence.append("lower lows")
        if direction == "up":
            structure_score = (0.25 if higher_highs else 0.0) + (0.25 if higher_lows else 0.0)
        elif direction == "down":
            structure_score = (0.25 if lower_highs else 0.0) + (0.25 if lower_lows else 0.0)
        strength = max(0.0, min(1.0, abs(progress) / 8.0 * 0.45 + persistence * 0.30 + structure_score + (0.10 if acceleration else 0.0)))
        maturity = max(0.0, min(1.0, abs(progress) / 10.0 + (0.20 if not acceleration and strength > 0.55 else 0.0)))
        if acceleration:
            evidence.append("trend acceleration")
        elif strength > 0.55:
            evidence.append("trend deterioration or maturation")
        return {"direction": direction, "strength": strength, "maturity": maturity, "evidence": tuple(evidence)}

    @staticmethod
    def _compression_probability(frame: pd.DataFrame, atr: pd.Series, atr_now: float) -> float:
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        close = frame["close"].astype(float)
        range_now = float((high - low).tail(20).mean())
        range_prev = float((high - low).iloc[-60:-20].mean()) if len(frame) >= 60 else range_now
        atr_mean = float(atr.rolling(50, min_periods=10).mean().iloc[-1]) or atr_now
        bb_mid = close.rolling(20, min_periods=5).mean()
        bb_std = close.rolling(20, min_periods=5).std().bfill()
        bb_width = ((bb_mid + 2 * bb_std) - (bb_mid - 2 * bb_std)).iloc[-1]
        bb_base = (((bb_mid + 2 * bb_std) - (bb_mid - 2 * bb_std)).rolling(50, min_periods=10).mean().iloc[-1]) or bb_width
        atr_compress = max(0.0, min(1.0, 1.0 - atr_now / max(atr_mean, 1e-9)))
        range_compress = max(0.0, min(1.0, 1.0 - range_now / max(range_prev, 1e-9)))
        bb_compress = max(0.0, min(1.0, 1.0 - float(bb_width) / max(float(bb_base), 1e-9)))
        return round(0.40 * atr_compress + 0.30 * range_compress + 0.30 * bb_compress, 4)

    @staticmethod
    def _breakout_quality(
        frame: pd.DataFrame,
        range_result: RangeIntelligenceResult,
        atr_now: float,
    ) -> tuple[int, float, tuple[str, ...]]:
        close = frame["close"].astype(float)
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        volume = frame["tick_volume"].astype(float)
        resistance = range_result.resistance_level
        support = range_result.support_level
        broke_up = close.iloc[-1] > resistance
        broke_down = close.iloc[-1] < support
        volume_ratio = float(volume.iloc[-1] / max(volume.rolling(20, min_periods=5).mean().iloc[-1], 1.0))
        follow = abs(close.iloc[-1] - close.iloc[-4]) / atr_now
        immediate_reject = (broke_up and low.iloc[-1] < resistance) or (broke_down and high.iloc[-1] > support)
        evidence: list[str] = []
        if broke_up or broke_down:
            evidence.append("structure breaks range boundary")
            if volume_ratio >= 1.05:
                evidence.append("volume supports breakout")
            if follow >= 0.75:
                evidence.append("breakout follow-through")
            if immediate_reject:
                evidence.append("immediate rejection after break")
            quality = max(0.0, min(1.0, 0.35 + 0.20 * volume_ratio + 0.20 * follow - (0.35 if immediate_reject else 0.0)))
            false_prob = max(0.0, min(1.0, 0.25 + (0.40 if immediate_reject else 0.0) + (0.20 if volume_ratio < 0.9 else 0.0) - 0.15 * follow))
            return int(round(quality * 100)), false_prob, tuple(evidence)
        false_up = high.iloc[-1] > resistance and close.iloc[-1] < resistance
        false_down = low.iloc[-1] < support and close.iloc[-1] > support
        if false_up or false_down:
            evidence.append("false breakout and return into range")
            return 28, 0.76, tuple(evidence)
        return 45, 0.25, tuple(evidence)

    @staticmethod
    def _breakout_preparation_score(
        range_result: RangeIntelligenceResult,
        *,
        compression_probability: float,
        frame_len: int,
    ) -> int:
        duration = min(1.0, frame_len / 140.0)
        score = 0.35 * (range_result.range_quality_score / 100.0) + 0.35 * compression_probability + 0.20 * (range_result.breakout_risk_score / 100.0) + 0.10 * duration
        return int(round(max(0.0, min(1.0, score)) * 100))

    @staticmethod
    def _accumulation_distribution(
        frame: pd.DataFrame,
        range_result: RangeIntelligenceResult,
        atr_now: float,
    ) -> tuple[float, float, tuple[str, ...]]:
        close = frame["close"].astype(float)
        volume = frame["tick_volume"].astype(float)
        low = frame["low"].astype(float)
        high = frame["high"].astype(float)
        lower_rejections = int(((low <= range_result.support_level + atr_now * 0.4) & (close > range_result.equilibrium_zone)).sum())
        upper_rejections = int(((high >= range_result.resistance_level - atr_now * 0.4) & (close < range_result.equilibrium_zone)).sum())
        volume_rising = volume.tail(20).mean() > volume.iloc[-60:-20].mean() if len(volume) >= 60 else False
        accumulation = min(1.0, lower_rejections / 8.0 + (0.15 if volume_rising else 0.0))
        distribution = min(1.0, upper_rejections / 8.0 + (0.15 if volume_rising else 0.0))
        evidence: list[str] = []
        if accumulation >= 0.45:
            evidence.append("accumulation evidence near support")
        if distribution >= 0.45:
            evidence.append("distribution evidence near resistance")
        return accumulation, distribution, tuple(evidence)

    @staticmethod
    def _select_regime(
        *,
        trend_direction: str,
        trend_strength: float,
        trend_maturity: float,
        range_quality: int,
        compression_probability: float,
        breakout_preparation: int,
        breakout_quality: int,
        accumulation_score: float,
        distribution_score: float,
        atr_ratio: float,
    ) -> MarketRegimeLabel:
        if breakout_quality >= 78 and trend_strength < 0.70:
            return "breakout_in_progress"
        if breakout_preparation >= 55 and compression_probability >= 0.25:
            return "breakout_preparation"
        if accumulation_score >= 0.62 and range_quality >= 45:
            return "accumulation"
        if distribution_score >= 0.62 and range_quality >= 45:
            return "distribution"
        if compression_probability >= 0.58:
            return "compression"
        if range_quality >= 62 and trend_strength < 0.55:
            return "ranging_market"
        if trend_strength >= 0.72 and trend_direction == "up":
            return "mature_uptrend" if trend_maturity >= 0.75 else "strong_uptrend"
        if trend_strength >= 0.72 and trend_direction == "down":
            return "mature_downtrend" if trend_maturity >= 0.75 else "strong_downtrend"
        if trend_strength >= 0.50 and trend_direction == "up":
            return "healthy_uptrend"
        if trend_strength >= 0.50 and trend_direction == "down":
            return "healthy_downtrend"
        if range_quality >= 45 and trend_strength >= 0.45:
            return "transition"
        if atr_ratio > 1.4 and trend_strength < 0.40:
            return "transition"
        return "unclear"

    @staticmethod
    def _confidence(
        regime: str,
        *,
        trend_strength: float,
        range_quality: int,
        compression_probability: float,
        breakout_quality: int,
        accumulation_score: float,
        distribution_score: float,
    ) -> float:
        if "trend" in regime:
            base = trend_strength
        elif regime == "ranging_market":
            base = range_quality / 100.0
        elif regime == "compression":
            base = compression_probability
        elif regime == "breakout_in_progress":
            base = breakout_quality / 100.0
        elif regime == "accumulation":
            base = accumulation_score
        elif regime == "distribution":
            base = distribution_score
        elif regime == "breakout_preparation":
            base = max(compression_probability, range_quality / 100.0)
        else:
            base = 0.42
        return round(max(0.35, min(0.96, base)), 4)

    @staticmethod
    def _likely_next_regime(
        regime: str,
        *,
        breakout_preparation: int,
        compression_probability: float,
        likely_breakout_direction: str,
    ) -> str:
        if regime in {"compression", "breakout_preparation", "ranging_market"} and breakout_preparation >= 55:
            return f"breakout_{likely_breakout_direction}" if likely_breakout_direction != "neutral" else "breakout"
        if regime in {"mature_uptrend", "distribution"}:
            return "transition_or_downside_break"
        if regime in {"mature_downtrend", "accumulation"}:
            return "transition_or_upside_break"
        if compression_probability >= 0.55:
            return "breakout_preparation"
        return "continuation"

    @staticmethod
    def _primary_regime(
        *,
        regime: str,
        trend_strength: float,
        range_quality: int,
        compression_probability: float,
        breakout_quality: int,
        atr_ratio: float,
        accumulation_score: float,
        distribution_score: float,
    ) -> PrimaryRegime:
        if regime in {"breakout_in_progress", "breakout_preparation"} or breakout_quality >= 70:
            return "breakout"
        if compression_probability >= 0.55 or regime == "compression":
            return "compression"
        if atr_ratio > 1.45 and trend_strength < 0.40:
            return "chaos"
        if regime in {"strong_uptrend", "strong_downtrend", "healthy_uptrend", "healthy_downtrend", "mature_uptrend", "mature_downtrend"}:
            return "trending"
        if regime == "ranging_market" or (range_quality >= 55 and trend_strength < 0.50):
            return "ranging"
        if accumulation_score >= 0.50 or distribution_score >= 0.50:
            return "mean_reversion"
        if trend_strength >= 0.50:
            return "trending"
        if range_quality >= 45:
            return "ranging"
        return "chaos"

    @staticmethod
    def _trade_opportunity(primary: PrimaryRegime, regime: str, strategy_bias: str) -> str:
        opportunities = {
            "trending": "Trade pullbacks and continuations with the dominant trend",
            "ranging": "Fade range extremes and scout breakout preparation",
            "breakout": "Enter on confirmed break/retest or momentum continuation",
            "mean_reversion": "Fade extensions back toward equilibrium — snapback setups",
            "compression": "Prepare for expansion — bracket orders or scout breakout direction",
            "chaos": "Reduce size, scout micro edges — volatility offers scalp opportunities",
        }
        detail = opportunities[primary]
        if regime == "accumulation":
            detail = "Accumulation — scout longs on support absorption and spring setups"
        elif regime == "distribution":
            detail = "Distribution — scout shorts on failed highs and exhaustion fades"
        elif regime == "transition":
            detail = "Transition — adaptive scout both directions until new regime forms"
        elif regime == "unclear":
            detail = "Unclear — probe both range boundaries with reduced size"
        return f"{detail} | strategy: {strategy_bias}"

    @staticmethod
    def _strategy_bias(regime: str) -> str:
        if regime in {"strong_uptrend", "strong_downtrend"}:
            return "trend_continuation"
        if regime in {"healthy_uptrend", "healthy_downtrend"}:
            return "pullback"
        if regime in {"mature_uptrend", "mature_downtrend"}:
            return "reduced_risk_trend"
        if regime == "ranging_market":
            return "range_logic"
        if regime in {"compression", "breakout_preparation"}:
            return "prepare_breakout"
        if regime == "breakout_in_progress":
            return "breakout_logic"
        if regime == "distribution":
            return "fade_exhaustion"
        if regime == "accumulation":
            return "support_absorption"
        if regime == "transition":
            return "adaptive_scout"
        return "boundary_scout"


__all__ = [
    "MarketRegimeEngine",
    "MarketRegimeEngineConfig",
    "MarketRegimeEngineError",
    "MarketRegimeLabel",
    "MarketRegimeResult",
    "PrimaryRegime",
]
