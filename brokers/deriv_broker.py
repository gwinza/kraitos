"""Deriv broker adapter (API stub — no live orders in default mode)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import pandas as pd
from loguru import logger

from brokers.base_broker import BaseBroker, BrokerOrder, BrokerTradeResult
from brokers.exceptions import BrokerConnectionError
from config.broker_settings import BrokerSettings

if TYPE_CHECKING:
    from paper_trading.paper_executor import PaperExecutor

DEFAULT_SYMBOLS = ("frxEURUSD", "frxGBPUSD", "frxUSDJPY")


class DerivBroker(BaseBroker):
    """Deriv integration stub with mocked market responses for testing."""

    name = "deriv"

    def __init__(
        self,
        settings: BrokerSettings,
        *,
        symbols: tuple[str, ...] | None = None,
        paper_executor: PaperExecutor | None = None,
        mock_balance: float = 100.0,
    ) -> None:
        super().__init__(settings, paper_executor=paper_executor)
        self._symbols = symbols or DEFAULT_SYMBOLS
        self._mock_balance = mock_balance
        self._open_trades: dict[str, BrokerTradeResult] = {}
        self._trade_counter = 0

    def connect(self) -> None:
        if not self.settings.api_key and not self.settings.sandbox:
            raise BrokerConnectionError("Deriv API key required for non-sandbox mode")
        self._connected = True
        logger.info("Deriv broker connected (stub mode)")

    def disconnect(self) -> None:
        self._connected = False
        logger.info("Deriv broker disconnected")

    def get_symbols(self) -> tuple[str, ...]:
        self._ensure_connected()
        return self._symbols

    def get_candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        self._ensure_connected()
        if count <= 0:
            count = 10
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = []
        for index in range(count):
            close = 1.10 + index * 0.0001
            rows.append(
                {
                    "time": start + timedelta(hours=index),
                    "open": close - 0.0001,
                    "high": close + 0.0002,
                    "low": close - 0.0002,
                    "close": close,
                    "tick_volume": 100,
                    "spread": 1.0,
                }
            )
        return pd.DataFrame(rows)

    def get_balance(self) -> float:
        self._ensure_connected()
        return self._mock_balance

    def _place_live_trade(self, order: BrokerOrder) -> BrokerTradeResult:
        self._ensure_connected()
        self._trade_counter += 1
        trade_id = f"deriv-{self._trade_counter}"
        entry = order.entry_price or 1.1000
        result = BrokerTradeResult(
            trade_id=trade_id,
            symbol=order.symbol,
            side=order.side,
            volume=order.volume,
            entry_price=entry,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            simulated=False,
            message="deriv stub order accepted",
        )
        self._open_trades[trade_id] = result
        return result

    def _close_live_trade(self, trade_id: str) -> BrokerTradeResult:
        self._ensure_connected()
        if trade_id not in self._open_trades:
            raise BrokerConnectionError(f"Deriv trade not found: {trade_id}")
        result = self._open_trades.pop(trade_id)
        return BrokerTradeResult(
            trade_id=result.trade_id,
            symbol=result.symbol,
            side=result.side,
            volume=result.volume,
            entry_price=result.entry_price,
            stop_loss=result.stop_loss,
            take_profit=result.take_profit,
            simulated=False,
            message="deriv stub close accepted",
        )

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise BrokerConnectionError("Deriv broker is not connected. Call connect() first.")
