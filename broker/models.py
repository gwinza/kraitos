"""Broker order and position models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TradeSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class MarketOrderResult:
    """Result of a filled market order on MetaTrader 5."""

    ticket: int
    symbol: str
    side: TradeSide
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float | None
    deal: int
    order: int
    retcode: int
    comment: str


@dataclass(frozen=True)
class LivePosition:
    """An open position on the connected MT5 account."""

    ticket: int
    symbol: str
    side: TradeSide
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float
    magic: int
    comment: str
