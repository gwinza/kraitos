"""
Multi-timeframe bias analyzer for Kraitos.

Combines directional bias across six timeframes with role-specific weights:
- H8 / H4: macro bias
- H1: structure confirmation
- M15 / M5: setup quality
- M1: precision entry
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from loguru import logger

from strategies.models import MarketBias, MultiTimeframeBiasResult, TimeframeBiasDetail

REQUIRED_COLUMNS = ("time", "open", "high", "low", "close", "tick_volume", "spread")

TIMEFRAME_ROLES: dict[str, str] = {
    "H8": "macro",
    "H4": "macro",
    "H1": "structure",
    "M15": "setup",
    "M5": "setup",
    "M1": "precision_entry",
}

TIMEFRAME_WEIGHTS: dict[str, float] = {
    "H8": 0.20,
    "H4": 0.20,
    "H1": 0.25,
    "M15": 0.10,
    "M5": 0.10,
    "M1": 0.15,
}

REQUIRED_TIMEFRAMES: tuple[str, ...] = tuple(TIMEFRAME_WEIGHTS.keys())

MIN_CANDLES_BY_TIMEFRAME: dict[str, int] = {
    "H8": 25,
    "H4": 30,
    "H1": 40,
    "M15": 50,
    "M5": 50,
    "M1": 60,
}


@dataclass(frozen=True)
class MultiTimeframeBiasConfig:
    """Thresholds for classifying timeframe and aggregate bias."""

    ma_period: int = 20
    slope_lookback: int = 5
    momentum_lookback: int = 10
    structure_lookback: int = 10
    bullish_threshold: float = 0.12
    bearish_threshold: float = -0.12
    timeframe_neutral_band: float = 0.08


class MultiTimeframeBiasError(Exception):
    """Raised when multi-timeframe input is invalid."""


class MultiTimeframeBiasAnalyzer:
    """Derive directional bias from aligned multi-timeframe candle data."""

    def __init__(self, config: MultiTimeframeBiasConfig | None = None) -> None:
        self.config = config or MultiTimeframeBiasConfig()

    def evaluate(
        self,
        candles_by_timeframe: dict[str, pd.DataFrame],
    ) -> MultiTimeframeBiasResult:
        """
        Evaluate bullish/bearish/neutral bias across all required timeframes.

        Args:
            candles_by_timeframe: Mapping of timeframe -> OHLCV DataFrame.

        Returns:
            MultiTimeframeBiasResult with bias, confidence, and explanation.
        """
        self._validate_inputs(candles_by_timeframe)

        layer_details: list[TimeframeBiasDetail] = []
        weighted_scores: dict[str, float] = {}

        for timeframe in REQUIRED_TIMEFRAMES:
            frame = self._prepare_candles(
                candles_by_timeframe[timeframe],
                MIN_CANDLES_BY_TIMEFRAME[timeframe],
                timeframe,
            )
            score = self._timeframe_score(frame)
            layer_bias = self._score_to_bias(score)
            layer_details.append(
                TimeframeBiasDetail(
                    timeframe=timeframe,
                    bias=layer_bias,
                    score=round(score, 4),
                    role=TIMEFRAME_ROLES[timeframe],
                )
            )
            weighted_scores[timeframe] = score * TIMEFRAME_WEIGHTS[timeframe]

        aggregate_score = sum(weighted_scores.values())
        layer_bias_set = {layer.bias for layer in layer_details}
        if layer_bias_set == {"neutral"}:
            bias: MarketBias = "neutral"
        else:
            bias = self._score_to_bias(
                aggregate_score,
                bullish_threshold=self.config.bullish_threshold,
                bearish_threshold=self.config.bearish_threshold,
            )
        confidence = self._calculate_confidence(layer_details, aggregate_score, bias)
        explanation = self._build_explanation(bias, layer_details, aggregate_score)

        logger.debug(
            f"Multi-timeframe bias: {bias} (confidence={confidence:.2f}, score={aggregate_score:.3f})"
        )

        return MultiTimeframeBiasResult(
            bias=bias,
            confidence=confidence,
            explanation=explanation,
            layers=tuple(layer_details),
        )

    def _validate_inputs(self, candles_by_timeframe: dict[str, pd.DataFrame]) -> None:
        if not candles_by_timeframe:
            raise MultiTimeframeBiasError("candles_by_timeframe cannot be empty")

        missing = [
            timeframe
            for timeframe in REQUIRED_TIMEFRAMES
            if timeframe not in candles_by_timeframe
        ]
        if missing:
            raise MultiTimeframeBiasError(
                f"Missing required timeframes: {', '.join(missing)}"
            )

    def _prepare_candles(
        self,
        candles: pd.DataFrame,
        min_candles: int,
        timeframe: str,
    ) -> pd.DataFrame:
        if candles is None or candles.empty:
            raise MultiTimeframeBiasError(f"{timeframe} candle data is empty")

        missing = [column for column in REQUIRED_COLUMNS if column not in candles.columns]
        if missing:
            raise MultiTimeframeBiasError(
                f"{timeframe} missing columns: {', '.join(missing)}"
            )

        frame = candles.copy()
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frame = frame.dropna(subset=["open", "high", "low", "close"])
        frame = frame.sort_values("time").reset_index(drop=True)

        if len(frame) < min_candles:
            raise MultiTimeframeBiasError(
                f"{timeframe} requires at least {min_candles} candles, got {len(frame)}"
            )
        return frame

    def _timeframe_score(self, frame: pd.DataFrame) -> float:
        cfg = self.config
        close = frame["close"].astype(float)
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)

        ma = close.rolling(cfg.ma_period).mean()
        if pd.isna(ma.iloc[-1]) or pd.isna(ma.iloc[-1 - cfg.slope_lookback]):
            return 0.0

        price_vs_ma = (close.iloc[-1] - ma.iloc[-1]) / ma.iloc[-1]
        ma_slope = (ma.iloc[-1] - ma.iloc[-1 - cfg.slope_lookback]) / (
            ma.iloc[-1 - cfg.slope_lookback] * cfg.slope_lookback
        )

        momentum_lookback = min(cfg.momentum_lookback, len(close) - 1)
        momentum = (close.iloc[-1] - close.iloc[-1 - momentum_lookback]) / close.iloc[
            -1 - momentum_lookback
        ]

        structure_score = self._structure_score(
            high,
            low,
            lookback=cfg.structure_lookback,
        )

        raw_score = (
            self._clamp(price_vs_ma * 120.0) * 0.30
            + self._clamp(ma_slope * 250.0) * 0.30
            + self._clamp(momentum * 100.0) * 0.25
            + structure_score * 0.15
        )
        return float(max(-1.0, min(1.0, raw_score)))

    def _structure_score(self, high: pd.Series, low: pd.Series, lookback: int) -> float:
        if len(high) < lookback * 2:
            return 0.0

        recent_high = float(high.iloc[-lookback:].max())
        prior_high = float(high.iloc[-lookback * 2 : -lookback].max())
        recent_low = float(low.iloc[-lookback:].min())
        prior_low = float(low.iloc[-lookback * 2 : -lookback].min())

        if recent_high > prior_high and recent_low > prior_low:
            return 1.0
        if recent_high < prior_high and recent_low < prior_low:
            return -1.0
        return 0.0

    def _score_to_bias(
        self,
        score: float,
        *,
        bullish_threshold: float | None = None,
        bearish_threshold: float | None = None,
    ) -> MarketBias:
        bullish = (
            self.config.bullish_threshold
            if bullish_threshold is None
            else bullish_threshold
        )
        bearish = (
            self.config.bearish_threshold
            if bearish_threshold is None
            else bearish_threshold
        )

        if score >= bullish:
            return "bullish"
        if score <= bearish:
            return "bearish"
        return "neutral"

    def _calculate_confidence(
        self,
        layers: list[TimeframeBiasDetail],
        aggregate_score: float,
        bias: MarketBias,
    ) -> float:
        if bias == "neutral":
            agreement = sum(1 for layer in layers if layer.bias == "neutral") / len(layers)
            magnitude = 1.0 - min(1.0, abs(aggregate_score) / self.config.bullish_threshold)
            raw = agreement * 0.55 + magnitude * 0.35
            return round(max(0.35, min(0.85, raw)), 2)

        aligned = [layer for layer in layers if layer.bias == bias]
        agreement = len(aligned) / len(layers)

        macro_layers = [layer for layer in layers if layer.role == "macro"]
        macro_aligned = sum(1 for layer in macro_layers if layer.bias == bias) / len(
            macro_layers
        )

        structure_layer = next(layer for layer in layers if layer.role == "structure")
        structure_aligned = 1.0 if structure_layer.bias == bias else 0.0

        precision_layer = next(layer for layer in layers if layer.role == "precision_entry")
        precision_aligned = 1.0 if precision_layer.bias == bias else 0.0

        magnitude = min(1.0, abs(aggregate_score) / 0.35)
        raw = (
            agreement * 0.40
            + macro_aligned * 0.25
            + structure_aligned * 0.20
            + precision_aligned * 0.10
            + magnitude * 0.05
        )
        return round(max(0.40, min(0.99, raw)), 2)

    def _build_explanation(
        self,
        bias: MarketBias,
        layers: list[TimeframeBiasDetail],
        aggregate_score: float,
    ) -> str:
        macro = [layer for layer in layers if layer.role == "macro"]
        structure = next(layer for layer in layers if layer.role == "structure")
        setup = [layer for layer in layers if layer.role == "setup"]
        precision = next(layer for layer in layers if layer.role == "precision_entry")

        macro_summary = ", ".join(f"{layer.timeframe} {layer.bias}" for layer in macro)
        setup_summary = ", ".join(f"{layer.timeframe} {layer.bias}" for layer in setup)

        if bias == "bullish":
            lead = "Bullish bias"
        elif bias == "bearish":
            lead = "Bearish bias"
        else:
            lead = "Neutral bias"

        return (
            f"{lead} (score {aggregate_score:.3f}). "
            f"Macro ({macro_summary}) sets direction, "
            f"H1 {structure.bias} confirms structure, "
            f"setup ({setup_summary}) quality, "
            f"M1 {precision.bias} for precision entry."
        )

    @staticmethod
    def _clamp(value: float, limit: float = 1.0) -> float:
        return max(-limit, min(limit, value))
