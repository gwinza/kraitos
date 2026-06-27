"""Tests for the MetaTrader 5 connector (mocked — no terminal required)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

pytestmark = pytest.mark.mt5_mock

from broker import (
    LiveTradingDisabledError,
    MT5ConnectionError,
    MT5Connector,
    MT5Credentials,
    MT5DataError,
)


@pytest.fixture
def mock_mt5():
    module = MagicMock()
    module.TIMEFRAME_M5 = 5
    module.TIMEFRAME_H1 = 60
    module.TIMEFRAME_M1 = 1
    module.TIMEFRAME_M15 = 15
    module.TIMEFRAME_M30 = 30
    module.TIMEFRAME_H4 = 240
    module.TIMEFRAME_D1 = 1440
    module.TIMEFRAME_W1 = 10080
    module.TIMEFRAME_MN1 = 43200
    module.SYMBOL_TRADE_MODE_DISABLED = 0
    module.last_error.return_value = (1, "terminal not found")
    return module


@pytest.fixture
def connector(mock_mt5):
    with patch("broker.mt5_connector.mt5", mock_mt5):
        yield MT5Connector(
            MT5Credentials(login=12345, password="secret", server="Broker-Demo"),
            live_trading_enabled=False,
            reconnect_attempts=2,
            reconnect_delay_seconds=0,
        )


def test_connect_success(connector, mock_mt5):
    mock_mt5.initialize.return_value = True
    mock_mt5.terminal_info.return_value = SimpleNamespace(
        name="MetaTrader 5",
        build=4755,
        company="MetaQuotes",
    )

    connector.connect()

    assert connector.is_connected is True
    mock_mt5.initialize.assert_called_once()


def test_connect_failure_after_retries(connector, mock_mt5):
    mock_mt5.initialize.return_value = False

    with pytest.raises(MT5ConnectionError, match="Failed to connect"):
        connector.connect()

    assert connector.is_connected is False
    assert mock_mt5.initialize.call_count == 2


def test_disconnect(connector, mock_mt5):
    mock_mt5.initialize.return_value = True
    connector.connect()
    connector.disconnect()

    assert connector.is_connected is False
    mock_mt5.shutdown.assert_called_once()


def test_get_account_info(connector, mock_mt5):
    mock_mt5.initialize.return_value = True
    mock_mt5.account_info.return_value = SimpleNamespace(
        login=12345,
        name="Demo",
        server="Broker-Demo",
        currency="USD",
        balance=10000.0,
        equity=10050.0,
        margin=100.0,
        margin_free=9950.0,
        leverage=100,
        trade_mode=0,
    )

    connector.connect()
    account = connector.get_account_info()

    assert account.login == 12345
    assert account.balance == 10000.0


def test_is_symbol_available_enables_hidden_symbol(connector, mock_mt5):
    mock_mt5.initialize.return_value = True
    hidden = SimpleNamespace(visible=False, trade_mode=4)
    visible = SimpleNamespace(visible=True, trade_mode=4)
    mock_mt5.symbol_info.side_effect = [hidden, visible]
    mock_mt5.symbol_select.return_value = True

    connector.connect()
    assert connector.is_symbol_available("eurusd") is True
    mock_mt5.symbol_select.assert_called_once_with("EURUSD", True)


def test_get_quote(connector, mock_mt5):
    mock_mt5.initialize.return_value = True
    mock_mt5.symbol_info.return_value = SimpleNamespace(visible=True, trade_mode=4)
    tick_time = int(datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc).timestamp())
    mock_mt5.symbol_info_tick.return_value = SimpleNamespace(
        bid=1.1000,
        ask=1.1002,
        time=tick_time,
    )

    connector.connect()
    quote = connector.get_quote("EURUSD")

    assert quote.symbol == "EURUSD"
    assert quote.bid == 1.1000
    assert quote.ask == 1.1002
    assert quote.spread == pytest.approx(0.0002)


def test_get_candles(connector, mock_mt5):
    mock_mt5.initialize.return_value = True
    mock_mt5.symbol_info.return_value = SimpleNamespace(visible=True, trade_mode=4)
    mock_mt5.copy_rates_from_pos.return_value = [
        {
            "time": 1700000000,
            "open": 1.1,
            "high": 1.2,
            "low": 1.0,
            "close": 1.15,
            "tick_volume": 100,
            "spread": 2,
            "real_volume": 0,
        }
    ]

    connector.connect()
    candles = connector.get_candles("EURUSD", "M5", count=1)

    assert isinstance(candles, pd.DataFrame)
    assert len(candles) == 1
    assert candles.iloc[0]["close"] == 1.15


def test_require_live_trading_blocks_orders(connector, mock_mt5):
    mock_mt5.initialize.return_value = True
    connector.connect()

    with pytest.raises(LiveTradingDisabledError, match="Live trading is disabled"):
        connector.require_live_trading()


def test_live_trading_enabled_allows_guard(mock_mt5):
    with patch("broker.mt5_connector.mt5", mock_mt5):
        connector = MT5Connector(live_trading_enabled=True)
        mock_mt5.initialize.return_value = True
        connector.connect()
        connector.require_live_trading()


def test_operations_require_connection(connector):
    with pytest.raises(MT5ConnectionError, match="not connected"):
        connector.get_account_info()
