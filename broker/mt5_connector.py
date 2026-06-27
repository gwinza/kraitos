"""
MetaTrader 5 connection module for Kraitos.

Provides market data, account inspection, and gated live order placement.
Live orders require LIVE_TRADING_ENABLED=true and trading.live_enabled in config.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from loguru import logger

from broker.exceptions import (
    LiveTradingDisabledError,
    MT5ConnectionError,
    MT5DataError,
    MT5OrderError,
)
from broker.models import LivePosition, MarketOrderResult, TradeSide

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - exercised only when package is missing
    mt5 = None  # type: ignore[assignment]

def _timeframe_map() -> dict[str, int]:
    """Return supported Kraitos timeframe strings mapped to MT5 constants."""
    _ensure_package_installed()
    return {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
        "MN1": mt5.TIMEFRAME_MN1,
    }


def _ensure_package_installed() -> None:
    if mt5 is None:
        raise MT5ConnectionError(
            "MetaTrader5 package is not installed. "
            "Install it with: pip install MetaTrader5"
        )


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _mt5_error_message() -> str:
    if mt5 is None:
        return "MetaTrader5 package is not installed"
    code, message = mt5.last_error()
    if code == 0:
        return "unknown MetaTrader 5 error"
    return f"[{code}] {message}"


@dataclass(frozen=True)
class MT5Credentials:
    """Connection credentials for MetaTrader 5."""

    path: str | None = None
    login: int | None = None
    password: str | None = None
    server: str | None = None


@dataclass(frozen=True)
class AccountInfo:
    """Snapshot of the connected MT5 account."""

    login: int
    name: str
    server: str
    currency: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    leverage: int
    trade_mode: int


@dataclass(frozen=True)
class SymbolQuote:
    """Current bid/ask quote for a symbol."""

    symbol: str
    bid: float
    ask: float
    spread: float
    time: datetime


class MT5Connector:
    """
    MetaTrader 5 broker connector.

    Read-only operations (quotes, candles, account info) are always available
    when connected. Any live order placement must call ``require_live_trading()``
    first; orders are rejected unless LIVE_TRADING_ENABLED=true.
    """

    def __init__(
        self,
        credentials: MT5Credentials | None = None,
        *,
        live_trading_enabled: bool | None = None,
        reconnect_attempts: int = 3,
        reconnect_delay_seconds: float = 5.0,
    ) -> None:
        self._credentials = credentials or MT5Credentials()
        self._live_trading_enabled = (
            live_trading_enabled
            if live_trading_enabled is not None
            else _env_bool("LIVE_TRADING_ENABLED", default=False)
        )
        self._reconnect_attempts = max(1, reconnect_attempts)
        self._reconnect_delay_seconds = max(0.0, reconnect_delay_seconds)
        self._connected = False

        if not self._live_trading_enabled:
            logger.warning(
                "Live trading is DISABLED (LIVE_TRADING_ENABLED is not true). "
                "Order placement will be blocked."
            )
        else:
            logger.warning("Live trading is ENABLED. Order placement is allowed.")

    @classmethod
    def from_env(
        cls,
        *,
        reconnect_attempts: int = 3,
        reconnect_delay_seconds: float = 5.0,
    ) -> MT5Connector:
        """Build a connector using MT5_* environment variables."""
        login_raw = os.getenv("MT5_LOGIN", "").strip()
        credentials = MT5Credentials(
            path=os.getenv("MT5_PATH") or None,
            login=int(login_raw) if login_raw.isdigit() else None,
            password=os.getenv("MT5_PASSWORD") or None,
            server=os.getenv("MT5_SERVER") or None,
        )
        return cls(
            credentials,
            reconnect_attempts=reconnect_attempts,
            reconnect_delay_seconds=reconnect_delay_seconds,
        )

    @property
    def live_trading_enabled(self) -> bool:
        """Whether live order placement is permitted."""
        return self._live_trading_enabled

    @property
    def is_connected(self) -> bool:
        """Return True when the MT5 terminal session is active."""
        return self._connected

    def connect(self) -> None:
        """Initialize MetaTrader 5 with retry logic."""
        _ensure_package_installed()

        if self._connected:
            logger.debug("MetaTrader 5 is already connected")
            return

        init_kwargs = self._build_init_kwargs()
        last_error = "connection not attempted"

        for attempt in range(1, self._reconnect_attempts + 1):
            logger.info(
                f"Connecting to MetaTrader 5 (attempt {attempt}/{self._reconnect_attempts})"
            )
            if mt5.initialize(**init_kwargs):
                self._connected = True
                terminal = mt5.terminal_info()
                if terminal is not None:
                    logger.info(
                        f"Connected to MT5 terminal: {terminal.name} "
                        f"(build {terminal.build}, {terminal.company})"
                    )
                else:
                    logger.info("Connected to MetaTrader 5")
                return

            last_error = _mt5_error_message()
            logger.warning(f"MT5 connection attempt {attempt} failed: {last_error}")

            if attempt < self._reconnect_attempts:
                time.sleep(self._reconnect_delay_seconds)

        raise MT5ConnectionError(
            f"Failed to connect to MetaTrader 5 after "
            f"{self._reconnect_attempts} attempt(s): {last_error}"
        )

    def disconnect(self) -> None:
        """Shut down the MetaTrader 5 connection."""
        if not self._connected:
            logger.debug("MetaTrader 5 is not connected; nothing to disconnect")
            return

        if mt5 is not None:
            mt5.shutdown()

        self._connected = False
        logger.info("Disconnected from MetaTrader 5")

    def __enter__(self) -> MT5Connector:
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.disconnect()

    def require_live_trading(self) -> None:
        """
        Guard for order placement.

        Raises:
            LiveTradingDisabledError: If LIVE_TRADING_ENABLED is not true.
        """
        if not self._live_trading_enabled:
            raise LiveTradingDisabledError(
                "Live trading is disabled. Set LIVE_TRADING_ENABLED=true in .env "
                "to allow order placement."
            )

    def get_account_info(self) -> AccountInfo:
        """Return account details for the connected terminal."""
        self._ensure_connected()

        info = mt5.account_info()
        if info is None:
            raise MT5DataError(
                f"Unable to fetch account info: {_mt5_error_message()}"
            )

        account = AccountInfo(
            login=info.login,
            name=info.name,
            server=info.server,
            currency=info.currency,
            balance=float(info.balance),
            equity=float(info.equity),
            margin=float(info.margin),
            free_margin=float(info.margin_free),
            leverage=int(info.leverage),
            trade_mode=int(info.trade_mode),
        )
        logger.debug(
            f"Account {account.login} | balance={account.balance:,.2f} "
            f"{account.currency} | equity={account.equity:,.2f}"
        )
        return account

    def is_symbol_available(self, symbol: str) -> bool:
        """Check whether a symbol exists and is enabled for trading."""
        self._ensure_connected()
        normalized = self._normalize_symbol(symbol)

        info = mt5.symbol_info(normalized)
        if info is None:
            logger.warning(f"Symbol not found: {normalized} ({_mt5_error_message()})")
            return False

        if not info.visible:
            logger.info(f"Symbol {normalized} not visible; attempting to enable")
            if not mt5.symbol_select(normalized, True):
                logger.warning(
                    f"Failed to enable symbol {normalized}: {_mt5_error_message()}"
                )
                return False
            info = mt5.symbol_info(normalized)
            if info is None:
                return False

        available = info.trade_mode != mt5.SYMBOL_TRADE_MODE_DISABLED
        if available:
            logger.debug(f"Symbol available: {normalized}")
        else:
            logger.warning(f"Symbol disabled for trading: {normalized}")
        return available

    def get_quote(self, symbol: str) -> SymbolQuote:
        """Fetch the current bid/ask for a symbol."""
        self._ensure_connected()
        normalized = self._normalize_symbol(symbol)

        if not self.is_symbol_available(normalized):
            raise MT5DataError(f"Symbol is not available: {normalized}")

        tick = mt5.symbol_info_tick(normalized)
        if tick is None:
            raise MT5DataError(
                f"Unable to fetch quote for {normalized}: {_mt5_error_message()}"
            )

        quote = SymbolQuote(
            symbol=normalized,
            bid=float(tick.bid),
            ask=float(tick.ask),
            spread=float(tick.ask - tick.bid),
            time=datetime.fromtimestamp(tick.time, tz=timezone.utc),
        )
        logger.debug(
            f"Quote {normalized}: bid={quote.bid} ask={quote.ask} "
            f"spread={quote.spread:.5f}"
        )
        return quote

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 500,
        *,
        start_pos: int = 0,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV candles.

        Args:
            symbol: Forex symbol (e.g. EURUSD).
            timeframe: Kraitos timeframe string (M1, M5, H1, D1, ...).
            count: Number of candles to retrieve.
            start_pos: Bar offset from the current bar (0 = most recent).

        Returns:
            DataFrame with columns:
            time, open, high, low, close, tick_volume, spread, real_volume
        """
        self._ensure_connected()
        normalized = self._normalize_symbol(symbol)
        timeframe_key = timeframe.strip().upper()
        timeframe_map = _timeframe_map()

        if timeframe_key not in timeframe_map:
            allowed = ", ".join(sorted(timeframe_map))
            raise MT5DataError(
                f"Unsupported timeframe '{timeframe}'. Allowed values: {allowed}"
            )
        if count <= 0:
            raise MT5DataError("count must be a positive integer")
        if start_pos < 0:
            raise MT5DataError("start_pos must be zero or positive")

        if not self.is_symbol_available(normalized):
            raise MT5DataError(f"Symbol is not available: {normalized}")

        rates = mt5.copy_rates_from_pos(
            normalized,
            timeframe_map[timeframe_key],
            start_pos,
            count,
        )
        if rates is None or len(rates) == 0:
            raise MT5DataError(
                f"Unable to fetch candles for {normalized} {timeframe_key}: "
                f"{_mt5_error_message()}"
            )

        frame = pd.DataFrame(rates)
        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
        logger.debug(
            f"Fetched {len(frame)} candles for {normalized} {timeframe_key} "
            f"(start_pos={start_pos})"
        )
        return frame

    def _build_init_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self._credentials.path:
            kwargs["path"] = self._credentials.path
        if self._credentials.login is not None:
            kwargs["login"] = self._credentials.login
        if self._credentials.password:
            kwargs["password"] = self._credentials.password
        if self._credentials.server:
            kwargs["server"] = self._credentials.server
        return kwargs

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized:
            raise MT5DataError("symbol must be a non-empty string")
        return normalized

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise MT5ConnectionError(
                "MetaTrader 5 is not connected. Call connect() first."
            )

    KRAITOS_MAGIC = 56001
    _SUCCESS_RETCODES = frozenset({10008, 10009})  # TRADE_RETCODE_PLACED, DONE

    def place_market_order(
        self,
        *,
        symbol: str,
        side: TradeSide,
        volume: float,
        stop_loss: float,
        take_profit: float | None = None,
        comment: str = "kraitos",
        deviation_pips: float = 1.0,
        magic: int | None = None,
    ) -> MarketOrderResult:
        """
        Place a market order with stop loss and optional take profit.

        Requires ``require_live_trading()`` to have been satisfied by the caller.
        """
        self.require_live_trading()
        self._ensure_connected()
        normalized = self._normalize_symbol(symbol)
        if not self.is_symbol_available(normalized):
            raise MT5OrderError(f"Symbol is not available for trading: {normalized}")

        info = mt5.symbol_info(normalized)
        if info is None:
            raise MT5OrderError(
                f"Unable to load symbol info for {normalized}: {_mt5_error_message()}"
            )

        tick = mt5.symbol_info_tick(normalized)
        if tick is None:
            raise MT5OrderError(
                f"Unable to fetch quote for {normalized}: {_mt5_error_message()}"
            )

        order_type = (
            mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
        )
        raw_price = float(tick.ask) if side == "buy" else float(tick.bid)
        price = self._normalize_price(info, raw_price)
        sl = self._normalize_price(info, stop_loss)
        tp = (
            self._normalize_price(info, take_profit)
            if take_profit is not None
            else 0.0
        )
        normalized_volume = self._normalize_volume(info, volume)
        deviation = self._deviation_points(info, deviation_pips)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": normalized,
            "volume": normalized_volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": deviation,
            "magic": magic if magic is not None else self.KRAITOS_MAGIC,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._resolve_filling_mode(info),
        }
        result = mt5.order_send(request)
        if result is None:
            raise MT5OrderError(
                f"order_send returned None for {normalized}: {_mt5_error_message()}"
            )
        if result.retcode not in self._SUCCESS_RETCODES:
            raise MT5OrderError(
                f"Market order rejected for {normalized}: "
                f"[{result.retcode}] {result.comment}"
            )

        ticket = int(result.deal or result.order)
        order_result = MarketOrderResult(
            ticket=ticket,
            symbol=normalized,
            side=side,
            volume=float(result.volume or normalized_volume),
            entry_price=float(result.price or price),
            stop_loss=sl,
            take_profit=take_profit,
            deal=int(result.deal),
            order=int(result.order),
            retcode=int(result.retcode),
            comment=str(result.comment),
        )
        logger.info(
            f"Live {side} {normalized} {order_result.volume:.2f} lots "
            f"@ {order_result.entry_price:.5f} (ticket={order_result.ticket})"
        )
        return order_result

    def get_open_positions(
        self,
        *,
        symbol: str | None = None,
        magic: int | None = None,
    ) -> tuple[LivePosition, ...]:
        """Return open positions, optionally filtered by symbol and magic number."""
        self._ensure_connected()
        normalized = self._normalize_symbol(symbol) if symbol else None
        if normalized and not self.is_symbol_available(normalized):
            return ()

        if normalized:
            raw_positions = mt5.positions_get(symbol=normalized)
        else:
            raw_positions = mt5.positions_get()
        if raw_positions is None:
            raise MT5DataError(
                f"Unable to fetch positions: {_mt5_error_message()}"
            )

        positions: list[LivePosition] = []
        magic_filter = magic if magic is not None else self.KRAITOS_MAGIC
        for item in raw_positions:
            if magic_filter is not None and int(item.magic) != magic_filter:
                continue
            side: TradeSide = (
                "buy" if item.type == mt5.POSITION_TYPE_BUY else "sell"
            )
            positions.append(
                LivePosition(
                    ticket=int(item.ticket),
                    symbol=str(item.symbol),
                    side=side,
                    volume=float(item.volume),
                    entry_price=float(item.price_open),
                    stop_loss=float(item.sl),
                    take_profit=float(item.tp),
                    magic=int(item.magic),
                    comment=str(item.comment),
                )
            )
        return tuple(positions)

    def close_position(
        self,
        ticket: int,
        *,
        volume: float | None = None,
        deviation_pips: float = 1.0,
        comment: str = "kraitos close",
    ) -> MarketOrderResult:
        """Close an open position fully or partially."""
        self.require_live_trading()
        self._ensure_connected()

        matches = mt5.positions_get(ticket=ticket)
        if not matches:
            raise MT5OrderError(f"Position not found: ticket={ticket}")
        position = matches[0]
        symbol = str(position.symbol)
        info = mt5.symbol_info(symbol)
        if info is None:
            raise MT5OrderError(f"Unable to load symbol info for {symbol}")

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5OrderError(f"Unable to fetch quote for {symbol}")

        close_volume = (
            self._normalize_volume(info, volume)
            if volume is not None
            else float(position.volume)
        )
        if close_volume <= 0 or close_volume > float(position.volume):
            raise MT5OrderError(
                f"Invalid close volume {close_volume} for ticket={ticket}"
            )

        if position.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = self._normalize_price(info, float(tick.bid))
            side: TradeSide = "buy"
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = self._normalize_price(info, float(tick.ask))
            side = "sell"

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": close_volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": self._deviation_points(info, deviation_pips),
            "magic": int(position.magic),
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._resolve_filling_mode(info),
        }
        result = mt5.order_send(request)
        if result is None:
            raise MT5OrderError(
                f"close order_send returned None: {_mt5_error_message()}"
            )
        if result.retcode not in self._SUCCESS_RETCODES:
            raise MT5OrderError(
                f"Close rejected for ticket={ticket}: "
                f"[{result.retcode}] {result.comment}"
            )

        order_result = MarketOrderResult(
            ticket=ticket,
            symbol=symbol,
            side=side,
            volume=close_volume,
            entry_price=float(position.price_open),
            stop_loss=float(position.sl),
            take_profit=float(position.tp) or None,
            deal=int(result.deal),
            order=int(result.order),
            retcode=int(result.retcode),
            comment=str(result.comment),
        )
        logger.info(
            f"Closed live position ticket={ticket} {symbol} "
            f"volume={close_volume:.2f}"
        )
        return order_result

    def modify_position(
        self,
        ticket: int,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> None:
        """Update stop loss and/or take profit on an open position."""
        self.require_live_trading()
        self._ensure_connected()

        matches = mt5.positions_get(ticket=ticket)
        if not matches:
            raise MT5OrderError(f"Position not found: ticket={ticket}")
        position = matches[0]
        info = mt5.symbol_info(str(position.symbol))
        if info is None:
            raise MT5OrderError(f"Unable to load symbol info for {position.symbol}")

        sl = (
            self._normalize_price(info, stop_loss)
            if stop_loss is not None
            else float(position.sl)
        )
        tp = (
            self._normalize_price(info, take_profit)
            if take_profit is not None
            else float(position.tp)
        )
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": str(position.symbol),
            "sl": sl,
            "tp": tp,
        }
        result = mt5.order_send(request)
        if result is None:
            raise MT5OrderError(
                f"modify order_send returned None: {_mt5_error_message()}"
            )
        if result.retcode not in self._SUCCESS_RETCODES:
            raise MT5OrderError(
                f"Modify rejected for ticket={ticket}: "
                f"[{result.retcode}] {result.comment}"
            )
        logger.info(f"Modified live position ticket={ticket} sl={sl:.5f} tp={tp:.5f}")

    @staticmethod
    def _normalize_volume(info: Any, volume: float) -> float:
        step = float(info.volume_step)
        minimum = float(info.volume_min)
        maximum = float(info.volume_max)
        if step <= 0:
            raise MT5OrderError("Broker reported invalid volume step")
        steps = round(volume / step)
        normalized = max(minimum, min(maximum, steps * step))
        decimals = max(0, len(str(step).split(".")[-1].rstrip("0")) if "." in str(step) else 0)
        return round(normalized, decimals)

    @staticmethod
    def _normalize_price(info: Any, price: float) -> float:
        return round(price, int(info.digits))

    @staticmethod
    def _deviation_points(info: Any, deviation_pips: float) -> int:
        point = float(info.point)
        if point <= 0:
            return max(1, int(deviation_pips))
        pip_size = point * 10 if int(info.digits) in {3, 5} else point
        points = int(round((deviation_pips * pip_size) / point))
        return max(1, points)

    @staticmethod
    def _resolve_filling_mode(info: Any) -> int:
        filling = int(info.filling_mode)
        if filling & mt5.SYMBOL_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK
        if filling & mt5.SYMBOL_FILLING_IOC:
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

