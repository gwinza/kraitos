"""Adaptive exit engine — manage open trades from live market behaviour.

Replaces rigid exit schedules with dynamic responses to trend, volatility,
momentum, liquidity, and thesis health. Protects profit without cutting
strong trades too early.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from brain.market_story_engine import MarketStory
from execution.atr_timing_engine import compute_atr
from intelligence.thesis_trade_management import check_thesis_invalidation
from strategies.market_reading_utils import validate_candles
from strategies.models import MarketContext

ExitAction = Literal["HOLD", "SCALE_OUT", "TRAIL", "EXIT"]
Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class ExitDecision:
    """Adaptive exit recommendation for one open trade."""

    action: ExitAction
    stop_level: float | None
    reasoning: str
    scale_fraction: float | None = None

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "stop_level": round(self.stop_level, 5) if self.stop_level is not None else None,
            "reasoning": self.reasoning,
            "scale_fraction": self.scale_fraction,
        }


@dataclass(frozen=True)
class OpenTradeSnapshot:
    """Minimal open-trade state for adaptive exit evaluation."""

    symbol: str
    side: Side
    entry_price: float
    stop_loss: float
    current_price: float
    best_price: float | None = None
    invalidation_level: float | None = None
    liquidity_targets: tuple[float, ...] = ()
    partial_taken: bool = False
    bars_since_entry: int = 0


@dataclass(frozen=True)
class AdaptiveExitConfig:
    """Volatility-normalised behaviour thresholds."""

    min_candles: int = 20
    liquidity_touch_atr: float = 0.22
    momentum_collapse_atr: float = 1.15
    acceleration_momentum_delta: float = 0.35
    weakening_momentum_delta: float = -0.25
    favorable_vol_expansion: float = 1.18
    trail_tight_atr: float = 0.65
    trail_normal_atr: float = 0.90
    trail_room_atr: float = 1.35
    scale_out_fraction: float = 0.50
    min_profit_r_to_trail: float = 0.35
    min_profit_r_to_scale: float = 0.80


@dataclass(frozen=True)
class _MarketBehaviour:
    atr: float
    current_r: float
    peak_r: float
    trend_accelerating: bool
    trend_weakening: bool
    vol_favorable: bool
    momentum_collapsing: bool
    at_major_liquidity: bool
    liquidity_label: str


class AdaptiveExitEngine:
    """Evaluate open trades against live price behaviour."""

    def __init__(self, config: AdaptiveExitConfig | None = None) -> None:
        self.config = config or AdaptiveExitConfig()

    def evaluate(
        self,
        *,
        trade: OpenTradeSnapshot,
        candles: pd.DataFrame,
        structure: MarketContext | None = None,
        story: MarketStory | None = None,
    ) -> ExitDecision:
        """Return the best adaptive exit action for the current bar."""
        invalidation = self._invalidation_level(trade, story)
        liquidity_targets = self._liquidity_targets(trade, story)

        if self._hard_stop_hit(trade):
            return ExitDecision(
                action="EXIT",
                stop_level=trade.stop_loss,
                reasoning="Hard stop breached — exit immediately",
            )

        invalidated, inv_reason = check_thesis_invalidation(
            side=trade.side,
            current_price=trade.current_price,
            invalidation_level=invalidation,
            structure=structure,
            candles_m15=candles if len(candles) >= 8 else None,
        )
        if invalidated:
            return ExitDecision(
                action="EXIT",
                stop_level=trade.stop_loss,
                reasoning=f"Thesis invalidated — {inv_reason}",
            )

        try:
            frame = validate_candles(
                candles, min_candles=self.config.min_candles, engine="AdaptiveExitEngine"
            )
        except ValueError as exc:
            return ExitDecision(
                action="HOLD",
                stop_level=trade.stop_loss,
                reasoning=f"Awaiting more price data: {exc}",
            )

        behaviour = self._read_behaviour(
            trade=trade,
            frame=frame,
            structure=structure,
            liquidity_targets=liquidity_targets,
        )

        if behaviour.momentum_collapsing and (
            behaviour.current_r <= -0.25
            or (behaviour.current_r < 0 and behaviour.peak_r >= 0.35)
        ):
            return ExitDecision(
                action="EXIT",
                stop_level=trade.stop_loss,
                reasoning=(
                    "Momentum collapsed against the position — cut before thesis drifts further"
                ),
            )

        if behaviour.at_major_liquidity:
            if behaviour.trend_accelerating and behaviour.current_r >= self.config.min_profit_r_to_scale:
                fraction = self.config.scale_out_fraction if not trade.partial_taken else 1.0
                action: ExitAction = "SCALE_OUT" if fraction < 1.0 else "EXIT"
                return ExitDecision(
                    action=action,
                    stop_level=self._trail_stop(
                        trade, behaviour.atr, self.config.trail_room_atr
                    ),
                    reasoning=(
                        f"Major liquidity reached ({behaviour.liquidity_label}) with trend "
                        f"still accelerating — bank {fraction:.0%} and let runner breathe"
                    ),
                    scale_fraction=None if action == "EXIT" else fraction,
                )
            if behaviour.current_r >= self.config.min_profit_r_to_scale:
                return ExitDecision(
                    action="SCALE_OUT" if not trade.partial_taken else "EXIT",
                    stop_level=self._trail_stop(trade, behaviour.atr, self.config.trail_tight_atr),
                    reasoning=(
                        f"Price at major liquidity ({behaviour.liquidity_label}) — "
                        "scale out into resting orders"
                    ),
                    scale_fraction=None if trade.partial_taken else self.config.scale_out_fraction,
                )

        if behaviour.momentum_collapsing and behaviour.current_r > 0:
            return ExitDecision(
                action="SCALE_OUT" if not trade.partial_taken else "TRAIL",
                stop_level=self._trail_stop(trade, behaviour.atr, self.config.trail_tight_atr),
                reasoning="Momentum fading after progress — reduce exposure before give-back",
                scale_fraction=None if trade.partial_taken else 0.35,
            )

        if behaviour.trend_weakening and behaviour.current_r >= self.config.min_profit_r_to_trail:
            tightened = self._trail_stop(trade, behaviour.atr, self.config.trail_tight_atr)
            if tightened is not None and tightened != trade.stop_loss:
                return ExitDecision(
                    action="TRAIL",
                    stop_level=tightened,
                    reasoning=(
                        "Trend sponsorship weakening — tighten trail to protect open profit"
                    ),
                )

        if behaviour.trend_accelerating and behaviour.current_r > 0:
            room_stop = self._trail_stop(trade, behaviour.atr, self.config.trail_room_atr)
            return ExitDecision(
                action="HOLD",
                stop_level=room_stop or trade.stop_loss,
                reasoning=(
                    "Trend accelerating in favour — hold for extension with wider volatility room"
                ),
            )

        if behaviour.vol_favorable and behaviour.current_r > 0:
            room_stop = self._trail_stop(trade, behaviour.atr, self.config.trail_normal_atr)
            return ExitDecision(
                action="HOLD",
                stop_level=room_stop or trade.stop_loss,
                reasoning=(
                    "Volatility expanding with the trade — give price room, avoid premature exit"
                ),
            )

        if behaviour.current_r >= 1.0 and not behaviour.trend_weakening:
            trail = self._trail_stop(trade, behaviour.atr, self.config.trail_normal_atr)
            if trail is not None and trail != trade.stop_loss:
                return ExitDecision(
                    action="TRAIL",
                    stop_level=trail,
                    reasoning="Trade working — structure trail to protect profit without capping upside",
                )

        return ExitDecision(
            action="HOLD",
            stop_level=trade.stop_loss,
            reasoning="Live behaviour stable — hold while thesis remains intact",
        )

    def _read_behaviour(
        self,
        *,
        trade: OpenTradeSnapshot,
        frame: pd.DataFrame,
        structure: MarketContext | None,
        liquidity_targets: tuple[float, ...],
    ) -> _MarketBehaviour:
        cfg = self.config
        atr = compute_atr(frame)
        if atr <= 0:
            atr = float((frame["high"] - frame["low"]).tail(14).mean()) or 0.0001

        risk = abs(trade.entry_price - trade.stop_loss) or atr
        current_r = self._current_r(trade, risk)
        peak_r = self._peak_r(trade, risk)

        recent = frame.tail(3)
        prior = frame.iloc[-6:-3] if len(frame) >= 6 else frame.iloc[:-3]
        recent_mom = self._directional_momentum(trade.side, recent, atr)
        prior_mom = self._directional_momentum(trade.side, prior, atr) if len(prior) >= 2 else 0.0
        mom_delta = recent_mom - prior_mom

        trend_accelerating = (
            recent_mom > 0.4
            and (mom_delta >= cfg.acceleration_momentum_delta or recent_mom > prior_mom * 1.25)
        )
        trend_weakening = mom_delta <= cfg.weakening_momentum_delta or self._structure_against(
            trade.side, structure
        )

        recent_range = float(recent["high"].max() - recent["low"].min())
        prior_range = float(prior["high"].max() - prior["low"].min()) if len(prior) >= 3 else recent_range
        vol_ratio = recent_range / max(prior_range, atr * 0.5)
        vol_favorable = vol_ratio >= cfg.favorable_vol_expansion and recent_mom > 0

        momentum_collapsing = self._momentum_collapsing(trade.side, frame, atr)

        at_liq, label = self._near_liquidity(trade, liquidity_targets, atr)

        if trend_accelerating:
            trend_weakening = False

        return _MarketBehaviour(
            atr=atr,
            current_r=current_r,
            peak_r=peak_r,
            trend_accelerating=trend_accelerating,
            trend_weakening=trend_weakening,
            vol_favorable=vol_favorable,
            momentum_collapsing=momentum_collapsing,
            at_major_liquidity=at_liq,
            liquidity_label=label,
        )

    @staticmethod
    def _invalidation_level(trade: OpenTradeSnapshot, story: MarketStory | None) -> float:
        if trade.invalidation_level is not None and trade.invalidation_level > 0:
            return trade.invalidation_level
        if story is not None and story.invalidation_level > 0:
            return story.invalidation_level
        return trade.stop_loss

    @staticmethod
    def _liquidity_targets(
        trade: OpenTradeSnapshot, story: MarketStory | None
    ) -> tuple[float, ...]:
        if trade.liquidity_targets:
            return trade.liquidity_targets
        if story is None:
            return ()
        return tuple(target.price for target in story.liquidity_targets)

    @staticmethod
    def _hard_stop_hit(trade: OpenTradeSnapshot) -> bool:
        if trade.side == "buy":
            return trade.current_price <= trade.stop_loss
        return trade.current_price >= trade.stop_loss

    @staticmethod
    def _current_r(trade: OpenTradeSnapshot, risk: float) -> float:
        if trade.side == "buy":
            return (trade.current_price - trade.entry_price) / risk
        return (trade.entry_price - trade.current_price) / risk

    @staticmethod
    def _peak_r(trade: OpenTradeSnapshot, risk: float) -> float:
        best = trade.best_price if trade.best_price is not None else trade.current_price
        if trade.side == "buy":
            return (best - trade.entry_price) / risk
        return (trade.entry_price - best) / risk

    @staticmethod
    def _directional_momentum(side: Side, frame: pd.DataFrame, atr: float) -> float:
        if len(frame) < 2:
            return 0.0
        delta = float(frame["close"].iloc[-1]) - float(frame["close"].iloc[0])
        signed = delta if side == "buy" else -delta
        return signed / max(atr, 1e-9)

    @staticmethod
    def _structure_against(side: Side, structure: MarketContext | None) -> bool:
        if structure is None:
            return False
        if side == "buy":
            return structure.trend == "bearish" and structure.lower_highs and structure.lower_lows
        return structure.trend == "bullish" and structure.higher_highs and structure.higher_lows

    def _momentum_collapsing(self, side: Side, frame: pd.DataFrame, atr: float) -> bool:
        tail = frame.tail(4)
        if len(tail) < 3:
            return False
        against = 0
        min_move = atr * 0.20
        closes = tail["close"].astype(float).values
        for i in range(len(tail)):
            row = tail.iloc[i]
            o = float(row["open"])
            c = float(row["close"])
            rng = float(row["high"]) - float(row["low"])
            if side == "buy" and c < o - min_move * 0.25:
                against += 1
            elif side == "sell" and c > o + min_move * 0.25:
                against += 1
            elif rng >= self.config.momentum_collapse_atr * atr * 0.45:
                if side == "buy" and c < o:
                    against += 1
                elif side == "sell" and c > o:
                    against += 1
        if against >= 2:
            return True
        if side == "buy":
            down_closes = sum(
                1 for i in range(1, len(closes)) if closes[i] < closes[i - 1] - min_move
            )
            return down_closes >= 2
        up_closes = sum(
            1 for i in range(1, len(closes)) if closes[i] > closes[i - 1] + min_move
        )
        return up_closes >= 2

    def _near_liquidity(
        self,
        trade: OpenTradeSnapshot,
        targets: tuple[float, ...],
        atr: float,
    ) -> tuple[bool, str]:
        if not targets:
            return False, ""
        price = trade.current_price
        tolerance = self.config.liquidity_touch_atr * atr
        relevant = [
            level
            for level in targets
            if (trade.side == "buy" and level >= trade.entry_price)
            or (trade.side == "sell" and level <= trade.entry_price)
        ]
        if not relevant:
            relevant = list(targets)
        nearest = min(relevant, key=lambda level: abs(level - price))
        if abs(nearest - price) <= tolerance:
            return True, f"{nearest:.5f}"
        return False, ""

    def _trail_stop(
        self,
        trade: OpenTradeSnapshot,
        atr: float,
        multiplier: float,
    ) -> float | None:
        buffer = multiplier * atr
        if trade.side == "buy":
            candidate = trade.current_price - buffer
            if candidate <= trade.stop_loss:
                return None
            return round(candidate, 5)
        candidate = trade.current_price + buffer
        if candidate >= trade.stop_loss:
            return None
        return round(candidate, 5)


__all__ = [
    "AdaptiveExitConfig",
    "AdaptiveExitEngine",
    "ExitAction",
    "ExitDecision",
    "OpenTradeSnapshot",
]
