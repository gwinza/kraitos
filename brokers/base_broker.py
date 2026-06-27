"""Abstract broker interface and live-trading safety guard."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import pandas as pd

from broker.exceptions import LiveTradingDisabledError
from brokers.exceptions import LiveTradingGuardError
from config.broker_settings import BrokerSettings

if TYPE_CHECKING:
    from core.signal_router import TradeSignal
    from paper_trading.paper_executor import PaperExecutor

TradeSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class BrokerOrder:
    """Order request sent to a broker adapter."""

    symbol: str
    side: TradeSide
    volume: float
    stop_loss: float
    take_profit: float | None = None
    entry_price: float | None = None
    comment: str = "kraitos"
    timeframe: str = "H1"
    confidence: float = 0.0
    mode: str = "normal"
    reason: str = ""


@dataclass(frozen=True)
class BrokerTradeResult:
    """Result of a broker trade operation."""

    trade_id: str
    symbol: str
    side: TradeSide
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float | None
    simulated: bool = False
    message: str = ""


class LiveTradingGuard:
    """Validate all confirmation requirements before live order placement."""

    def __init__(self, settings: BrokerSettings) -> None:
        self._settings = settings

    def validate(self) -> None:
        """
        Require explicit confirmation before any live trade.

        Checks:
            - ENABLE_LIVE_TRADING=True
            - LIVE_TRADING=True
            - BROKER_NAME set
            - account_id set
            - max_risk_per_trade <= 1%
            - daily_drawdown_limit <= 5%
        """
        failures: list[str] = []

        if not self._settings.enable_live_trading:
            failures.append("ENABLE_LIVE_TRADING must be True")
        if not self._settings.live_trading:
            failures.append("LIVE_TRADING must be True")
        if not self._settings.broker_name:
            failures.append("BROKER_NAME must be set")
        if not self._settings.account_id:
            failures.append("account_id (BROKER_ACCOUNT_ID) must be set")
        if self._settings.max_risk_per_trade_pct > 1.0:
            failures.append(
                f"max_risk_per_trade must be <= 1% "
                f"(got {self._settings.max_risk_per_trade_pct}%)"
            )
        if self._settings.daily_drawdown_limit_pct > 5.0:
            failures.append(
                f"daily_drawdown_limit must be <= 5% "
                f"(got {self._settings.daily_drawdown_limit_pct}%)"
            )

        if failures:
            raise LiveTradingGuardError(
                "Live trading confirmation failed: " + "; ".join(failures)
            )

    @property
    def live_enabled(self) -> bool:
        """Return True when live trading switches are both on."""
        return self._settings.live_allowed


class BaseBroker(ABC):
    """Common broker adapter interface for Kraitos."""

    name: str = "base"

    def __init__(
        self,
        settings: BrokerSettings,
        *,
        paper_executor: PaperExecutor | None = None,
    ) -> None:
        self.settings = settings
        self.guard = LiveTradingGuard(settings)
        self._paper_executor = paper_executor
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection to the broker."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the broker connection."""

    @abstractmethod
    def get_symbols(self) -> tuple[str, ...]:
        """Return tradable symbols available from this broker."""

    @abstractmethod
    def get_candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        """Fetch OHLCV candles for a symbol and timeframe."""

    @abstractmethod
    def get_balance(self) -> float:
        """Return the current account balance."""

    def place_trade(self, order: BrokerOrder) -> BrokerTradeResult:
        """
        Place a trade on the broker or redirect to paper execution.

        Live orders require all confirmation guard checks to pass.
        When live trading is disabled, raises LiveTradingDisabledError
        unless a paper executor is configured for redirection.
        """
        if not self.guard.live_enabled:
            if self._paper_executor is not None:
                return self._redirect_to_paper(order)
            raise LiveTradingDisabledError(
                "Live trading is disabled (LIVE_TRADING / ENABLE_LIVE_TRADING). "
                "Configure a paper executor for simulated placement."
            )
        self.guard.validate()
        return self._place_live_trade(order)

    def close_trade(self, trade_id: str) -> BrokerTradeResult:
        """Close an open trade, respecting live-trading safety gates."""
        if not self.guard.live_enabled:
            raise LiveTradingDisabledError(
                f"Cannot close live trade {trade_id}: live trading is disabled"
            )
        self.guard.validate()
        return self._close_live_trade(trade_id)

    @abstractmethod
    def _place_live_trade(self, order: BrokerOrder) -> BrokerTradeResult:
        """Broker-specific live order placement (only called after guard passes)."""

    @abstractmethod
    def _close_live_trade(self, trade_id: str) -> BrokerTradeResult:
        """Broker-specific live trade close (only called after guard passes)."""

    def _redirect_to_paper(self, order: BrokerOrder) -> BrokerTradeResult:
        """Simulate order placement via the paper executor."""
        from core.signal_router import TradeSignal

        if self._paper_executor is None:
            raise LiveTradingDisabledError("Paper executor is not configured")

        signal = TradeSignal(
            symbol=order.symbol,
            decision="TRADE",
            direction=order.side,
            confidence=order.confidence,
            entry=order.entry_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            risk_pct=self.settings.max_risk_per_trade_pct,
            lot_size=order.volume,
            reason=order.reason or "broker paper redirect",
            mode=(
                order.mode
                if order.mode in {"scalp", "harvest", "normal"}
                else "normal"
            ),
            trace_id="broker-paper",
        )
        candles = {
            order.timeframe: self.get_candles(order.symbol, order.timeframe, count=5),
        }
        position = self._paper_executor.try_open(signal, candles=candles)
        if position is None:
            raise LiveTradingDisabledError(
                f"Paper redirect rejected for {order.symbol}"
            )
        return BrokerTradeResult(
            trade_id=position.trade_id,
            symbol=order.symbol,
            side=order.side,
            volume=order.volume,
            entry_price=position.entry,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            simulated=True,
            message="Redirected to paper executor",
        )
