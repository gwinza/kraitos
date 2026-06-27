"""
Paper trading simulator for Kraitos.

Simulates live trading without sending orders to MetaTrader 5.
All trade events are logged to logs/paper_trades.csv.
"""

from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from core.helpers import trade_pnl
from execution.models import PaperAccountSnapshot, PaperTrade, TradeSide
from logs.event_logger import KraitosEventLogger

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "paper_trades.csv"

CSV_COLUMNS = [
    "trade_id",
    "event_time",
    "event_type",
    "symbol",
    "side",
    "status",
    "entry_price",
    "exit_price",
    "lot_size",
    "stop_loss",
    "take_profit",
    "floating_pl",
    "closed_pl",
    "balance",
    "reason",
]


@dataclass
class PaperTraderConfig:
    """Configuration for paper trading simulation."""

    initial_balance: float = 10_000.0
    contract_size: float = 100_000.0
    pip_size: float = 0.0001
    spread_pips: float = 1.0
    log_path: Path = field(default_factory=lambda: DEFAULT_LOG_PATH)


class PaperTraderError(Exception):
    """Raised when paper trading operations are invalid."""


class PaperTrader:
    """Simulate order execution and track paper account state."""

    def __init__(
        self,
        config: PaperTraderConfig | None = None,
        event_logger: KraitosEventLogger | None = None,
    ) -> None:
        self.config = config or PaperTraderConfig()
        self._event_logger = event_logger
        self._balance = self.config.initial_balance
        self._closed_pl = 0.0
        self._open_trades: dict[str, PaperTrade] = {}
        self._trade_history: list[PaperTrade] = []
        self._last_prices: dict[str, float] = {}
        self._ensure_log_file()

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def closed_pl(self) -> float:
        return self._closed_pl

    @property
    def floating_pl(self) -> float:
        return sum(self._floating_pnl(trade) for trade in self._open_trades.values())

    @property
    def equity(self) -> float:
        return self._balance + self.floating_pl

    def open_trade(
        self,
        *,
        symbol: str,
        side: TradeSide,
        entry_price: float,
        lot_size: float,
        stop_loss: float,
        take_profit: float | None = None,
        reason: str = "paper entry",
        trace_id: str | None = None,
        invalidation_level: float | None = None,
        entry_type: str | None = None,
        story_direction: str | None = None,
        story_confidence: float | None = None,
        story_narrative: str | None = None,
    ) -> PaperTrade:
        """Open a simulated paper trade."""
        symbol_key = self._normalize_symbol(symbol)
        self._validate_side(side)
        self._validate_price(entry_price, "entry_price")
        self._validate_price(stop_loss, "stop_loss")
        if lot_size <= 0:
            raise PaperTraderError("lot_size must be positive")
        if take_profit is not None:
            self._validate_price(take_profit, "take_profit")

        spread_price = self.config.spread_pips * self.config.pip_size
        fill_price = entry_price + spread_price / 2 if side == "buy" else entry_price - spread_price / 2

        trade = PaperTrade(
            trade_id=self._new_trade_id(),
            symbol=symbol_key,
            side=side,
            entry_time=datetime.now(timezone.utc),
            entry_price=fill_price,
            lot_size=lot_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            best_price=fill_price,
            invalidation_level=invalidation_level,
            trace_id=trace_id,
            entry_type=entry_type,
            story_direction=story_direction,
            story_confidence=story_confidence,
            story_narrative=story_narrative,
        )
        self._open_trades[trade.trade_id] = trade
        self._trade_history.append(trade)
        self._last_prices[symbol_key] = fill_price

        self._log_event(
            trade=trade,
            event_type="open",
            floating_pl=self._floating_pnl(trade),
            balance=self._balance,
            reason=reason,
        )
        logger.info(
            f"Paper open {side} {symbol_key} {lot_size:.2f} lots @ {fill_price:.5f}"
        )
        self._log_execution(
            trade,
            event_type="open",
            trace_id=trace_id,
            reason=reason,
            exit_price=None,
            closed_pl=0.0,
        )
        return trade

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        *,
        reason: str = "paper exit",
        trace_id: str | None = None,
    ) -> PaperTrade:
        """Close an open paper trade fully."""
        trade = self._require_open_trade(trade_id)
        return self._close_trade(trade, exit_price, trade.lot_size, reason, trace_id=trace_id)

    def scale_out(
        self,
        trade_id: str,
        exit_price: float,
        fraction: float,
        *,
        reason: str = "paper scale out",
        trace_id: str | None = None,
    ) -> PaperTrade:
        """Close a fraction of an open paper trade."""
        if fraction <= 0 or fraction > 1:
            raise PaperTraderError("fraction must be between 0 and 1")

        trade = self._require_open_trade(trade_id)
        close_volume = round(trade.lot_size * fraction, 2)
        if close_volume <= 0:
            raise PaperTraderError("scale out volume is zero")
        return self._close_trade(
            trade,
            exit_price,
            close_volume,
            reason,
            partial=fraction < 1.0,
            trace_id=trace_id,
        )

    def update_stop_loss(self, trade_id: str, stop_loss: float, *, reason: str = "trail stop") -> PaperTrade:
        """Update stop loss on an open trade."""
        trade = self._require_open_trade(trade_id)
        self._validate_price(stop_loss, "stop_loss")
        trade.stop_loss = stop_loss

        self._log_event(
            trade=trade,
            event_type="trail_stop",
            floating_pl=self._floating_pnl(trade),
            balance=self._balance,
            reason=reason,
        )
        logger.info(f"Paper trail stop {trade.trade_id} -> {stop_loss:.5f}")
        return trade

    def record_exit_tick(self, trade_id: str, current_price: float) -> PaperTrade:
        """Advance bar count and update best price for ATR exit management."""
        trade = self._require_open_trade(trade_id)
        self._validate_price(current_price, "current_price")
        trade.bars_since_entry += 1
        if trade.best_price <= 0:
            trade.best_price = trade.entry_price
        if trade.side == "buy":
            trade.best_price = max(trade.best_price, current_price)
        else:
            trade.best_price = min(trade.best_price, current_price)
        self._last_prices[trade.symbol] = current_price
        return trade

    def mark_to_market(self, prices: dict[str, float]) -> PaperAccountSnapshot:
        """Update floating P/L from latest symbol prices."""
        for symbol, price in prices.items():
            self._last_prices[self._normalize_symbol(symbol)] = price
        return self.snapshot()

    def snapshot(self) -> PaperAccountSnapshot:
        """Return current account and trade state."""
        return PaperAccountSnapshot(
            balance=self._balance,
            initial_balance=self.config.initial_balance,
            closed_pl=self._closed_pl,
            floating_pl=self.floating_pl,
            equity=self.equity,
            open_trades=tuple(self._open_trades.values()),
            trade_history=tuple(self._trade_history),
        )

    def _close_trade(
        self,
        trade: PaperTrade,
        exit_price: float,
        close_volume: float,
        reason: str,
        *,
        partial: bool = False,
        trace_id: str | None = None,
    ) -> PaperTrade:
        self._validate_price(exit_price, "exit_price")
        spread_price = self.config.spread_pips * self.config.pip_size
        fill_price = exit_price - spread_price / 2 if trade.side == "buy" else exit_price + spread_price / 2

        pnl = self._realized_pnl(
            trade.symbol,
            trade.side,
            trade.entry_price,
            fill_price,
            close_volume,
        )
        self._balance += pnl
        self._closed_pl += pnl
        trade.closed_pl += pnl

        if partial and close_volume < trade.lot_size:
            trade.lot_size = round(trade.lot_size - close_volume, 2)
            trade.partial_taken = True
            event_type = "scale_out"
            self._log_event(
                trade=trade,
                event_type=event_type,
                exit_price=fill_price,
                floating_pl=self._floating_pnl(trade),
                closed_pl=pnl,
                balance=self._balance,
                reason=reason,
            )
            logger.info(
                f"Paper scale out {trade.trade_id}: closed {close_volume:.2f} lots, "
                f"pnl={pnl:.2f}, balance={self._balance:.2f}"
            )
            self._log_execution(
                trade,
                event_type="scale_out",
                trace_id=trace_id,
                reason=reason,
                exit_price=fill_price,
                closed_pl=pnl,
            )
            return trade

        trade.status = "closed"
        trade.exit_time = datetime.now(timezone.utc)
        trade.exit_price = fill_price
        trade.exit_reason = reason
        trade.lot_size = close_volume
        self._open_trades.pop(trade.trade_id, None)

        self._log_event(
            trade=trade,
            event_type="close",
            exit_price=fill_price,
            floating_pl=0.0,
            closed_pl=pnl,
            balance=self._balance,
            reason=reason,
        )
        logger.info(
            f"Paper close {trade.trade_id}: pnl={pnl:.2f}, balance={self._balance:.2f}"
        )
        self._log_execution(
            trade,
            event_type="close",
            trace_id=trace_id,
            reason=reason,
            exit_price=fill_price,
            closed_pl=pnl,
        )
        return trade

    def _log_execution(
        self,
        trade: PaperTrade,
        *,
        event_type: str,
        trace_id: str | None,
        reason: str,
        exit_price: float | None,
        closed_pl: float,
    ) -> None:
        if self._event_logger is None:
            return
        active_trace = trace_id or self._event_logger.new_trace_id()
        self._event_logger.executed_trade(
            reason,
            symbol=trade.symbol,
            trace_id=active_trace,
            event_type=event_type,
            data={
                "trade_id": trade.trade_id,
                "side": trade.side,
                "entry_price": trade.entry_price,
                "exit_price": exit_price,
                "lot_size": trade.lot_size,
                "stop_loss": trade.stop_loss,
                "take_profit": trade.take_profit,
                "closed_pl": closed_pl,
                "balance": self._balance,
                "floating_pl": self.floating_pl,
            },
        )

    def _floating_pnl(self, trade: PaperTrade) -> float:
        mark = self._last_prices.get(trade.symbol, trade.entry_price)
        return self._realized_pnl(
            trade.symbol,
            trade.side,
            trade.entry_price,
            mark,
            trade.lot_size,
        )

    def _realized_pnl(
        self,
        symbol: str,
        side: TradeSide,
        entry: float,
        exit_price: float,
        lot_size: float,
    ) -> float:
        return trade_pnl(
            symbol=symbol,
            side=side,
            entry_price=entry,
            exit_price=exit_price,
            lot_size=lot_size,
            contract_size=self.config.contract_size,
        )

    def _require_open_trade(self, trade_id: str) -> PaperTrade:
        trade = self._open_trades.get(trade_id)
        if trade is None:
            raise PaperTraderError(f"Open trade not found: {trade_id}")
        return trade

    def _log_event(
        self,
        *,
        trade: PaperTrade,
        event_type: str,
        floating_pl: float = 0.0,
        closed_pl: float = 0.0,
        balance: float,
        reason: str,
        exit_price: float | None = None,
    ) -> None:
        row = {
            "trade_id": trade.trade_id,
            "event_time": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "symbol": trade.symbol,
            "side": trade.side,
            "status": trade.status,
            "entry_price": f"{trade.entry_price:.5f}",
            "exit_price": "" if exit_price is None else f"{exit_price:.5f}",
            "lot_size": f"{trade.lot_size:.2f}",
            "stop_loss": f"{trade.stop_loss:.5f}",
            "take_profit": "" if trade.take_profit is None else f"{trade.take_profit:.5f}",
            "floating_pl": f"{floating_pl:.2f}",
            "closed_pl": f"{closed_pl:.2f}",
            "balance": f"{balance:.2f}",
            "reason": reason,
        }
        self._append_csv(row)

    def _ensure_log_file(self) -> None:
        path = self.config.log_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()

    def _append_csv(self, row: dict[str, str]) -> None:
        with self.config.log_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writerow(row)

    @staticmethod
    def _new_trade_id() -> str:
        return uuid.uuid4().hex[:12]

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized:
            raise PaperTraderError("symbol is required")
        return normalized

    @staticmethod
    def _validate_side(side: str) -> None:
        if side not in {"buy", "sell"}:
            raise PaperTraderError(f"invalid side: {side}")

    @staticmethod
    def _validate_price(value: float, name: str) -> None:
        if value <= 0:
            raise PaperTraderError(f"{name} must be positive")
