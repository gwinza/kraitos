"""Tradability engine v2 — score spread, volatility, liquidity, and reward potential."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategies.market_reading_utils import atr_series, validate_candles, volume_participation

TradabilityGrade = Literal["A", "B", "C", "D"]


@dataclass(frozen=True)
class TradabilityComponents:
    """Component scores (0–100)."""

    spread_quality: int
    volatility_quality: int
    liquidity_quality: int
    reward_potential: int

    def to_dict(self) -> dict:
        return {
            "spread_quality": self.spread_quality,
            "volatility_quality": self.volatility_quality,
            "liquidity_quality": self.liquidity_quality,
            "reward_potential": self.reward_potential,
        }


@dataclass(frozen=True)
class TradabilityResultV2:
    """Enhanced tradability assessment."""

    symbol: str
    tradability_score: int
    grade: TradabilityGrade
    components: TradabilityComponents
    spread_drag_pct: float
    reward_risk_ratio: float
    executable: bool
    explanation: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "tradability_score": self.tradability_score,
            "grade": self.grade,
            "components": self.components.to_dict(),
            "spread_drag_pct": round(self.spread_drag_pct, 3),
            "reward_risk_ratio": round(self.reward_risk_ratio, 3),
            "executable": self.executable,
            "explanation": self.explanation,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class TradabilityEngineV2Config:
    min_tradability_probe: int = 35
    min_tradability_normal: int = 52
    ideal_spread_drag_pct: float = 0.12
    max_spread_drag_pct: float = 0.40
    min_reward_risk: float = 0.80
    ideal_reward_risk: float = 1.50


class TradabilityEngineV2Error(Exception):
    pass


class TradabilityEngineV2:
    """Score whether a setup is worth executing — improves quality, not fewer trades."""

    def __init__(self, config: TradabilityEngineV2Config | None = None) -> None:
        self.config = config or TradabilityEngineV2Config()

    def evaluate(
        self,
        *,
        symbol: str,
        spread_pips: float,
        spread_limit: float,
        stop_pips: float,
        target_pips: float,
        candles: pd.DataFrame | None = None,
    ) -> TradabilityResultV2:
        if stop_pips <= 0:
            raise TradabilityEngineV2Error("stop_pips must be positive")

        rr = target_pips / stop_pips if target_pips > 0 else 0.0
        spread_drag = spread_pips / max(target_pips, 0.01)

        spread_score = self._spread_quality(spread_pips, spread_limit, spread_drag)
        vol_score = self._volatility_quality(candles, stop_pips)
        liq_score = self._liquidity_quality(candles, spread_pips, spread_limit)
        reward_score = self._reward_potential(rr)

        raw = spread_score * 0.25 + vol_score * 0.25 + liq_score * 0.20 + reward_score * 0.30
        score = int(max(0, min(100, round(raw))))
        grade = self._grade(score)
        executable = score >= self.config.min_tradability_probe and rr >= self.config.min_reward_risk * 0.5

        evidence = (
            f"spread quality {spread_score}/100 (drag {spread_drag:.1%})",
            f"volatility quality {vol_score}/100",
            f"liquidity quality {liq_score}/100",
            f"reward potential {reward_score}/100 ({rr:.2f}R)",
        )

        return TradabilityResultV2(
            symbol=symbol.strip().upper(),
            tradability_score=score,
            grade=grade,
            components=TradabilityComponents(
                spread_quality=spread_score,
                volatility_quality=vol_score,
                liquidity_quality=liq_score,
                reward_potential=reward_score,
            ),
            spread_drag_pct=spread_drag,
            reward_risk_ratio=rr,
            executable=executable,
            explanation=f"Tradability {score}/100 ({grade}) — {rr:.2f}R, spread drag {spread_drag:.1%}",
            evidence=evidence,
        )

    def _spread_quality(self, spread: float, limit: float, drag: float) -> int:
        cfg = self.config
        if spread > limit:
            return max(0, 30 - int((spread - limit) * 10))
        if drag <= cfg.ideal_spread_drag_pct:
            return 95
        if drag <= cfg.max_spread_drag_pct:
            ratio = (drag - cfg.ideal_spread_drag_pct) / (
                cfg.max_spread_drag_pct - cfg.ideal_spread_drag_pct
            )
            return int(95 - ratio * 45)
        return max(15, int(50 - (drag - cfg.max_spread_drag_pct) * 80))

    @staticmethod
    def _volatility_quality(candles: pd.DataFrame | None, stop_pips: float) -> int:
        if candles is None or candles.empty:
            return 55
        try:
            frame = validate_candles(candles, min_candles=15, engine="TradabilityEngineV2")
            atr = float(atr_series(frame).iloc[-1])
            pip_proxy = atr / max(float(frame["close"].iloc[-1]) * 0.0001, 1e-9)
            atr_pips = atr / max(pip_proxy * 0.0001, 1e-9) if pip_proxy else atr * 10000
            ratio = stop_pips / max(atr_pips, 0.1)
            if 0.8 <= ratio <= 2.5:
                return 85
            if 0.5 <= ratio <= 3.5:
                return 70
            return 45
        except ValueError:
            return 50

    @staticmethod
    def _liquidity_quality(
        candles: pd.DataFrame | None, spread: float, limit: float
    ) -> int:
        score = 60
        if spread <= limit * 0.5:
            score += 20
        elif spread <= limit:
            score += 10
        else:
            score -= 20
        if candles is not None and not candles.empty:
            participation = volume_participation(candles)
            score += int(participation * 25)
        return max(0, min(100, score))

    def _reward_potential(self, rr: float) -> int:
        cfg = self.config
        if rr >= cfg.ideal_reward_risk:
            return 95
        if rr >= cfg.min_reward_risk:
            span = cfg.ideal_reward_risk - cfg.min_reward_risk
            progress = (rr - cfg.min_reward_risk) / span if span > 0 else 0
            return int(65 + progress * 30)
        if rr >= cfg.min_reward_risk * 0.5:
            return int(40 + (rr / cfg.min_reward_risk) * 25)
        return max(10, int(rr * 40))

    @staticmethod
    def _grade(score: int) -> TradabilityGrade:
        if score >= 75:
            return "A"
        if score >= 58:
            return "B"
        if score >= 40:
            return "C"
        return "D"


__all__ = [
    "TradabilityComponents",
    "TradabilityEngineV2",
    "TradabilityEngineV2Config",
    "TradabilityEngineV2Error",
    "TradabilityGrade",
    "TradabilityResultV2",
]
