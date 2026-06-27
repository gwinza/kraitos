"""Analyse per-asset trend, regime, and microstructure for strategy selection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from strategies.models import (
    MarketContext,
    MultiTimeframeBiasResult,
    RegimeResult,
)

AssetState = Literal[
    "strong_uptrend",
    "strong_downtrend",
    "weak_trend",
    "ranging",
    "volatile_breakout",
    "choppy_noise",
    "mean_reverting",
    "low_liquidity",
    "unsuitable_now",
]

REQUIRED_COLUMNS = ("time", "open", "high", "low", "close", "tick_volume", "spread")


@dataclass(frozen=True)
class AssetTrendFeatures:
    """Computed market condition features for one symbol."""

    macro_trend: str
    structure_trend: str
    setup_alignment: float
    precision_momentum: float
    atr_ratio: float
    adx: float
    ma_slope_signed: float
    ma_slope_abs: float
    range_compression: float
    range_expansion: float
    breakout_score: float
    mean_reversion_score: float
    swing_range_pips: float
    spread_to_target_ratio: float
    spread_to_limit: float
    session_strength: float
    volume_ratio: float
    layer_agreement: float
    choppiness: float

    def to_dict(self) -> dict[str, float | str]:
        return {
            "macro_trend": self.macro_trend,
            "structure_trend": self.structure_trend,
            "setup_alignment": round(self.setup_alignment, 4),
            "precision_momentum": round(self.precision_momentum, 6),
            "atr_ratio": round(self.atr_ratio, 4),
            "adx": round(self.adx, 2),
            "ma_slope_signed": round(self.ma_slope_signed, 6),
            "ma_slope_abs": round(self.ma_slope_abs, 6),
            "range_compression": round(self.range_compression, 4),
            "range_expansion": round(self.range_expansion, 4),
            "breakout_score": round(self.breakout_score, 4),
            "mean_reversion_score": round(self.mean_reversion_score, 4),
            "swing_range_pips": round(self.swing_range_pips, 2),
            "spread_to_target_ratio": round(self.spread_to_target_ratio, 4),
            "spread_to_limit": round(self.spread_to_limit, 4),
            "session_strength": round(self.session_strength, 4),
            "volume_ratio": round(self.volume_ratio, 4),
            "layer_agreement": round(self.layer_agreement, 4),
            "choppiness": round(self.choppiness, 4),
        }


@dataclass(frozen=True)
class AssetTrendSnapshot:
    """Classified asset state with supporting features."""

    symbol: str
    state: AssetState
    confidence: float
    reason: str
    features: AssetTrendFeatures
    regime: str
    bias: str
    evaluation_time: str | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "state": self.state,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "regime": self.regime,
            "bias": self.bias,
            "evaluation_time": self.evaluation_time,
            "features": self.features.to_dict(),
        }


@dataclass(frozen=True)
class AssetTrendAnalyzerConfig:
    """Thresholds for asset state classification."""

    atr_period: int = 14
    atr_long_period: int = 50
    ma_period: int = 20
    ma_slope_lookback: int = 5
    adx_period: int = 14
    strong_adx: float = 25.0
    weak_adx: float = 18.0
    strong_slope: float = 0.00012
    weak_slope: float = 0.00004
    compression_ratio: float = 0.75
    expansion_ratio: float = 1.35
    max_spread_to_target: float = 0.35
    choppy_layer_threshold: float = 0.45


class AssetTrendAnalyzer:
    """Classify current asset state from multi-timeframe context."""

    def __init__(self, config: AssetTrendAnalyzerConfig | None = None) -> None:
        self.config = config or AssetTrendAnalyzerConfig()

    def analyze(
        self,
        *,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
        regime: RegimeResult,
        spread_pips: float,
        spread_limit: float,
        target_pips: float = 10.0,
        in_active_session: bool = True,
        evaluation_time: str | None = None,
    ) -> AssetTrendSnapshot:
        features = self._compute_features(
            candles=candles,
            bias=bias,
            structure=structure,
            regime=regime,
            spread_pips=spread_pips,
            spread_limit=spread_limit,
            target_pips=target_pips,
            in_active_session=in_active_session,
        )
        state, confidence, reason = self._classify_state(features, regime, bias, structure)
        return AssetTrendSnapshot(
            symbol=symbol,
            state=state,
            confidence=confidence,
            reason=reason,
            features=features,
            regime=regime.regime,
            bias=bias.bias,
            evaluation_time=evaluation_time,
        )

    def _compute_features(
        self,
        *,
        candles: dict[str, pd.DataFrame],
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
        regime: RegimeResult,
        spread_pips: float,
        spread_limit: float,
        target_pips: float,
        in_active_session: bool,
    ) -> AssetTrendFeatures:
        h1 = self._prepare(candles.get("H1", pd.DataFrame()))
        m1 = self._prepare(candles.get("M1", pd.DataFrame()))
        m5 = self._prepare(candles.get("M5", pd.DataFrame()))

        h1_feats = self._ohlc_features(h1) if not h1.empty else self._empty_ohlc()
        macro = self._macro_trend(bias)
        setup_alignment = self._setup_alignment(bias)
        precision = self._precision_momentum(m1, m5)
        swing_range = self._swing_range_pips(structure, h1)
        layer_agreement = self._layer_agreement(bias)
        choppiness = self._choppiness(bias, structure, regime)

        spread_to_target = spread_pips / max(target_pips, 0.1)
        spread_to_limit = spread_pips / max(spread_limit, 0.1)

        return AssetTrendFeatures(
            macro_trend=macro,
            structure_trend=structure.trend,
            setup_alignment=setup_alignment,
            precision_momentum=precision,
            atr_ratio=h1_feats["atr_ratio"],
            adx=h1_feats["adx"],
            ma_slope_signed=h1_feats["ma_slope_signed"],
            ma_slope_abs=abs(h1_feats["ma_slope_signed"]),
            range_compression=h1_feats["compression_ratio"],
            range_expansion=h1_feats["expansion_ratio"],
            breakout_score=h1_feats["breakout_score"],
            mean_reversion_score=h1_feats["mean_reversion_score"],
            swing_range_pips=swing_range,
            spread_to_target_ratio=spread_to_target,
            spread_to_limit=spread_to_limit,
            session_strength=1.0 if in_active_session else 0.35,
            volume_ratio=h1_feats["volume_ratio"],
            layer_agreement=layer_agreement,
            choppiness=choppiness,
        )

    def _classify_state(
        self,
        features: AssetTrendFeatures,
        regime: RegimeResult,
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
    ) -> tuple[AssetState, float, str]:
        cfg = self.config

        if regime.regime == "news_risk":
            return "unsuitable_now", 0.95, "News-risk regime active"

        if (
            features.spread_to_limit >= 1.0
            or regime.regime == "low_liquidity"
            or features.volume_ratio < 0.5
        ):
            return (
                "low_liquidity",
                0.88,
                f"Spread/volume unsuitable (spread/limit={features.spread_to_limit:.2f})",
            )

        if features.spread_to_target_ratio > cfg.max_spread_to_target:
            return (
                "unsuitable_now",
                0.82,
                f"Spread-to-target ratio too high ({features.spread_to_target_ratio:.2f})",
            )

        if features.choppiness >= 0.7 or regime.regime == "unclear":
            return "choppy_noise", 0.8, "Conflicting layers and unclear structure"

        if (
            features.breakout_score >= 0.65
            and features.range_expansion >= cfg.expansion_ratio
            and regime.regime == "volatile"
        ):
            return "volatile_breakout", 0.85, "Volatility expansion with breakout behaviour"

        if (
            features.mean_reversion_score >= 0.6
            or (regime.regime == "ranging" and structure.trend == "ranging")
        ):
            return "mean_reverting", 0.78, "Range-bound mean reversion behaviour"

        if regime.regime == "ranging" or features.ma_slope_abs <= cfg.weak_slope:
            return "ranging", 0.75, "Compressed range with flat slope"

        bullish_stack = (
            bias.bias == "bullish"
            and features.macro_trend == "bullish"
            and structure.trend == "bullish"
            and features.ma_slope_signed > 0
        )
        bearish_stack = (
            bias.bias == "bearish"
            and features.macro_trend == "bearish"
            and structure.trend == "bearish"
            and features.ma_slope_signed < 0
        )

        if (
            bullish_stack
            and features.adx >= cfg.strong_adx
            and features.layer_agreement >= 0.65
        ):
            return "strong_uptrend", 0.9, "Aligned bullish macro/structure with strong ADX"

        if (
            bearish_stack
            and features.adx >= cfg.strong_adx
            and features.layer_agreement >= 0.65
        ):
            return "strong_downtrend", 0.9, "Aligned bearish macro/structure with strong ADX"

        if regime.regime == "trending" or features.ma_slope_abs >= cfg.weak_slope:
            return "weak_trend", 0.68, "Trend present but confirmation is mixed"

        return "choppy_noise", 0.55, "No clear tradable state"

    @staticmethod
    def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame()
        missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
        if missing:
            return pd.DataFrame()
        out = frame.copy()
        out["time"] = pd.to_datetime(out["time"], utc=True, errors="coerce")
        return out.dropna(subset=["open", "high", "low", "close"]).sort_values("time")

    def _ohlc_features(self, frame: pd.DataFrame) -> dict[str, float]:
        cfg = self.config
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        close = frame["close"].astype(float)
        open_ = frame["open"].astype(float)

        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(cfg.atr_period).mean()
        atr_long = tr.rolling(cfg.atr_long_period).mean()
        ma = close.rolling(cfg.ma_period).mean()
        lb = cfg.ma_slope_lookback
        ma_slope = (ma.iloc[-1] - ma.iloc[-1 - lb]) / (ma.iloc[-1 - lb] * lb)

        current_atr = float(atr.iloc[-1])
        baseline_atr = float(atr_long.iloc[-1]) or current_atr
        atr_ratio = current_atr / baseline_atr if baseline_atr > 0 else 1.0

        recent_high = float(high.tail(20).max())
        recent_low = float(low.tail(20).min())
        range_mid = (recent_high + recent_low) / 2.0
        distance_from_mid = abs(float(close.iloc[-1]) - range_mid)
        range_width = max(recent_high - recent_low, 1e-9)
        mean_reversion = 1.0 - min(1.0, distance_from_mid / (range_width / 2.0))

        breakout = 0.0
        if float(close.iloc[-1]) >= recent_high * 0.9995:
            breakout += 0.5
        if float(close.iloc[-1]) <= recent_low * 1.0005:
            breakout += 0.5
        if atr_ratio >= cfg.expansion_ratio:
            breakout += 0.25

        volume = float(frame["tick_volume"].iloc[-1])
        mean_volume = float(frame["tick_volume"].rolling(cfg.atr_period).mean().iloc[-1])
        volume_ratio = volume / mean_volume if mean_volume > 0 else 1.0

        return {
            "atr_ratio": atr_ratio,
            "compression_ratio": atr_ratio if atr_ratio < 1.0 else 1.0,
            "expansion_ratio": atr_ratio,
            "ma_slope_signed": float(ma_slope),
            "adx": self._adx(frame),
            "breakout_score": min(1.0, breakout),
            "mean_reversion_score": mean_reversion,
            "volume_ratio": volume_ratio,
        }

    def _adx(self, frame: pd.DataFrame) -> float:
        cfg = self.config
        if len(frame) < cfg.adx_period + 2:
            return 0.0
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        close = frame["close"].astype(float)
        up = high.diff()
        down = -low.diff()
        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)
        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(cfg.adx_period).mean()
        plus_di = 100 * pd.Series(plus_dm, index=frame.index).rolling(cfg.adx_period).mean() / atr
        minus_di = 100 * pd.Series(minus_dm, index=frame.index).rolling(cfg.adx_period).mean() / atr
        dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
        adx = dx.rolling(cfg.adx_period).mean()
        value = float(adx.iloc[-1])
        return 0.0 if np.isnan(value) else value

    @staticmethod
    def _macro_trend(bias: MultiTimeframeBiasResult) -> str:
        macro_layers = [layer for layer in bias.layers if layer.role == "macro"]
        if not macro_layers:
            return bias.bias
        bullish = sum(1 for layer in macro_layers if layer.bias == "bullish")
        bearish = sum(1 for layer in macro_layers if layer.bias == "bearish")
        if bullish > bearish:
            return "bullish"
        if bearish > bullish:
            return "bearish"
        return "neutral"

    @staticmethod
    def _setup_alignment(bias: MultiTimeframeBiasResult) -> float:
        setup_layers = [layer for layer in bias.layers if layer.role == "setup"]
        if not setup_layers:
            return 0.5
        aligned = sum(1 for layer in setup_layers if layer.bias == bias.bias)
        return aligned / len(setup_layers)

    @staticmethod
    def _precision_momentum(m1: pd.DataFrame, m5: pd.DataFrame) -> float:
        values: list[float] = []
        for frame in (m1, m5):
            if frame.empty or len(frame) < 6:
                continue
            close = frame["close"].astype(float)
            values.append(float(close.iloc[-1] - close.iloc[-6]))
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def _swing_range_pips(structure: MarketContext, h1: pd.DataFrame) -> float:
        highs = [point.price for point in structure.swing_highs[-3:]]
        lows = [point.price for point in structure.swing_lows[-3:]]
        if highs and lows:
            width = max(highs) - min(lows)
            pip = 0.01 if structure.symbol.endswith("JPY") else 0.0001
            return width / pip
        if not h1.empty:
            width = float(h1["high"].tail(20).max() - h1["low"].tail(20).min())
            pip = 0.01 if structure.symbol.endswith("JPY") else 0.0001
            return width / pip
        return 0.0

    @staticmethod
    def _layer_agreement(bias: MultiTimeframeBiasResult) -> float:
        if not bias.layers:
            return 0.5
        aligned = sum(1 for layer in bias.layers if layer.bias == bias.bias)
        return aligned / len(bias.layers)

    @staticmethod
    def _choppiness(
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
        regime: RegimeResult,
    ) -> float:
        directions = {layer.bias for layer in bias.layers}
        score = 0.0
        if len(directions) >= 3:
            score += 0.35
        if structure.higher_highs and structure.lower_lows:
            score += 0.25
        if regime.regime == "unclear":
            score += 0.25
        if bias.confidence < 0.5:
            score += 0.15
        return min(1.0, score)

    @staticmethod
    def _empty_ohlc() -> dict[str, float]:
        return {
            "atr_ratio": 1.0,
            "compression_ratio": 1.0,
            "expansion_ratio": 1.0,
            "ma_slope_signed": 0.0,
            "adx": 0.0,
            "breakout_score": 0.0,
            "mean_reversion_score": 0.0,
            "volume_ratio": 1.0,
        }
