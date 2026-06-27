"""Conservative execution assumptions for backtest red-teaming.

OWNERSHIP: Auditor Brain only (`brains/auditor_brain.py`).

The Trader Brain generates trade intent without these pessimistic assumptions.
ConservativeBacktestEngine and AuditorBrain.apply_conservative_execution()
use this module for fill simulation. Never import from discovery layers
(intelligence/, strategies/, council/, portfolio/).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd

from backtesting.candle_resampler import PIPELINE_TIMEFRAMES
from core.helpers import pip_size_for_symbol
from paper_trading.virtual_account import OpenVirtualPosition

TIMEFRAME_MINUTES: dict[str, int] = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "H1": 60,
    "H4": 240,
    "H8": 480,
}


@dataclass(frozen=True)
class ExecutionCostConfig:
    """Configurable trading costs for conservative simulation."""

    spread_pips: float = 1.2
    commission_per_lot_round_turn: float = 7.0
    slippage_pips: float = 0.3
    sl_first_on_ambiguity: bool = True
    entry_on_next_bar: bool = True
    closed_candles_only: bool = True
    mark_open_at_backtest_end: bool = True


@dataclass(frozen=True)
class PendingEntry:
    """Trade signal queued for next-bar open fill."""

    fill_moment: datetime
    signal: object
    symbol: str


def bar_close_time(open_time: pd.Timestamp, timeframe: str) -> pd.Timestamp:
    """Return the UTC close timestamp for a left-labeled OHLC bar."""
    minutes = TIMEFRAME_MINUTES.get(timeframe, 60)
    return open_time + pd.Timedelta(minutes=minutes)


def slice_closed_candles(
    candles: dict[str, pd.DataFrame],
    moment: datetime,
) -> dict[str, pd.DataFrame]:
    """
    Return only fully closed candles as of ``moment``.

    Higher timeframe bars whose period has not yet completed are excluded,
    preventing partial-period lookahead from future M1 data.
    """
    cutoff = pd.Timestamp(moment)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")

    sliced: dict[str, pd.DataFrame] = {}
    for timeframe in PIPELINE_TIMEFRAMES:
        frame = candles.get(timeframe)
        if frame is None or frame.empty:
            sliced[timeframe] = frame if frame is not None else pd.DataFrame()
            continue

        times = pd.to_datetime(frame["time"], utc=True)
        minutes = TIMEFRAME_MINUTES.get(timeframe, 60)
        close_times = times + pd.Timedelta(minutes=minutes)
        mask = close_times <= cutoff
        sliced[timeframe] = frame.loc[mask].copy()
    return sliced


def slice_inclusive_candles(
    candles: dict[str, pd.DataFrame],
    moment: datetime,
) -> dict[str, pd.DataFrame]:
    """Optimistic slice used by the default engine (may include forming bars)."""
    cutoff = pd.Timestamp(moment)
    sliced: dict[str, pd.DataFrame] = {}
    for timeframe in PIPELINE_TIMEFRAMES:
        frame = candles.get(timeframe)
        if frame is None or frame.empty:
            sliced[timeframe] = frame if frame is not None else pd.DataFrame()
            continue
        times = pd.to_datetime(frame["time"], utc=True)
        sliced[timeframe] = frame.loc[times <= cutoff].copy()
    return sliced


@dataclass(frozen=True)
class PositionExitEvent:
    """Resolved exit event for a simulated position."""

    price: float
    reason: str
    partial: bool = False
    fraction: float = 1.0
    move_stop_to_breakeven: bool = False
    runner_tp: float | None = None


def resolve_exit_price(
    position: OpenVirtualPosition,
    *,
    high: float,
    low: float,
    sl_first: bool = True,
) -> tuple[float | None, str]:
    """Backward-compatible wrapper returning price and reason only."""
    event = resolve_position_exit(position, high=high, low=low, sl_first=sl_first)
    if event is None:
        return None, ""
    return event.price, event.reason


def resolve_position_exit(
    position: OpenVirtualPosition,
    *,
    high: float,
    low: float,
    sl_first: bool = True,
) -> PositionExitEvent | None:
    """
    Resolve stop, partial, or take-profit exit on a completed bar.

    When both levels are touched, stop loss is assumed first (conservative).
    """
    if position.direction == "buy":
        stop_hit = low <= position.stop_loss
        partial_tp = position.partial_tp if not position.partial_taken else None
        partial_hit = partial_tp is not None and high >= partial_tp
        tp_level = position.take_profit
        tp_hit = tp_level is not None and high >= tp_level

        if stop_hit and (partial_hit or tp_hit) and sl_first:
            return PositionExitEvent(position.stop_loss, "stop_loss")
        if stop_hit:
            return PositionExitEvent(position.stop_loss, "stop_loss")
        if partial_hit and not position.partial_taken:
            return PositionExitEvent(
                partial_tp,  # type: ignore[arg-type]
                "partial_take_profit",
                partial=True,
                fraction=position.partial_fraction,
                move_stop_to_breakeven=position.move_stop_to_breakeven,
                runner_tp=position.runner_tp or position.take_profit,
            )
        if tp_hit:
            return PositionExitEvent(tp_level, "take_profit")  # type: ignore[arg-type]
    else:
        stop_hit = high >= position.stop_loss
        partial_tp = position.partial_tp if not position.partial_taken else None
        partial_hit = partial_tp is not None and low <= partial_tp
        tp_level = position.take_profit
        tp_hit = tp_level is not None and low <= tp_level

        if stop_hit and (partial_hit or tp_hit) and sl_first:
            return PositionExitEvent(position.stop_loss, "stop_loss")
        if stop_hit:
            return PositionExitEvent(position.stop_loss, "stop_loss")
        if partial_hit and not position.partial_taken:
            return PositionExitEvent(
                partial_tp,  # type: ignore[arg-type]
                "partial_take_profit",
                partial=True,
                fraction=position.partial_fraction,
                move_stop_to_breakeven=position.move_stop_to_breakeven,
                runner_tp=position.runner_tp or position.take_profit,
            )
        if tp_hit:
            return PositionExitEvent(tp_level, "take_profit")  # type: ignore[arg-type]
    return None


def entry_fill_price(
    *,
    direction: str,
    open_price: float,
    symbol: str,
    costs: ExecutionCostConfig,
) -> float:
    """Fill at next bar open with spread and slippage working against the trader."""
    pip_size = pip_size_for_symbol(symbol)
    spread_half = costs.spread_pips * pip_size / 2.0
    slippage = costs.slippage_pips * pip_size
    if direction == "buy":
        return open_price + spread_half + slippage
    return open_price - spread_half - slippage


def exit_fill_price(
    *,
    direction: str,
    raw_price: float,
    symbol: str,
    costs: ExecutionCostConfig,
) -> float:
    """Apply spread/slippage on exit."""
    pip_size = pip_size_for_symbol(symbol)
    spread_half = costs.spread_pips * pip_size / 2.0
    slippage = costs.slippage_pips * pip_size
    if direction == "buy":
        return raw_price - spread_half - slippage
    return raw_price + spread_half + slippage


def commission_cost(lot_size: float, costs: ExecutionCostConfig) -> float:
    """Round-turn commission charged on open and close."""
    return costs.commission_per_lot_round_turn * lot_size


def next_bar_open(moment: datetime, timeframe: str) -> datetime:
    """Return the open time of the bar immediately after ``moment``."""
    minutes = TIMEFRAME_MINUTES.get(timeframe, 60)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment + timedelta(minutes=minutes)
