"""Market acceptance — is the market accepting or rejecting the thesis?"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from strategies.market_reading_utils import atr_series, validate_candles

AcceptanceState = Literal[
    "accepting_bullish_thesis",
    "accepting_bearish_thesis",
    "rejecting_bullish_thesis",
    "rejecting_bearish_thesis",
    "undecided",
]


@dataclass(frozen=True)
class MarketAcceptanceResult:
    acceptance_state: AcceptanceState
    acceptance_score: int
    rejection_score: int
    time_to_acceptance: int | None
    explanation: str
    acceptance_evidence: tuple[str, ...] = field(default_factory=tuple)
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "acceptance_state": self.acceptance_state,
            "acceptance_score": self.acceptance_score,
            "rejection_score": self.rejection_score,
            "time_to_acceptance": self.time_to_acceptance,
            "explanation": self.explanation,
            "acceptance_evidence": list(self.acceptance_evidence),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class MarketAcceptanceConfig:
    min_candles: int = 15
    level_buffer_atr: float = 0.15
    reclaim_lookback: int = 8
    spread_penalty_pips: float = 3.0


class MarketAcceptanceEngine:
    """Determine whether price action accepts the proposed thesis."""

    def __init__(self, config: MarketAcceptanceConfig | None = None) -> None:
        self.config = config or MarketAcceptanceConfig()

    def evaluate(
        self,
        *,
        side: str,
        candles: pd.DataFrame | None = None,
        invalidation_level: float | None = None,
        structure: object | None = None,
        spread_pips: float | None = None,
        reclaim_level: float | None = None,
    ) -> MarketAcceptanceResult:
        evidence: list[str] = []
        acceptance = 48
        rejection = 52
        state: AcceptanceState = "undecided"
        time_to_acceptance: int | None = None

        if candles is None or candles.empty:
            return MarketAcceptanceResult(
                acceptance_state="undecided",
                acceptance_score=45,
                rejection_score=55,
                time_to_acceptance=None,
                explanation="Insufficient data for acceptance read",
                acceptance_evidence=("no candles",),
                evidence=("no candles",),
            )

        try:
            frame = validate_candles(
                candles, min_candles=self.config.min_candles, engine="MarketAcceptanceEngine"
            ).tail(40)
        except ValueError:
            return MarketAcceptanceResult(
                acceptance_state="undecided",
                acceptance_score=45,
                rejection_score=55,
                time_to_acceptance=None,
                explanation="Invalid candle data",
                acceptance_evidence=("invalid candles",),
                evidence=("invalid candles",),
            )

        atr = float(atr_series(frame).iloc[-1]) or 1e-9
        buf = atr * self.config.level_buffer_atr
        close = float(frame["close"].iloc[-1])
        prev_close = float(frame["close"].iloc[-2])
        open_px = float(frame["open"].iloc[-1])
        high = float(frame["high"].iloc[-1])
        low = float(frame["low"].iloc[-1])

        level = invalidation_level
        if level is None and structure is not None:
            if side == "buy" and getattr(structure, "swing_lows", ()):
                lows = getattr(structure, "swing_lows")
                if lows:
                    level = float(lows[-1].price if hasattr(lows[-1], "price") else lows[-1][1])
            elif side == "sell" and getattr(structure, "swing_highs", ()):
                highs = getattr(structure, "swing_highs")
                if highs:
                    level = float(highs[-1].price if hasattr(highs[-1], "price") else highs[-1][1])

        reclaim = reclaim_level if reclaim_level is not None else level
        lookback = self.config.reclaim_lookback

        if side == "buy":
            acceptance, rejection, state, evidence, tta = self._bullish_acceptance(
                frame=frame,
                close=close,
                prev_close=prev_close,
                open_px=open_px,
                high=high,
                low=low,
                level=level,
                reclaim=reclaim,
                buf=buf,
                atr=atr,
                structure=structure,
                lookback=lookback,
                acceptance=acceptance,
                rejection=rejection,
                state=state,
                evidence=evidence,
            )
            time_to_acceptance = tta
        else:
            acceptance, rejection, state, evidence, tta = self._bearish_acceptance(
                frame=frame,
                close=close,
                prev_close=prev_close,
                open_px=open_px,
                high=high,
                low=low,
                level=level,
                reclaim=reclaim,
                buf=buf,
                atr=atr,
                structure=structure,
                lookback=lookback,
                acceptance=acceptance,
                rejection=rejection,
                state=state,
                evidence=evidence,
            )
            time_to_acceptance = tta

        if spread_pips is not None and spread_pips > self.config.spread_penalty_pips:
            rejection += 8
            evidence.append(f"spread elevated ({spread_pips:.1f} pips) — acceptance discounted")
        elif spread_pips is not None and spread_pips <= 1.5:
            acceptance += 4
            evidence.append("spread acceptable")

        if state == "undecided":
            if acceptance > rejection + 8:
                state = (
                    "accepting_bullish_thesis"
                    if side == "buy"
                    else "accepting_bearish_thesis"
                )
            elif rejection > acceptance + 8:
                state = (
                    "rejecting_bullish_thesis"
                    if side == "buy"
                    else "rejecting_bearish_thesis"
                )

        acceptance = max(0, min(100, acceptance))
        rejection = max(0, min(100, rejection))
        explanation = (
            f"Acceptance {acceptance}/100 vs rejection {rejection}/100 — "
            f"{state.replace('_', ' ')}"
            + (f" (acceptance in ~{time_to_acceptance} bars)" if time_to_acceptance else "")
        )

        return MarketAcceptanceResult(
            acceptance_state=state,
            acceptance_score=acceptance,
            rejection_score=rejection,
            time_to_acceptance=time_to_acceptance,
            explanation=explanation,
            acceptance_evidence=tuple(evidence),
            evidence=tuple(evidence),
        )

    def _bullish_acceptance(
        self,
        *,
        frame: pd.DataFrame,
        close: float,
        prev_close: float,
        open_px: float,
        high: float,
        low: float,
        level: float | None,
        reclaim: float | None,
        buf: float,
        atr: float,
        structure: object | None,
        lookback: int,
        acceptance: int,
        rejection: int,
        state: AcceptanceState,
        evidence: list[str],
    ) -> tuple[int, int, AcceptanceState, list[str], int | None]:
        time_to_acceptance: int | None = None
        closes_above = 0
        closes_below = 0
        if level is not None:
            for idx in range(-lookback, 0):
                px = float(frame["close"].iloc[idx])
                if px > level + buf:
                    closes_above += 1
                elif px < level - buf:
                    closes_below += 1

            if reclaim is not None and close > reclaim + buf * 0.5:
                acceptance += 14
                evidence.append("price reclaims key level")
                for bars_back in range(1, lookback + 1):
                    if float(frame["close"].iloc[-bars_back]) <= reclaim:
                        time_to_acceptance = bars_back
                        break
            if reclaim is not None and close > reclaim and close > open_px:
                acceptance += 10
                evidence.append("candle closes above reclaim level")

            if closes_above >= 3 and close > level:
                acceptance += 22
                state = "accepting_bullish_thesis"
                evidence.append("sustained closes above invalidation — acceptance")
            elif closes_below >= 2 and close < level:
                rejection += 28
                state = "rejecting_bullish_thesis"
                evidence.append("failed reclaim — rejecting bullish thesis")
            elif close > prev_close and close > level - buf:
                acceptance += 10
                evidence.append("follow-through after level test")
            if low >= level - buf * 2 and close > level - buf:
                acceptance += 8
                evidence.append("pullback holds above invalidation")

        recent_high = float(frame["high"].tail(5).max())
        if close < recent_high - atr * 0.35 and close > prev_close:
            acceptance += 6
            evidence.append("bearish follow-through fails — buyers respond")

        if len(frame) >= 6:
            micro_lows = [float(frame["low"].iloc[i]) for i in range(-5, 0)]
            if micro_lows[-1] > min(micro_lows[:-1]):
                acceptance += 8
                evidence.append("micro higher low forms")
            mom = float(frame["close"].iloc[-1]) - float(frame["close"].iloc[-4])
            if mom > 0 and close > prev_close:
                acceptance += 6
                evidence.append("momentum restarts upward")

        hh = bool(getattr(structure, "higher_highs", False)) if structure else False
        hl = bool(getattr(structure, "higher_lows", False)) if structure else False
        lh = bool(getattr(structure, "lower_highs", False)) if structure else False
        ll = bool(getattr(structure, "lower_lows", False)) if structure else False
        if hh and hl:
            acceptance += 10
            evidence.append("structure supports bullish acceptance")
        elif lh or ll:
            rejection += 12
            evidence.append("structure conflicts with bullish thesis")

        return acceptance, rejection, state, evidence, time_to_acceptance

    def _bearish_acceptance(
        self,
        *,
        frame: pd.DataFrame,
        close: float,
        prev_close: float,
        open_px: float,
        high: float,
        low: float,
        level: float | None,
        reclaim: float | None,
        buf: float,
        atr: float,
        structure: object | None,
        lookback: int,
        acceptance: int,
        rejection: int,
        state: AcceptanceState,
        evidence: list[str],
    ) -> tuple[int, int, AcceptanceState, list[str], int | None]:
        time_to_acceptance: int | None = None
        closes_above = 0
        closes_below = 0
        if level is not None:
            for idx in range(-lookback, 0):
                px = float(frame["close"].iloc[idx])
                if px > level + buf:
                    closes_above += 1
                elif px < level - buf:
                    closes_below += 1

            if reclaim is not None and close < reclaim - buf * 0.5:
                acceptance += 14
                evidence.append("price rejects key level")
                for bars_back in range(1, lookback + 1):
                    if float(frame["close"].iloc[-bars_back]) >= reclaim:
                        time_to_acceptance = bars_back
                        break
            if reclaim is not None and close < reclaim and close < open_px:
                acceptance += 10
                evidence.append("candle closes below rejection level")

            if closes_below >= 3 and close < level:
                acceptance += 22
                state = "accepting_bearish_thesis"
                evidence.append("sustained closes below invalidation — acceptance")
            elif closes_above >= 2 and close > level:
                rejection += 28
                state = "rejecting_bearish_thesis"
                evidence.append("failed rejection — rejecting bearish thesis")
            elif close < prev_close and close < level + buf:
                acceptance += 10
                evidence.append("follow-through after level test")
            if high <= level + buf * 2 and close < level + buf:
                acceptance += 8
                evidence.append("rally fails below invalidation")

        recent_low = float(frame["low"].tail(5).min())
        if close > recent_low + atr * 0.35 and close < prev_close:
            acceptance += 6
            evidence.append("bullish follow-through fails — sellers respond")

        if len(frame) >= 6:
            micro_highs = [float(frame["high"].iloc[i]) for i in range(-5, 0)]
            if micro_highs[-1] < max(micro_highs[:-1]):
                acceptance += 8
                evidence.append("micro lower high forms")
            mom = float(frame["close"].iloc[-1]) - float(frame["close"].iloc[-4])
            if mom < 0 and close < prev_close:
                acceptance += 6
                evidence.append("momentum restarts downward")

        hh = bool(getattr(structure, "higher_highs", False)) if structure else False
        hl = bool(getattr(structure, "higher_lows", False)) if structure else False
        lh = bool(getattr(structure, "lower_highs", False)) if structure else False
        ll = bool(getattr(structure, "lower_lows", False)) if structure else False
        if lh and ll:
            acceptance += 10
            evidence.append("structure supports bearish acceptance")
        elif hh or hl:
            rejection += 12
            evidence.append("structure conflicts with bearish thesis")

        return acceptance, rejection, state, evidence, time_to_acceptance


__all__ = [
    "AcceptanceState",
    "MarketAcceptanceConfig",
    "MarketAcceptanceEngine",
    "MarketAcceptanceResult",
]
