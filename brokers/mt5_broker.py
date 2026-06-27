"""MetaTrader 5 broker adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
from loguru import logger

from broker.mt5_connector import MT5Connector
from brokers.base_broker import BaseBroker, BrokerOrder, BrokerTradeResult
from brokers.exceptions import BrokerConnectionError, BrokerDataError
from config.broker_settings import BrokerSettings

if TYPE_CHECKING:
    from paper_trading.paper_executor import PaperExecutor


class MT5Broker(BaseBroker):
    """Broker adapter wrapping the existing MT5Connector."""

    name = "mt5"

    def __init__(
        self,
        settings: BrokerSettings,
        *,
        connector: MT5Connector | None = None,
        symbols: tuple[str, ...] | None = None,
        paper_executor: PaperExecutor | None = None,
    ) -> None:
        super().__init__(settings, paper_executor=paper_executor)
        self._connector = connector or MT5Connector.from_env()
        self._symbols = symbols

    def connect(self) -> None:
        try:
            self._connector.connect()
            self._connected = True
            logger.info("MT5 broker connected")
        except Exception as exc:
            raise BrokerConnectionError(str(exc)) from exc

    def disconnect(self) -> None:
        self._connector.disconnect()
        self._connected = False
        logger.info("MT5 broker disconnected")

    def get_symbols(self) -> tuple[str, ...]:
        self._ensure_connected()
        if self._symbols:
            return self._symbols
        return ("EURUSD", "GBPUSD", "USDJPY")

    def get_candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        self._ensure_connected()
        try:
            return self._connector.get_candles(symbol, timeframe, count=count)
        except Exception as exc:
            raise BrokerDataError(str(exc)) from exc

    def get_balance(self) -> float:
        self._ensure_connected()
        try:
            return float(self._connector.get_account_info().balance)
        except Exception as exc:
            raise BrokerDataError(str(exc)) from exc

    def _place_live_trade(self, order: BrokerOrder) -> BrokerTradeResult:
        self._ensure_connected()
        result = self._connector.place_market_order(
            symbol=order.symbol,
            side=order.side,
            volume=order.volume,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            comment=order.comment,
        )
        return BrokerTradeResult(
            trade_id=str(result.ticket),
            symbol=result.symbol,
            side=result.side,
            volume=result.volume,
            entry_price=result.entry_price,
            stop_loss=result.stop_loss,
            take_profit=result.take_profit,
            simulated=False,
            message=result.comment,
        )

    def _close_live_trade(self, trade_id: str) -> BrokerTradeResult:
        self._ensure_connected()
        ticket = int(trade_id)
        result = self._connector.close_position(ticket)
        return BrokerTradeResult(
            trade_id=str(result.ticket),
            symbol=result.symbol,
            side=result.side,
            volume=result.volume,
            entry_price=result.entry_price,
            stop_loss=result.stop_loss,
            take_profit=result.take_profit,
            simulated=False,
            message="closed",
        )

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise BrokerConnectionError("MT5 broker is not connected. Call connect() first.")
