"""Indicator confirmation — insight enrichment only, never sole trade trigger."""

from __future__ import annotations

from dataclasses import dataclass

from intelligence.asset_trend_analyzer import AssetTrendFeatures
from intelligence.indicator_interpretation_engine import IndicatorInterpretationEngine
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult


@dataclass(frozen=True)
class IndicatorConfirmation:
    """Confirmation layer — adjusts narrative/council confidence."""

    boost: float
    atr_confirms: bool
    adx_confirms: bool
    ma_confirms: bool
    momentum_confirms: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "boost": round(self.boost, 2),
            "atr_confirms": self.atr_confirms,
            "adx_confirms": self.adx_confirms,
            "ma_confirms": self.ma_confirms,
            "momentum_confirms": self.momentum_confirms,
            "reason": self.reason,
        }


class IndicatorConfirmationEngine:
    """Interpretation-backed enrichment — boost only, never veto."""

    def __init__(self) -> None:
        self._interpreter = IndicatorInterpretationEngine()

    def confirm(
        self,
        *,
        features: AssetTrendFeatures | None,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        narrative_direction: str,
        candles: dict | None = None,
        symbol: str = "",
        regime: RegimeResult | None = None,
        spread_pips: float = 1.0,
        spread_limit: float = 3.0,
    ) -> IndicatorConfirmation:
        if candles:
            interp = self._interpreter.interpret(
                symbol=symbol or structure.symbol,
                candles=candles,
                structure=structure,
                bias=bias,
                regime=regime,
                features=features,
                narrative_direction=narrative_direction,
                spread_pips=spread_pips,
                spread_limit=spread_limit,
            )
            boost = interp.insight_score
            if features is None and regime is not None:
                features = self._interpreter._analyzer._compute_features(
                    candles=candles,
                    bias=bias,
                    structure=structure,
                    regime=regime,
                    spread_pips=spread_pips,
                    spread_limit=spread_limit,
                    target_pips=10.0,
                    in_active_session=True,
                )
        elif features is None:
            return IndicatorConfirmation(
                boost=0.0,
                atr_confirms=False,
                adx_confirms=False,
                ma_confirms=False,
                momentum_confirms=False,
                reason="No features — narrative drives decision",
            )
        else:
            boost = self._legacy_boost(features, structure, bias, narrative_direction)

        atr_ok = features is not None and 0.75 <= features.atr_ratio <= 1.45
        adx_ok = features is not None and features.adx >= 18.0
        ma_ok = False
        if features is not None:
            if narrative_direction == "bullish" and features.ma_slope_signed > 0:
                ma_ok = True
            elif narrative_direction == "bearish" and features.ma_slope_signed < 0:
                ma_ok = True
            elif narrative_direction == "neutral":
                ma_ok = features.ma_slope_abs < 0.00005
        mom_ok = False
        if features is not None:
            if narrative_direction == "bullish" and features.precision_momentum > 0:
                mom_ok = True
            elif narrative_direction == "bearish" and features.precision_momentum < 0:
                mom_ok = True
        if features is not None and structure.trend == bias.bias and bias.bias != "neutral":
            boost = min(12.0, boost + 2.0)

        confirms: list[str] = []
        if atr_ok:
            confirms.append("ATR")
        if adx_ok:
            confirms.append("ADX")
        if ma_ok:
            confirms.append("MA")
        if mom_ok:
            confirms.append("momentum")
        reason = f"Interpretation insight: {', '.join(confirms) or 'contextual'} (+{boost:.0f})"
        return IndicatorConfirmation(
            boost=min(12.0, boost),
            atr_confirms=atr_ok,
            adx_confirms=adx_ok,
            ma_confirms=ma_ok,
            momentum_confirms=mom_ok,
            reason=reason,
        )

    @staticmethod
    def _legacy_boost(
        features: AssetTrendFeatures,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        narrative_direction: str,
    ) -> float:
        boost = 0.0
        if 0.75 <= features.atr_ratio <= 1.45:
            boost += 4.0
        if features.adx >= 18.0:
            boost += 3.0
        if narrative_direction == "bullish" and features.ma_slope_signed > 0:
            boost += 3.0
        elif narrative_direction == "bearish" and features.ma_slope_signed < 0:
            boost += 3.0
        elif narrative_direction == "neutral" and features.ma_slope_abs < 0.00005:
            boost += 2.0
        if narrative_direction == "bullish" and features.precision_momentum > 0:
            boost += 4.0
        elif narrative_direction == "bearish" and features.precision_momentum < 0:
            boost += 4.0
        if structure.trend == bias.bias and bias.bias != "neutral":
            boost += 2.0
        return min(12.0, boost)
