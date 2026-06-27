"""Structural stop placement — beyond swings, liquidity, and story invalidation.

Stops sit outside normal volatility and sweep zones, not at arbitrary ATR distance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import pandas as pd

from core.helpers import pip_size_for_symbol

if TYPE_CHECKING:
    from brain.market_story_engine import MarketStory
    from execution.patience_engine import EntryType
    from strategies.models import MarketContext

Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class StopPlacementConfig:
    """Volatility and liquidity buffers for protective stops."""

    min_volatility_buffer_atr: float = 0.22
    max_volatility_buffer_atr: float = 0.55
    sweep_zone_buffer_atr: float = 0.18
    structure_buffer_pips: float = 5.0
    fallback_stop_pips: float = 20.0
    max_fallback_stop_pips: float = 50.0


def place_structural_stop(
    *,
    side: Side,
    entry_price: float,
    structure: MarketContext,
    symbol: str,
    atr: float,
    story: MarketStory | None = None,
    entry_type: EntryType | str | None = None,
    frame: pd.DataFrame | None = None,
    config: StopPlacementConfig | None = None,
) -> float:
    """
    Place stop beyond structure, liquidity sweep zones, volatility buffer,
    and market-story invalidation — never at a naked ATR multiple.
    """
    cfg = config or StopPlacementConfig()
    pip = pip_size_for_symbol(symbol)
    vol_buffer = _volatility_buffer(atr, cfg)
    struct_buffer = cfg.structure_buffer_pips * pip

    candidates: list[float] = []

    swing_stop = _swing_anchor_stop(
        side=side,
        entry_price=entry_price,
        structure=structure,
        pip=pip,
        struct_buffer=struct_buffer,
        cfg=cfg,
    )
    if swing_stop is not None:
        candidates.append(swing_stop)

    if frame is not None and len(frame) >= 3:
        sweep_stop = _liquidity_sweep_zone_stop(
            side=side,
            entry_price=entry_price,
            frame=frame,
            atr=atr,
            cfg=cfg,
            entry_type=entry_type,
        )
        if sweep_stop is not None:
            candidates.append(sweep_stop)

    if story is not None:
        inv = float(story.invalidation_level)
        if side == "buy" and inv < entry_price:
            candidates.append(inv - vol_buffer)
        elif side == "sell" and inv > entry_price:
            candidates.append(inv + vol_buffer)

    if frame is not None and entry_type == "compression_before_expansion" and len(frame) >= 4:
        if side == "buy":
            candidates.append(float(frame["low"].iloc[-4:].min()) - vol_buffer)
        else:
            candidates.append(float(frame["high"].iloc[-4:].max()) + vol_buffer)

    if not candidates:
        distance = cfg.fallback_stop_pips * pip
        if side == "buy":
            return entry_price - distance
        return entry_price + distance

    if side == "buy":
        valid = [c for c in candidates if c < entry_price]
        if not valid:
            return entry_price - cfg.fallback_stop_pips * pip
        stop = min(valid)
        if story is not None:
            inv = float(story.invalidation_level)
            if inv < entry_price:
                stop = min(stop, inv - vol_buffer)
        return stop

    valid = [c for c in candidates if c > entry_price]
    if not valid:
        return entry_price + cfg.fallback_stop_pips * pip
    stop = max(valid)
    if story is not None:
        inv = float(story.invalidation_level)
        if inv > entry_price:
            stop = max(stop, inv + vol_buffer)
    return stop


def liquidity_sweep_zone_levels(
    frame: pd.DataFrame,
    *,
    lookback: int = 12,
) -> tuple[float, float]:
    """Return (buy_side_sweep_low, sell_side_sweep_high) liquidity zone edges."""
    window = frame.tail(lookback)
    return float(window["low"].min()), float(window["high"].max())


def _volatility_buffer(atr: float, cfg: StopPlacementConfig) -> float:
    if atr <= 0:
        return 0.0
    return max(
        cfg.min_volatility_buffer_atr * atr,
        min(cfg.max_volatility_buffer_atr * atr, atr * 0.40),
    )


def _swing_anchor_stop(
    *,
    side: Side,
    entry_price: float,
    structure: MarketContext,
    pip: float,
    struct_buffer: float,
    cfg: StopPlacementConfig,
) -> float | None:
    max_dist = cfg.max_fallback_stop_pips * pip

    if side == "buy":
        anchors: list[float] = [s.price for s in structure.swing_lows if s.price < entry_price]
        anchors.extend(z.lower for z in structure.support_zones if z.lower < entry_price)
        if not anchors:
            return entry_price - cfg.fallback_stop_pips * pip
        anchor = anchors[-1]
        stop = anchor - struct_buffer
        return max(stop, entry_price - max_dist)

    anchors = [s.price for s in structure.swing_highs if s.price > entry_price]
    anchors.extend(z.upper for z in structure.resistance_zones if z.upper > entry_price)
    if not anchors:
        return entry_price + cfg.fallback_stop_pips * pip
    anchor = anchors[-1]
    stop = anchor + struct_buffer
    return min(stop, entry_price + max_dist)


def _liquidity_sweep_zone_stop(
    *,
    side: Side,
    entry_price: float,
    frame: pd.DataFrame,
    atr: float,
    cfg: StopPlacementConfig,
    entry_type: EntryType | str | None,
) -> float | None:
    sweep_low, sweep_high = liquidity_sweep_zone_levels(frame)
    pip = pip_size_for_symbol("EURUSD")  # fallback; buffer uses atr primarily
    buffer = cfg.sweep_zone_buffer_atr * atr + cfg.structure_buffer_pips * pip

    if side == "buy":
        zone_edge = sweep_low
        if entry_type == "liquidity_sweep_rejection":
            zone_edge = float(frame["low"].iloc[-3:].min())
        return zone_edge - buffer

    zone_edge = sweep_high
    if entry_type == "liquidity_sweep_rejection":
        zone_edge = float(frame["high"].iloc[-3:].max())
    return zone_edge + buffer


__all__ = [
    "StopPlacementConfig",
    "liquidity_sweep_zone_levels",
    "place_structural_stop",
]
