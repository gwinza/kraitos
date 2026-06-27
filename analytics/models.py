"""Analytics data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ClosedTradeRecord:
    """Normalized closed trade used for performance calculations."""

    trade_id: str
    symbol: str
    side: str
    exit_time: datetime
    pnl: float
    balance: float | None = None
    session: str = "unknown"
    event_type: str = "close"


@dataclass(frozen=True)
class PerformanceMetrics:
    """Aggregated trading performance statistics."""

    total_trades: int
    win_rate: float
    loss_rate: float
    average_win: float
    average_loss: float
    profit_factor: float
    max_drawdown: float
    daily_return: float
    best_symbol: str | None
    worst_symbol: str | None
    best_session: str | None
    worst_session: str | None
    gross_profit: float
    gross_loss: float
    net_profit: float


PairClassification = str  # strong | normal | weak | quarantined


@dataclass(frozen=True)
class SymbolPerformance:
    """Performance statistics for a single symbol."""

    symbol: str
    total_trades: int
    win_rate: float
    profit_factor: float
    net_profit: float
    average_win: float
    average_loss: float


@dataclass(frozen=True)
class PairSpecialisationEntry:
    """Classification and risk rules for one symbol."""

    symbol: str
    classification: PairClassification
    risk_multiplier: float
    trading_allowed: bool
    performance: SymbolPerformance
    reason: str


@dataclass(frozen=True)
class PairSpecialisationResult:
    """Full pair specialisation analysis."""

    generated_at: str
    pairs: tuple[PairSpecialisationEntry, ...]
