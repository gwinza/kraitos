"""Trend Strength Score engine (0–100) for opportunity allocation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from intelligence.asset_trend_analyzer import AssetTrendAnalyzer, AssetTrendSnapshot
from strategies.models import (
    MarketContext,
    MultiTimeframeBiasResult,
    RegimeResult,
)

TrendQuality = Literal[
    "institutional_trend",
    "developing_trend",
    "weak_trend",
    "range_or_noise",
]

QUALITY_THRESHOLDS = {
    "institutional_trend": 80,
    "developing_trend": 60,
    "weak_trend": 40,
}


@dataclass(frozen=True)
class TrendStrengthResult:
    """Trend strength assessment for one asset."""

    symbol: str
    score: float
    quality: TrendQuality
    direction: str
    components: dict[str, float]
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "score": round(self.score, 2),
            "quality": self.quality,
            "direction": self.direction,
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "reason": self.reason,
        }


class TrendStrengthEngine:
    """Compute 0–100 trend strength from multi-timeframe context."""

    def __init__(self, trend_analyzer: AssetTrendAnalyzer | None = None) -> None:
        self._analyzer = trend_analyzer or AssetTrendAnalyzer()

    def evaluate(
        self,
        *,
        symbol: str,
        candles: dict,
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
        regime: RegimeResult,
        spread_pips: float,
        spread_limit: float,
        in_active_session: bool = True,
        evaluation_time: str | None = None,
    ) -> tuple[AssetTrendSnapshot, TrendStrengthResult]:
        snapshot = self._analyzer.analyze(
            symbol=symbol,
            candles=candles,
            bias=bias,
            structure=structure,
            regime=regime,
            spread_pips=spread_pips,
            spread_limit=spread_limit,
            in_active_session=in_active_session,
            evaluation_time=evaluation_time,
        )
        strength = self._score_from_snapshot(snapshot, bias, structure, regime)
        return snapshot, strength

    def score_snapshot(
        self,
        snapshot: AssetTrendSnapshot,
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
        regime: RegimeResult,
    ) -> TrendStrengthResult:
        return self._score_from_snapshot(snapshot, bias, structure, regime)

    def _score_from_snapshot(
        self,
        snapshot: AssetTrendSnapshot,
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
        regime: RegimeResult,
    ) -> TrendStrengthResult:
        f = snapshot.features
        components: dict[str, float] = {}

        macro_score = 1.0 if f.macro_trend == bias.bias and bias.bias != "neutral" else 0.3
        if f.layer_agreement >= 0.65:
            macro_score = min(1.0, macro_score + 0.2)
        components["macro_alignment"] = macro_score * 15.0

        structure_score = 0.4
        if structure.trend == bias.bias and bias.bias != "neutral":
            structure_score = 0.85
        if structure.higher_highs and structure.higher_lows and bias.bias == "bullish":
            structure_score = 1.0
        if structure.lower_highs and structure.lower_lows and bias.bias == "bearish":
            structure_score = 1.0
        components["structure"] = structure_score * 15.0

        momentum_score = min(1.0, f.setup_alignment + abs(f.precision_momentum) * 5000)
        components["momentum_persistence"] = momentum_score * 12.0

        adx_score = min(1.0, f.adx / 35.0)
        components["adx"] = adx_score * 12.0

        slope_score = min(1.0, f.ma_slope_abs / 0.0002)
        components["ma_slope"] = slope_score * 10.0

        vol_score = 0.5
        if 0.85 <= f.atr_ratio <= 1.35:
            vol_score = 1.0
        elif f.range_expansion >= 1.2 and snapshot.state == "volatile_breakout":
            vol_score = 0.85
        components["volatility_quality"] = vol_score * 10.0

        swing_score = 0.5
        if structure.higher_highs or structure.higher_lows:
            swing_score = 0.75
        if (structure.higher_highs and structure.higher_lows) or (
            structure.lower_highs and structure.lower_lows
        ):
            swing_score = 1.0
        components["swing_progression"] = swing_score * 10.0

        consistency = max(0.0, 1.0 - f.choppiness)
        components["trend_consistency"] = consistency * 16.0

        total = sum(components.values())
        total = max(0.0, min(100.0, total))

        if regime.regime in {"low_liquidity", "news_risk", "unclear"}:
            total = min(total, 35.0)

        quality = self._classify_quality(total)
        direction = bias.bias if bias.bias != "neutral" else f.macro_trend

        return TrendStrengthResult(
            symbol=snapshot.symbol,
            score=round(total, 2),
            quality=quality,
            direction=direction,
            components=components,
            reason=f"{quality} score={total:.0f} ({snapshot.state})",
        )

    @staticmethod
    def _classify_quality(score: float) -> TrendQuality:
        if score >= QUALITY_THRESHOLDS["institutional_trend"]:
            return "institutional_trend"
        if score >= QUALITY_THRESHOLDS["developing_trend"]:
            return "developing_trend"
        if score >= QUALITY_THRESHOLDS["weak_trend"]:
            return "weak_trend"
        return "range_or_noise"
