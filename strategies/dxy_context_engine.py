"""DXY context engine — dollar index context for Gold and USD pairs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategies.market_reading_utils import atr_series, validate_candles

DxyDirection = Literal["rising", "falling", "neutral"]
DxyStrength = Literal["strong", "moderate", "weak"]


@dataclass(frozen=True)
class DxyContextResult:
    """DXY directional context for correlated instruments."""

    symbol: str
    dxy_direction: DxyDirection
    dxy_strength: DxyStrength
    dxy_divergence: bool
    dxy_strength_score: int
    gold_alignment: Literal["aligned", "divergent", "neutral"]
    explanation: str
    trade_opportunity: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "dxy_direction": self.dxy_direction,
            "dxy_strength": self.dxy_strength,
            "dxy_divergence": self.dxy_divergence,
            "dxy_strength_score": self.dxy_strength_score,
            "gold_alignment": self.gold_alignment,
            "explanation": self.explanation,
            "trade_opportunity": self.trade_opportunity,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class DxyContextConfig:
    min_candles: int = 30
    lookback: int = 60


class DxyContextEngineError(Exception):
    pass


class DxyContextEngine:
    """Track DXY direction, divergence, and strength for Gold and USD exposure."""

    def __init__(self, config: DxyContextConfig | None = None) -> None:
        self.config = config or DxyContextConfig()

    def analyze(
        self,
        dxy_candles: pd.DataFrame | None,
        *,
        symbol: str = "XAUUSD",
        asset_candles: pd.DataFrame | None = None,
    ) -> DxyContextResult:
        symbol_key = symbol.strip().upper()
        if dxy_candles is None or dxy_candles.empty:
            return self._neutral(symbol_key, "No DXY data — context unavailable")

        try:
            dxy = validate_candles(
                dxy_candles, min_candles=self.config.min_candles, engine="DxyContextEngine"
            ).tail(self.config.lookback)
        except ValueError as exc:
            raise DxyContextEngineError(str(exc)) from exc

        atr = atr_series(dxy)
        atr_value = float(atr.iloc[-1]) or 1.0
        close = dxy["close"].astype(float)
        progress = (float(close.iloc[-1]) - float(close.iloc[-20])) / atr_value
        short_move = (float(close.iloc[-1]) - float(close.iloc[-5])) / atr_value

        if progress > 0.8:
            direction: DxyDirection = "rising"
        elif progress < -0.8:
            direction = "falling"
        else:
            direction = "neutral"

        strength_score = int(min(100, max(0, abs(progress) / 4.0 * 100 + abs(short_move) * 15)))
        if strength_score >= 65:
            strength: DxyStrength = "strong"
        elif strength_score >= 35:
            strength = "moderate"
        else:
            strength = "weak"

        divergence = False
        gold_alignment: Literal["aligned", "divergent", "neutral"] = "neutral"
        evidence: list[str] = [f"DXY {direction} ({strength}, score {strength_score})"]

        if asset_candles is not None and not asset_candles.empty and symbol_key in {"XAUUSD", "GOLD"}:
            try:
                asset = validate_candles(
                    asset_candles, min_candles=20, engine="DxyContextEngine"
                ).tail(self.config.lookback)
                asset_close = asset["close"].astype(float)
                asset_atr = float(atr_series(asset).iloc[-1]) or 1.0
                asset_progress = (float(asset_close.iloc[-1]) - float(asset_close.iloc[-20])) / asset_atr

                if direction == "falling" and asset_progress > 0.5:
                    gold_alignment = "aligned"
                    evidence.append("Gold rising with falling DXY — aligned")
                elif direction == "rising" and asset_progress < -0.5:
                    gold_alignment = "aligned"
                    evidence.append("Gold falling with rising DXY — aligned")
                elif direction == "rising" and asset_progress > 0.5:
                    divergence = True
                    gold_alignment = "divergent"
                    evidence.append("Gold rising against rising DXY — bullish divergence")
                elif direction == "falling" and asset_progress < -0.5:
                    divergence = True
                    gold_alignment = "divergent"
                    evidence.append("Gold falling against falling DXY — bearish divergence")
            except ValueError:
                pass

        opportunity = self._trade_opportunity(symbol_key, direction, strength, gold_alignment, divergence)

        return DxyContextResult(
            symbol=symbol_key,
            dxy_direction=direction,
            dxy_strength=strength,
            dxy_divergence=divergence,
            dxy_strength_score=strength_score,
            gold_alignment=gold_alignment,
            explanation=f"DXY {direction}/{strength} — Gold {gold_alignment}",
            trade_opportunity=opportunity,
            evidence=tuple(evidence),
        )

    @staticmethod
    def _neutral(symbol: str, reason: str) -> DxyContextResult:
        return DxyContextResult(
            symbol=symbol,
            dxy_direction="neutral",
            dxy_strength="weak",
            dxy_divergence=False,
            dxy_strength_score=0,
            gold_alignment="neutral",
            explanation=reason,
            trade_opportunity="Trade Gold on structure — DXY context pending",
            evidence=(reason,),
        )

    @staticmethod
    def _trade_opportunity(
        symbol: str,
        direction: DxyDirection,
        strength: DxyStrength,
        alignment: str,
        divergence: bool,
    ) -> str:
        if symbol not in {"XAUUSD", "GOLD"}:
            if direction == "rising" and strength != "weak":
                return "USD strength — favour USD longs / commodity shorts on structure"
            if direction == "falling" and strength != "weak":
                return "USD weakness — favour USD shorts / commodity longs on structure"
            return "Neutral DXY — trade instrument structure independently"

        if alignment == "aligned" and direction == "falling":
            return "Gold longs favoured — DXY falling supports bullion"
        if alignment == "aligned" and direction == "rising":
            return "Gold shorts favoured — DXY rising pressures bullion"
        if divergence and direction == "rising":
            return "Gold divergence bullish — strong gold despite USD — scout longs"
        if divergence and direction == "falling":
            return "Gold divergence bearish — weak gold despite USD — scout shorts"
        return "Gold — use DXY as confluence, not veto; trade structure"


__all__ = [
    "DxyContextConfig",
    "DxyContextEngine",
    "DxyContextEngineError",
    "DxyContextResult",
    "DxyDirection",
    "DxyStrength",
]
