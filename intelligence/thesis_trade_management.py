"""
Thesis-based trade management — three-phase exit lifecycle and trade memory.

Phase 1 (thesis protection): exit only on invalidation before TP1.
Phase 2 (profit protection): ATR regret / trail after TP1.
Phase 3 (harvest): dynamic trails after TP2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

import pandas as pd

from strategies.models import MarketContext

ExitPhase = Literal["thesis_protection", "profit_protection", "harvest"]


@dataclass(frozen=True)
class ManagedTradeThesis:
    """Thesis contract stored at entry for lifecycle management."""

    story: str
    conviction_score: float
    conviction_level: str
    invalidators: tuple[str, ...]
    entry_reasons: tuple[str, ...]
    invalidation_level: float
    tp1_price: float
    tp2_price: float
    side: str


@dataclass
class OpportunityCostTracker:
    """Track whether confirmation adds or destroys edge."""

    missed_tp_count: int = 0
    missed_tp_r: float = 0.0
    avoided_loss_count: int = 0
    avoided_loss_r: float = 0.0
    skipped_low_conviction: int = 0

    @property
    def confirmation_expectancy(self) -> float:
        return self.avoided_loss_r - self.missed_tp_r

    def record_missed_winner(self, *, r_potential: float) -> None:
        self.missed_tp_count += 1
        self.missed_tp_r += r_potential

    def record_avoided_loser(self, *, r_avoided: float) -> None:
        self.avoided_loss_count += 1
        self.avoided_loss_r += r_avoided

    def record_skip(self) -> None:
        self.skipped_low_conviction += 1

    def summary(self) -> dict:
        return {
            "missed_tp_count": self.missed_tp_count,
            "missed_tp_r": round(self.missed_tp_r, 3),
            "avoided_loss_count": self.avoided_loss_count,
            "avoided_loss_r": round(self.avoided_loss_r, 3),
            "confirmation_expectancy": round(self.confirmation_expectancy, 3),
            "skipped_low_conviction": self.skipped_low_conviction,
        }


@dataclass
class TradeMemoryTracker:
    """Learn from premature exits, saved losses, and elite trades."""

    premature_exits: int = 0
    premature_would_tp: int = 0
    saved_losses: int = 0
    saved_from_sl: int = 0
    missed_elite: int = 0
    best_trade_r: float = 0.0
    worst_trade_r: float = 0.0
    exit_phase_counts: dict[str, int] = field(default_factory=dict)

    def record_premature_exit(self, *, would_have_tp: bool) -> None:
        self.premature_exits += 1
        if would_have_tp:
            self.premature_would_tp += 1

    def record_saved_loss(self, *, from_sl: bool) -> None:
        self.saved_losses += 1
        if from_sl:
            self.saved_from_sl += 1

    def record_outcome(self, *, r_multiple: float, phase: str) -> None:
        self.exit_phase_counts[phase] = self.exit_phase_counts.get(phase, 0) + 1
        if r_multiple > self.best_trade_r:
            self.best_trade_r = r_multiple
        if r_multiple < self.worst_trade_r:
            self.worst_trade_r = r_multiple

    def summary(self) -> dict:
        return {
            "premature_exits": self.premature_exits,
            "premature_would_tp": self.premature_would_tp,
            "saved_losses": self.saved_losses,
            "saved_from_sl": self.saved_from_sl,
            "missed_elite": self.missed_elite,
            "best_trade_r": round(self.best_trade_r, 3),
            "worst_trade_r": round(self.worst_trade_r, 3),
            "exit_phase_counts": dict(self.exit_phase_counts),
        }


_opportunity_tracker = OpportunityCostTracker()
_trade_memory = TradeMemoryTracker()
_lock = Lock()


def get_opportunity_cost_tracker() -> OpportunityCostTracker:
    return _opportunity_tracker


def get_trade_memory_tracker() -> TradeMemoryTracker:
    return _trade_memory


def reset_adaptive_trackers() -> None:
    global _opportunity_tracker, _trade_memory
    with _lock:
        _opportunity_tracker = OpportunityCostTracker()
        _trade_memory = TradeMemoryTracker()


def resolve_exit_phase(
    *,
    partial_taken: bool,
    tp2_taken: bool,
) -> ExitPhase:
    if tp2_taken:
        return "harvest"
    if partial_taken:
        return "profit_protection"
    return "thesis_protection"


def check_thesis_invalidation(
    *,
    side: str,
    current_price: float,
    invalidation_level: float,
    structure: MarketContext | None = None,
    candles_m15: pd.DataFrame | None = None,
) -> tuple[bool, str]:
    """
    Phase 1 exits — only thesis invalidation, not discomfort.

    Checks: invalidation level breach, H1 structure flip.
    """
    buffer = abs(invalidation_level) * 0.00005 if invalidation_level else 0.0

    if side == "buy":
        if current_price < invalidation_level - buffer:
            return True, "invalidation level breached"
        if structure is not None and structure.trend == "bearish":
            if structure.lower_highs and structure.lower_lows:
                return True, "H1 structure flipped bearish"
    else:
        if current_price > invalidation_level + buffer:
            return True, "invalidation level breached"
        if structure is not None and structure.trend == "bullish":
            if structure.higher_highs and structure.higher_lows:
                return True, "H1 structure flipped bullish"

    if candles_m15 is not None and len(candles_m15) >= 8:
        tail = candles_m15.tail(8)
        if side == "buy":
            swing_low = float(tail["low"].min())
            if current_price < swing_low:
                return True, "M15 swing low broken"
        else:
            swing_high = float(tail["high"].max())
            if current_price > swing_high:
                return True, "M15 swing high broken"

    return False, ""


__all__ = [
    "ExitPhase",
    "ManagedTradeThesis",
    "OpportunityCostTracker",
    "TradeMemoryTracker",
    "check_thesis_invalidation",
    "get_opportunity_cost_tracker",
    "get_trade_memory_tracker",
    "reset_adaptive_trackers",
    "resolve_exit_phase",
]
