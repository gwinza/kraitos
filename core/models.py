"""Orchestrator runtime models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from execution.models import EntryDecision
    from strategies.models import (
        HarvestDecision,
        MarketContext,
        MicroScalpSignal,
        MultiTimeframeBiasResult,
        RegimeResult,
    )


@dataclass
class SymbolCycleState:
    """Mutable state accumulated while processing one symbol in a cycle."""

    symbol: str
    trace_id: str
    candles: dict[str, pd.DataFrame] = field(default_factory=dict)
    bid: float = 0.0
    ask: float = 0.0
    spread_pips: float = 0.0
    spread_limit: float = 2.0
    regime: RegimeResult | None = None
    bias: MultiTimeframeBiasResult | None = None
    structure: MarketContext | None = None
    harvest: HarvestDecision | None = None
    micro_scalp: MicroScalpSignal | None = None
    news_allowed: bool = True
    news_reason: str = ""
    pair_allowed: bool = True
    pair_reason: str = ""
    entry: EntryDecision | None = None
    risk_approved: bool | None = None
    risk_lot_size: float = 0.0
    risk_reason: str = ""
    executed: bool = False
    execution_mode: str = ""
    live_ticket: int | None = None
    skip_reason: str = ""


@dataclass(frozen=True)
class CycleSummary:
    """Aggregate outcome for a completed orchestration cycle."""

    symbols_processed: int
    entries_attempted: int
    trades_executed: int
    exits_processed: int
    skipped_symbols: tuple[str, ...] = ()
