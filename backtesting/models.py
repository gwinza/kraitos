"""Data models for the backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import pandas as pd

TradeSide = Literal["buy", "sell"]
ExitReason = Literal["stop_loss", "take_profit", "close"]


@dataclass(frozen=True)
class BacktestConfig:
    """Configuration for a backtest run."""

    initial_balance: float = 10_000.0
    spread_pips: float = 1.5
    pip_size: float = 0.0001
    contract_size: float = 100_000.0
    allow_multiple_positions: bool = False


@dataclass(frozen=True)
class TradeSignal:
    """Instruction to open a trade on a specific candle bar."""

    bar_index: int
    side: TradeSide
    volume: float = 0.1
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass
class Trade:
    """A simulated trade with optional exit details."""

    symbol: str
    side: TradeSide
    volume: float
    entry_time: datetime
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    exit_time: datetime | None = None
    exit_price: float | None = None
    pnl: float = 0.0
    exit_reason: ExitReason | None = None


@dataclass(frozen=True)
class BacktestMetrics:
    """Summary statistics for a completed backtest."""

    initial_balance: float
    final_balance: float
    total_return: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    gross_profit: float
    gross_loss: float


@dataclass
class BacktestResult:
    """Full output of a backtest run."""

    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)
    metrics: BacktestMetrics | None = None
