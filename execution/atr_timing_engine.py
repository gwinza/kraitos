"""
ATR-normalized entry timing and exit management.

Entry: 3-candle consolidation OR 30–50% retracement of the latest 5-bar impulse.
Exit: ATR regret trailing, 20-bar extreme grace, EMA12/EMA50 slope override.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

CONSOLIDATION_BARS = 3
CONSOLIDATION_RANGE_ATR = 1.0
IMPULSE_BARS = 5
RETRACE_MIN = 0.30
RETRACE_MAX = 0.50
MIN_IMPULSE_ATR = 0.25
EXTREME_GRACE_BARS = 20
EXTREME_GRACE_BUFFER_ATR = 0.20
REGRET_TRAIL_ATR = 1.5
REGRET_EXIT_ATR = 2.25
MIN_PEAK_R_FOR_REGRET_EXIT = 0.30
REGRET_EXIT_DEEP_LOSS_R = -0.20
TRAIL_STOP_ATR = 0.75
EMA_FAST = 12
EMA_SLOW = 50
ExitPhase = Literal["thesis_protection", "profit_protection", "harvest"]
ATR_PERIOD = 14


@dataclass(frozen=True)
class EntryTimingResult:
    allowed: bool
    reason: str
    trigger: Literal["consolidation", "retracement", "none"] = "none"


@dataclass(frozen=True)
class ExitTimingResult:
    action: Literal["HOLD", "EXIT", "TRAIL"]
    reason: str
    new_stop: float | None = None


def compute_atr(candles: pd.DataFrame, period: int = ATR_PERIOD) -> float:
    if candles is None or len(candles) < 2:
        return 0.0
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    close = candles["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    window = min(period, len(tr))
    atr = float(tr.tail(window).mean())
    return atr if atr > 0 else float(tr.iloc[-1])


def should_enter(
    *,
    side: str,
    candles: pd.DataFrame | None,
    atr: float | None = None,
) -> EntryTimingResult:
    """Wait for consolidation or impulse retracement before entering."""
    if candles is None or len(candles) < IMPULSE_BARS + CONSOLIDATION_BARS:
        return EntryTimingResult(
            allowed=False,
            reason="insufficient bars for ATR entry timing",
            trigger="none",
        )

    vol = atr if atr is not None and atr > 0 else compute_atr(candles)
    if vol <= 0:
        return EntryTimingResult(
            allowed=False,
            reason="ATR unavailable",
            trigger="none",
        )

    if _consolidation_ok(candles, vol):
        return EntryTimingResult(
            allowed=True,
            reason=f"{CONSOLIDATION_BARS}-bar consolidation <= {CONSOLIDATION_RANGE_ATR:.1f} ATR",
            trigger="consolidation",
        )

    retrace = _retracement_ok(side=side, candles=candles, atr=vol)
    if retrace.allowed:
        return retrace

    return EntryTimingResult(
        allowed=False,
        reason="await consolidation or 30–50% impulse retracement",
        trigger="none",
    )


def should_exit(
    *,
    side: str,
    entry_price: float,
    current_price: float,
    stop_loss: float,
    candles: pd.DataFrame | None,
    bars_since_entry: int,
    best_price: float,
    atr: float | None = None,
    partial_taken: bool = False,
    exit_phase: ExitPhase = "thesis_protection",
) -> ExitTimingResult:
    """Three-phase exit: thesis protection → profit protection → harvest."""
    if exit_phase == "thesis_protection":
        return ExitTimingResult(
            action="HOLD",
            reason="thesis protection — hold for invalidation or TP1 only",
        )

    if candles is None or len(candles) < EMA_SLOW + 2:
        return ExitTimingResult(action="HOLD", reason="insufficient bars for ATR exit")

    vol = atr if atr is not None and atr > 0 else compute_atr(candles)
    if vol <= 0:
        return ExitTimingResult(action="HOLD", reason="ATR unavailable")

    regret_exit_atr = REGRET_EXIT_ATR
    if exit_phase == "harvest":
        regret_exit_atr *= 1.15

    ema_hold = _ema_slope_supports(side, candles, vol)

    if exit_phase == "profit_protection" and bars_since_entry <= EXTREME_GRACE_BARS:
        return ExitTimingResult(
            action="HOLD",
            reason="profit protection — post-TP1 grace",
        )

    regret = _regret_distance(side, best_price, current_price)
    regret_r = regret / vol
    progress = _progress_r(side, entry_price, stop_loss, current_price)
    peak_r = _progress_r(side, entry_price, stop_loss, best_price)

    regret_exit_eligible = (
        peak_r >= MIN_PEAK_R_FOR_REGRET_EXIT
        or progress <= REGRET_EXIT_DEEP_LOSS_R
    )
    if (
        regret_r >= regret_exit_atr
        and not ema_hold
        and regret_exit_eligible
    ):
        return ExitTimingResult(
            action="EXIT",
            reason=f"ATR regret trail ({regret_r:.2f} ATR from best)",
        )

    if regret_r >= REGRET_TRAIL_ATR * 0.65 and ema_hold:
        new_stop = _trail_stop(side, current_price, vol, stop_loss)
        if new_stop is not None:
            return ExitTimingResult(
                action="TRAIL",
                reason="EMA slope holds — tightening ATR trail",
                new_stop=new_stop,
            )

    if (
        regret_r >= REGRET_TRAIL_ATR * 0.85
        and not ema_hold
        and regret_r < regret_exit_atr
    ):
        new_stop = _trail_stop(side, current_price, vol, stop_loss)
        if new_stop is not None:
            return ExitTimingResult(
                action="TRAIL",
                reason="regret building — ATR trail",
                new_stop=new_stop,
            )

    if progress >= 0.50 and exit_phase == "profit_protection" and not partial_taken:
        new_stop = _breakeven_stop(side, entry_price, vol, stop_loss)
        if new_stop is not None:
            return ExitTimingResult(
                action="TRAIL",
                reason=">=0.50R progress — breakeven buffer",
                new_stop=new_stop,
            )

    return ExitTimingResult(action="HOLD", reason="hold — no exit trigger")


def _consolidation_ok(candles: pd.DataFrame, atr: float) -> bool:
    tail = candles.tail(CONSOLIDATION_BARS)
    total_range = float(tail["high"].max() - tail["low"].min())
    return total_range <= CONSOLIDATION_RANGE_ATR * atr


def _retracement_ok(
    *,
    side: str,
    candles: pd.DataFrame,
    atr: float,
) -> EntryTimingResult:
    window = candles.tail(IMPULSE_BARS + 1)
    impulse = window.iloc[:-1]
    current = float(window.iloc[-1]["close"])

    impulse_high = float(impulse["high"].max())
    impulse_low = float(impulse["low"].min())
    move = impulse_high - impulse_low
    if move < MIN_IMPULSE_ATR * atr:
        return EntryTimingResult(
            allowed=False,
            reason="impulse too small vs ATR",
            trigger="none",
        )

    if side == "buy":
        if float(impulse.iloc[-1]["close"]) <= float(impulse.iloc[0]["open"]):
            return EntryTimingResult(
                allowed=False,
                reason="no bullish 5-bar impulse",
                trigger="none",
            )
        ratio = (impulse_high - current) / move
    else:
        if float(impulse.iloc[-1]["close"]) >= float(impulse.iloc[0]["open"]):
            return EntryTimingResult(
                allowed=False,
                reason="no bearish 5-bar impulse",
                trigger="none",
            )
        ratio = (current - impulse_low) / move

    if RETRACE_MIN <= ratio <= RETRACE_MAX:
        return EntryTimingResult(
            allowed=True,
            reason=f"impulse retracement {ratio:.0%} of {IMPULSE_BARS}-bar move",
            trigger="retracement",
        )
    return EntryTimingResult(
        allowed=False,
        reason=f"retracement {ratio:.0%} outside {RETRACE_MIN:.0%}–{RETRACE_MAX:.0%}",
        trigger="none",
    )


def _regret_distance(side: str, best_price: float, current_price: float) -> float:
    if side == "buy":
        return max(0.0, best_price - current_price)
    return max(0.0, current_price - best_price)


def _progress_r(
    side: str,
    entry_price: float,
    stop_loss: float,
    current_price: float,
) -> float:
    risk = abs(entry_price - stop_loss)
    if risk <= 0:
        return 0.0
    if side == "buy":
        return (current_price - entry_price) / risk
    return (entry_price - current_price) / risk


def _extreme_grace_broken(
    *,
    side: str,
    current_price: float,
    candles: pd.DataFrame,
    atr: float,
) -> bool:
    tail = candles.tail(EXTREME_GRACE_BARS)
    buffer = EXTREME_GRACE_BUFFER_ATR * atr
    if side == "buy":
        floor = float(tail["low"].min())
        return current_price < floor - buffer
    ceiling = float(tail["high"].max())
    return current_price > ceiling + buffer


def _ema_slope_supports(side: str, candles: pd.DataFrame, atr: float) -> bool:
    close = candles["close"].astype(float)
    ema12 = close.ewm(span=EMA_FAST, adjust=False).mean()
    ema50 = close.ewm(span=EMA_SLOW, adjust=False).mean()
    if len(ema12) < 4:
        return False
    slope12 = (float(ema12.iloc[-1]) - float(ema12.iloc[-3])) / atr
    slope50 = (float(ema50.iloc[-1]) - float(ema50.iloc[-3])) / atr
    if side == "buy":
        return slope12 > -0.02 and slope50 >= -0.10
    return slope12 < 0.02 and slope50 <= 0.10


def _trail_stop(
    side: str,
    current_price: float,
    atr: float,
    stop_loss: float,
) -> float | None:
    if side == "buy":
        candidate = current_price - TRAIL_STOP_ATR * atr
        return candidate if candidate > stop_loss else None
    candidate = current_price + TRAIL_STOP_ATR * atr
    return candidate if candidate < stop_loss else None


def _breakeven_stop(
    side: str,
    entry_price: float,
    atr: float,
    stop_loss: float,
) -> float | None:
    buffer = 0.10 * atr
    if side == "buy":
        candidate = entry_price + buffer
        return candidate if candidate > stop_loss else None
    candidate = entry_price - buffer
    return candidate if candidate < stop_loss else None


__all__ = [
    "EntryTimingResult",
    "ExitPhase",
    "ExitTimingResult",
    "compute_atr",
    "should_enter",
    "should_exit",
]
