"""
Market regime detector for Kraitos.

Classifies market conditions using ATR, moving-average slope, candle size,
volatility compression, and spread.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from loguru import logger

from strategies.models import MarketRegime, RegimeResult

REQUIRED_COLUMNS = ("time", "open", "high", "low", "close", "tick_volume", "spread")


@dataclass(frozen=True)
class RegimeDetectorConfig:
    """Thresholds and periods for regime detection."""

    atr_period: int = 14
    atr_long_period: int = 50
    ma_period: int = 20
    ma_slope_lookback: int = 5
    min_candles: int = 60
    spread_limit: float = 2.0
    trending_slope_threshold: float = 0.00012
    ranging_slope_threshold: float = 0.00004
    volatile_atr_ratio: float = 1.35
    compression_atr_ratio: float = 0.75
    candle_expansion_ratio: float = 1.45
    low_volume_ratio: float = 0.55
    wide_spread_ratio: float = 1.4
    news_atr_spike_ratio: float = 1.9
    news_candle_expansion_ratio: float = 1.8


class RegimeDetectorError(Exception):
    """Raised when candle input is invalid for regime detection."""


class RegimeDetector:
    """Classify the current market regime from OHLCV candle data."""

    def __init__(self, config: RegimeDetectorConfig | None = None) -> None:
        self.config = config or RegimeDetectorConfig()

    def detect(
        self,
        candles: pd.DataFrame,
        *,
        spread_limit: float | None = None,
        news_risk_active: bool = False,
    ) -> RegimeResult:
        """
        Classify market condition from historical candles.

        Args:
            candles: OHLCV DataFrame with spread and tick_volume.
            spread_limit: Optional per-symbol spread limit in pips/points.
            news_risk_active: External flag when a high-impact news window is active.

        Returns:
            RegimeResult with regime, confidence, and reason.
        """
        frame = self._prepare_candles(candles)
        limit = spread_limit if spread_limit is not None else self.config.spread_limit
        features = self._compute_features(frame, spread_limit=limit)

        if news_risk_active:
            return RegimeResult(
                regime="news_risk",
                confidence=0.95,
                reason="High-impact news window is active",
            )

        scores = self._score_regimes(features, limit)
        regime, confidence, reason = self._select_regime(scores, features, limit)

        logger.debug(
            f"Regime detected: {regime} (confidence={confidence:.2f}) - {reason}"
        )
        return RegimeResult(regime=regime, confidence=confidence, reason=reason)

    def _prepare_candles(self, candles: pd.DataFrame) -> pd.DataFrame:
        if candles is None or candles.empty:
            raise RegimeDetectorError("Candle data is empty")

        missing = [column for column in REQUIRED_COLUMNS if column not in candles.columns]
        if missing:
            raise RegimeDetectorError(
                f"Candle data missing columns: {', '.join(missing)}"
            )

        frame = candles.copy()
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frame = frame.dropna(subset=["open", "high", "low", "close"])
        frame = frame.sort_values("time").reset_index(drop=True)

        if len(frame) < self.config.min_candles:
            raise RegimeDetectorError(
                f"At least {self.config.min_candles} candles are required, got {len(frame)}"
            )
        return frame

    def _compute_features(
        self,
        frame: pd.DataFrame,
        *,
        spread_limit: float | None = None,
    ) -> dict[str, float]:
        cfg = self.config
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        close = frame["close"].astype(float)
        open_ = frame["open"].astype(float)

        prev_close = close.shift(1)
        true_range = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = true_range.rolling(cfg.atr_period).mean()
        atr_long = true_range.rolling(cfg.atr_long_period).mean()

        ma = close.rolling(cfg.ma_period).mean()
        slope_lookback = cfg.ma_slope_lookback
        ma_slope = (ma.iloc[-1] - ma.iloc[-1 - slope_lookback]) / (
            ma.iloc[-1 - slope_lookback] * slope_lookback
        )

        candle_range = high - low
        candle_body = (close - open_).abs()
        avg_range = candle_range.rolling(cfg.atr_period).mean()
        avg_body = candle_body.rolling(cfg.atr_period).mean()

        current_atr = float(atr.iloc[-1])
        baseline_atr = float(atr_long.iloc[-1])
        atr_ratio = current_atr / baseline_atr if baseline_atr > 0 else 1.0
        compression_ratio = current_atr / baseline_atr if baseline_atr > 0 else 1.0

        current_range = float(candle_range.iloc[-1])
        mean_range = float(avg_range.iloc[-1])
        candle_expansion = current_range / mean_range if mean_range > 0 else 1.0

        current_body = float(candle_body.iloc[-1])
        mean_body = float(avg_body.iloc[-1])
        body_expansion = current_body / mean_body if mean_body > 0 else 1.0

        current_volume = float(frame["tick_volume"].iloc[-1])
        mean_volume = float(frame["tick_volume"].rolling(cfg.atr_period).mean().iloc[-1])
        volume_ratio = current_volume / mean_volume if mean_volume > 0 else 1.0

        current_spread = float(frame["spread"].iloc[-1])
        mean_spread = float(frame["spread"].rolling(cfg.atr_period).mean().iloc[-1])
        limit = spread_limit if spread_limit is not None else cfg.spread_limit
        spread_to_limit = current_spread / limit if limit > 0 else 1.0
        spread_to_average = current_spread / mean_spread if mean_spread > 0 else 1.0

        return {
            "ma_slope": float(abs(ma_slope)),
            "ma_slope_signed": float(ma_slope),
            "atr_ratio": float(atr_ratio),
            "compression_ratio": float(compression_ratio),
            "candle_expansion": float(candle_expansion),
            "body_expansion": float(body_expansion),
            "volume_ratio": float(volume_ratio),
            "spread_to_limit": float(spread_to_limit),
            "spread_to_average": float(spread_to_average),
            "current_spread": current_spread,
        }

    def _score_regimes(self, features: dict[str, float], spread_limit: float) -> dict[MarketRegime, float]:
        cfg = self.config
        slope = features["ma_slope"]
        atr_ratio = features["atr_ratio"]
        compression = features["compression_ratio"]
        candle_expansion = features["candle_expansion"]
        volume_ratio = features["volume_ratio"]
        spread_to_limit = features["spread_to_limit"]
        spread_to_average = features["spread_to_average"]

        trending_score = 0.0
        if slope >= cfg.trending_slope_threshold:
            trending_score += min(1.0, slope / cfg.trending_slope_threshold) * 0.5
        if cfg.compression_atr_ratio <= atr_ratio <= cfg.volatile_atr_ratio:
            trending_score += 0.25
        if candle_expansion < cfg.candle_expansion_ratio:
            trending_score += 0.25

        ranging_score = 0.0
        if slope <= cfg.ranging_slope_threshold:
            ranging_score += min(1.0, 1 - slope / cfg.ranging_slope_threshold) * 0.45
        if compression <= cfg.compression_atr_ratio:
            ranging_score += min(1.0, (cfg.compression_atr_ratio - compression) / 0.25) * 0.35
        if candle_expansion < cfg.candle_expansion_ratio:
            ranging_score += 0.2

        volatile_score = 0.0
        if atr_ratio >= cfg.volatile_atr_ratio:
            volatile_score += min(1.0, atr_ratio / cfg.volatile_atr_ratio) * 0.45
        if candle_expansion >= cfg.candle_expansion_ratio:
            volatile_score += min(1.0, candle_expansion / cfg.candle_expansion_ratio) * 0.35
        if features["body_expansion"] >= cfg.candle_expansion_ratio:
            volatile_score += 0.2

        low_liquidity_score = 0.0
        if volume_ratio <= cfg.low_volume_ratio:
            low_liquidity_score += min(1.0, (cfg.low_volume_ratio - volume_ratio) / 0.3) * 0.45
        if spread_to_limit >= 1.0 or spread_to_average >= cfg.wide_spread_ratio:
            low_liquidity_score += 0.35
        if spread_to_average >= cfg.wide_spread_ratio:
            low_liquidity_score += min(1.0, spread_to_average / cfg.wide_spread_ratio) * 0.2

        news_risk_score = 0.0
        if atr_ratio >= cfg.news_atr_spike_ratio:
            news_risk_score += min(1.0, atr_ratio / cfg.news_atr_spike_ratio) * 0.5
        if candle_expansion >= cfg.news_candle_expansion_ratio:
            news_risk_score += min(1.0, candle_expansion / cfg.news_candle_expansion_ratio) * 0.5

        unclear_score = 0.1
        regime_scores = [
            trending_score,
            ranging_score,
            volatile_score,
            low_liquidity_score,
            news_risk_score,
        ]
        top_scores = sorted(regime_scores, reverse=True)
        if top_scores[0] < 0.35 and len(top_scores) >= 2 and (top_scores[0] - top_scores[1]) < 0.15:
            unclear_score += 0.45

        if spread_to_limit >= 1.0:
            low_liquidity_score = max(low_liquidity_score, 0.85)
        if slope <= cfg.ranging_slope_threshold and compression <= cfg.compression_atr_ratio:
            ranging_score = max(ranging_score, 0.75)

        return {
            "trending": trending_score,
            "ranging": ranging_score,
            "volatile": volatile_score,
            "low_liquidity": low_liquidity_score,
            "news_risk": news_risk_score,
            "unclear": unclear_score,
        }

    def _select_regime(
        self,
        scores: dict[MarketRegime, float],
        features: dict[str, float],
        spread_limit: float,
    ) -> tuple[MarketRegime, float, str]:
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        regime, top_score = ordered[0]
        second_score = ordered[1][1] if len(ordered) > 1 else 0.0

        confidence = self._calculate_confidence(top_score, second_score)
        reason = self._build_reason(regime, features, spread_limit)
        return regime, confidence, reason

    @staticmethod
    def _calculate_confidence(top_score: float, second_score: float) -> float:
        margin = max(0.0, top_score - second_score)
        raw = min(1.0, top_score * 0.65 + margin * 0.35)
        return round(max(0.35, min(0.99, raw)), 2)

    def _build_reason(
        self,
        regime: MarketRegime,
        features: dict[str, float],
        spread_limit: float,
    ) -> str:
        slope = features["ma_slope"]
        atr_ratio = features["atr_ratio"]
        compression = features["compression_ratio"]
        candle_expansion = features["candle_expansion"]
        volume_ratio = features["volume_ratio"]
        spread = features["current_spread"]

        if regime == "trending":
            direction = "up" if features["ma_slope_signed"] >= 0 else "down"
            return (
                f"Moving average slope is {direction} ({slope:.6f}) with stable volatility "
                f"(ATR ratio {atr_ratio:.2f})"
            )
        if regime == "ranging":
            return (
                f"Flat MA slope ({slope:.6f}) and compressed volatility "
                f"(ATR ratio {compression:.2f})"
            )
        if regime == "volatile":
            return (
                f"Expanded volatility (ATR ratio {atr_ratio:.2f}) and enlarged candles "
                f"(range expansion {candle_expansion:.2f})"
            )
        if regime == "low_liquidity":
            return (
                f"Weak volume ({volume_ratio:.2f} of average) and wide spread "
                f"({spread:.2f} vs limit {spread_limit:.2f})"
            )
        if regime == "news_risk":
            return (
                f"Volatility spike (ATR ratio {atr_ratio:.2f}) with sudden candle expansion "
                f"({candle_expansion:.2f})"
            )
        return (
            f"Mixed signals: slope {slope:.6f}, ATR ratio {atr_ratio:.2f}, "
            f"candle expansion {candle_expansion:.2f}"
        )
