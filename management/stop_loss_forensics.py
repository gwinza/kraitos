"""Stop-loss forensics — classify why protective stops were hit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import pandas as pd

from risk.stop_placement import liquidity_sweep_zone_levels

if TYPE_CHECKING:
    from brain.market_story_engine import MarketStory
    from strategies.models import MarketContext

StopLossClass = Literal[
    "too_tight",
    "inside_volatility",
    "inside_sweep_zone",
    "invalid_thesis_stop",
    "correct_stop",
]


@dataclass(frozen=True)
class StopForensicsConfig:
    """Thresholds for stop-loss classification."""

    tight_stop_atr: float = 0.45
    volatility_band_atr: float = 0.65
    sweep_zone_atr: float = 0.35
    thesis_invalidation_atr: float = 0.50
    too_tight_recovery_r: float = 0.35


@dataclass(frozen=True)
class StopForensicsInput:
    """Closed trade context for stop forensics."""

    symbol: str
    side: Literal["buy", "sell"]
    entry_price: float
    stop_loss: float
    exit_price: float
    exit_action: str
    r_multiple: float
    atr: float
    structure: MarketContext | None = None
    story: MarketStory | None = None
    candles_after_entry: pd.DataFrame | None = None


@dataclass(frozen=True)
class StopForensicsResult:
    """Classification and mentor notes for a stopped trade."""

    classification: StopLossClass
    explanation: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "classification": self.classification,
            "explanation": self.explanation,
            "confidence": round(self.confidence, 2),
        }


class StopLossForensics:
    """Classify whether a stop was placed correctly or violated structure rules."""

    def __init__(self, config: StopForensicsConfig | None = None) -> None:
        self.config = config or StopForensicsConfig()

    def classify(self, trade: StopForensicsInput) -> StopForensicsResult | None:
        """Return classification when trade exited via stop loss."""
        if not self._is_stop_exit(trade.exit_action, trade.r_multiple):
            return None

        cfg = self.config
        stop_dist = abs(trade.entry_price - trade.stop_loss)
        if stop_dist <= 0 or trade.atr <= 0:
            return StopForensicsResult(
                classification="invalid_thesis_stop",
                explanation="Stop distance undefined — thesis risk undefined",
                confidence=0.85,
            )

        stop_atr = stop_dist / trade.atr

        if self._invalid_thesis_stop(trade, stop_atr):
            return StopForensicsResult(
                classification="invalid_thesis_stop",
                explanation=(
                    "Stop placed on wrong side of story invalidation — "
                    "thesis level did not protect narrative"
                ),
                confidence=0.88,
            )

        if stop_atr <= cfg.tight_stop_atr:
            recovery = self._post_stop_recovery_r(trade)
            if recovery >= cfg.too_tight_recovery_r:
                return StopForensicsResult(
                    classification="too_tight",
                    explanation=(
                        f"Stop only {stop_atr:.2f} ATR — price recovered {recovery:.2f}R "
                        "after stop; structure had room beyond stop"
                    ),
                    confidence=0.82,
                )

        if self._inside_sweep_zone(trade):
            return StopForensicsResult(
                classification="inside_sweep_zone",
                explanation=(
                    "Stop sat inside recent liquidity sweep zone — "
                    "normal stop-hunt wick likely triggered exit"
                ),
                confidence=0.80,
            )

        if stop_atr <= cfg.volatility_band_atr:
            return StopForensicsResult(
                classification="inside_volatility",
                explanation=(
                    f"Stop at {stop_atr:.2f} ATR inside normal volatility band — "
                    "buffer insufficient beyond structure"
                ),
                confidence=0.75,
            )

        if self._thesis_genuinely_failed(trade):
            return StopForensicsResult(
                classification="correct_stop",
                explanation="Price violated story invalidation — stop protected capital correctly",
                confidence=0.85,
            )

        return StopForensicsResult(
            classification="correct_stop",
            explanation="Stop beyond structure; loss reflects valid thesis failure or chop",
            confidence=0.70,
        )

    @staticmethod
    def _is_stop_exit(exit_action: str, r_multiple: float) -> bool:
        action = (exit_action or "").lower()
        if "stop" in action or "cut_loss" in action:
            return True
        return r_multiple <= -0.85

    def _invalid_thesis_stop(self, trade: StopForensicsInput, stop_atr: float) -> bool:
        story = trade.story
        if story is None:
            return False

        if trade.side == "buy":
            if trade.stop_loss >= trade.entry_price:
                return True
            if story.direction == "bearish":
                return True
        else:
            if trade.stop_loss <= trade.entry_price:
                return True
            if story.direction == "bullish":
                return True
        _ = stop_atr
        return False

    def _inside_sweep_zone(self, trade: StopForensicsInput) -> bool:
        frame = trade.candles_after_entry
        if frame is None or len(frame) < 5:
            return False
        sweep_low, sweep_high = liquidity_sweep_zone_levels(frame, lookback=10)
        buffer = self.config.sweep_zone_atr * trade.atr
        stop = trade.stop_loss

        if trade.side == "buy":
            return stop >= sweep_low - buffer and stop <= sweep_low + buffer
        return stop <= sweep_high + buffer and stop >= sweep_high - buffer

    def _post_stop_recovery_r(self, trade: StopForensicsInput) -> float:
        frame = trade.candles_after_entry
        if frame is None or len(frame) < 2:
            return 0.0
        stop_dist = abs(trade.entry_price - trade.stop_loss)
        if stop_dist <= 0:
            return 0.0

        if trade.side == "buy":
            best = float(frame["high"].max())
            move = best - trade.exit_price
        else:
            best = float(frame["low"].min())
            move = trade.exit_price - best
        return max(0.0, move / stop_dist)

    def _thesis_genuinely_failed(self, trade: StopForensicsInput) -> bool:
        story = trade.story
        if story is None:
            return False
        inv = float(story.invalidation_level)
        if trade.side == "buy":
            return trade.exit_price <= inv
        return trade.exit_price >= inv


__all__ = [
    "StopForensicsConfig",
    "StopForensicsInput",
    "StopForensicsResult",
    "StopLossClass",
    "StopLossForensics",
]
