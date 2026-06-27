"""Liquidity sweep engine — detect stop hunts and sweep failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategies.market_reading_utils import atr_series, swing_points, validate_candles

SweepType = Literal[
    "stop_hunt",
    "buy_side_sweep",
    "sell_side_sweep",
    "sweep_failure",
    "none",
]


@dataclass(frozen=True)
class LiquiditySweepResult:
    """Liquidity sweep detection result."""

    symbol: str
    timeframe: str
    liquidity_sweep_probability: float
    sweep_type: SweepType
    sweep_level: float
    reclaimed: bool
    buy_side_swept: bool
    sell_side_swept: bool
    explanation: str
    evidence: tuple[str, ...] = ()
    trade_opportunity: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "liquidity_sweep_probability": round(self.liquidity_sweep_probability, 3),
            "sweep_type": self.sweep_type,
            "sweep_level": round(self.sweep_level, 5),
            "reclaimed": self.reclaimed,
            "buy_side_swept": self.buy_side_swept,
            "sell_side_swept": self.sell_side_swept,
            "explanation": self.explanation,
            "evidence": list(self.evidence),
            "trade_opportunity": self.trade_opportunity,
        }


@dataclass(frozen=True)
class LiquiditySweepConfig:
    min_candles: int = 40
    lookback: int = 80
    swing_window: int = 2
    sweep_tolerance_atr: float = 0.15
    reclaim_bars: int = 5


class LiquiditySweepEngineError(Exception):
    pass


class LiquiditySweepEngine:
    """Detect stop hunts, buy/sell-side sweeps, and sweep failures."""

    def __init__(self, config: LiquiditySweepConfig | None = None) -> None:
        self.config = config or LiquiditySweepConfig()

    def analyze(
        self,
        candles: pd.DataFrame,
        *,
        symbol: str = "",
        timeframe: str = "H1",
    ) -> LiquiditySweepResult:
        try:
            frame = validate_candles(
                candles, min_candles=self.config.min_candles, engine="LiquiditySweepEngine"
            ).tail(self.config.lookback)
        except ValueError as exc:
            raise LiquiditySweepEngineError(str(exc)) from exc

        atr = atr_series(frame)
        atr_value = float(atr.iloc[-1]) or float((frame["high"] - frame["low"]).median()) or 1.0
        highs, lows = swing_points(frame, window=self.config.swing_window)
        tolerance = atr_value * self.config.sweep_tolerance_atr

        buy_side_level = max((h for _, h in highs[-4:]), default=float(frame["high"].iloc[-20:-1].max()))
        sell_side_level = min((l for _, l in lows[-4:]), default=float(frame["low"].iloc[-20:-1].min()))

        tail = frame.tail(self.config.reclaim_bars + 3)
        buy_swept = bool((tail["high"] > buy_side_level + tolerance).any())
        sell_swept = bool((tail["low"] < sell_side_level - tolerance).any())
        last_close = float(frame["close"].iloc[-1])

        buy_reclaimed = buy_swept and last_close < buy_side_level
        sell_reclaimed = sell_swept and last_close > sell_side_level
        reclaimed = buy_reclaimed or sell_reclaimed

        evidence: list[str] = []
        probability = 0.0
        sweep_type: SweepType = "none"
        sweep_level = 0.0

        if sell_swept and sell_reclaimed:
            probability = 0.82
            sweep_type = "sell_side_sweep"
            sweep_level = sell_side_level
            evidence.append(f"sell-side liquidity swept at {sell_side_level:.5f} and reclaimed")
        elif buy_swept and buy_reclaimed:
            probability = 0.82
            sweep_type = "buy_side_sweep"
            sweep_level = buy_side_level
            evidence.append(f"buy-side liquidity swept at {buy_side_level:.5f} and reclaimed")
        elif sell_swept and not sell_reclaimed:
            probability = 0.55
            sweep_type = "stop_hunt"
            sweep_level = sell_side_level
            evidence.append("downside stop hunt — awaiting reclaim")
        elif buy_swept and not buy_reclaimed:
            probability = 0.55
            sweep_type = "stop_hunt"
            sweep_level = buy_side_level
            evidence.append("upside stop hunt — awaiting reclaim")
        else:
            recent = frame.tail(12)
            wick_up = ((recent["high"] - recent[["open", "close"]].max(axis=1)) > tolerance).sum()
            wick_down = ((recent[["open", "close"]].min(axis=1) - recent["low"]) > tolerance).sum()
            if wick_up >= 2 and last_close < float(recent["high"].max()) - tolerance:
                probability = 0.45
                sweep_type = "sweep_failure"
                sweep_level = float(recent["high"].max())
                evidence.append("failed upside sweep — rejection wicks")
            elif wick_down >= 2 and last_close > float(recent["low"].min()) + tolerance:
                probability = 0.45
                sweep_type = "sweep_failure"
                sweep_level = float(recent["low"].min())
                evidence.append("failed downside sweep — rejection wicks")

        opportunity = self._trade_opportunity(sweep_type, reclaimed, buy_reclaimed, sell_reclaimed)

        return LiquiditySweepResult(
            symbol=symbol,
            timeframe=timeframe,
            liquidity_sweep_probability=round(probability, 3),
            sweep_type=sweep_type,
            sweep_level=sweep_level,
            reclaimed=reclaimed,
            buy_side_swept=buy_swept,
            sell_side_swept=sell_swept,
            explanation=(
                f"Sweep probability {probability:.0%} — {sweep_type.replace('_', ' ')}"
                + (" (reclaimed)" if reclaimed else "")
            ),
            evidence=tuple(evidence or ("No active sweep detected",)),
            trade_opportunity=opportunity,
        )

    @staticmethod
    def _trade_opportunity(
        sweep_type: SweepType,
        reclaimed: bool,
        buy_reclaimed: bool,
        sell_reclaimed: bool,
    ) -> str:
        if sell_reclaimed:
            return "Long on sell-side sweep reclaim — stops hunted, smart money accumulating"
        if buy_reclaimed:
            return "Short on buy-side sweep reclaim — stops hunted above highs"
        if sweep_type == "stop_hunt":
            return "Watch for reclaim — probe entry when price returns inside range"
        if sweep_type == "sweep_failure":
            return "Fade the failed sweep — trapped traders offer fuel"
        return "Map liquidity pools — scout sweep setups at range extremes"


__all__ = [
    "LiquiditySweepConfig",
    "LiquiditySweepEngine",
    "LiquiditySweepEngineError",
    "LiquiditySweepResult",
    "SweepType",
]
