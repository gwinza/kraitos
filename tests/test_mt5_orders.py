"""Tests for MT5 live order placement (mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from broker import LivePosition, MT5Connector, MT5Credentials, MT5OrderError
from broker.models import MarketOrderResult

pytestmark = pytest.mark.mt5_mock


@pytest.fixture
def mock_mt5():
    module = MagicMock()
    module.TIMEFRAME_M5 = 5
    module.SYMBOL_TRADE_MODE_DISABLED = 0
    module.TRADE_ACTION_DEAL = 1
    module.TRADE_ACTION_SLTP = 2
    module.ORDER_TYPE_BUY = 0
    module.ORDER_TYPE_SELL = 1
    module.ORDER_TIME_GTC = 0
    module.ORDER_FILLING_FOK = 0
    module.ORDER_FILLING_IOC = 1
    module.ORDER_FILLING_RETURN = 2
    module.SYMBOL_FILLING_FOK = 1
    module.SYMBOL_FILLING_IOC = 2
    module.POSITION_TYPE_BUY = 0
    module.POSITION_TYPE_SELL = 1
    module.last_error.return_value = (1, "terminal not found")
    return module


@pytest.fixture
def connector(mock_mt5):
    with patch("broker.mt5_connector.mt5", mock_mt5):
        yield MT5Connector(
            MT5Credentials(login=12345, password="secret", server="Broker-Demo"),
            live_trading_enabled=True,
            reconnect_attempts=1,
            reconnect_delay_seconds=0,
        )


def _symbol_info():
    return SimpleNamespace(
        visible=True,
        trade_mode=4,
        volume_step=0.01,
        volume_min=0.01,
        volume_max=100.0,
        digits=5,
        point=0.00001,
        filling_mode=1,
    )


def test_place_market_order_buy(connector, mock_mt5):
    mock_mt5.initialize.return_value = True
    mock_mt5.symbol_info.return_value = _symbol_info()
    mock_mt5.symbol_info_tick.return_value = SimpleNamespace(bid=1.1000, ask=1.1002, time=0)
    mock_mt5.order_send.return_value = SimpleNamespace(
        retcode=10009,
        deal=1001,
        order=2001,
        volume=0.1,
        price=1.1002,
        comment="done",
    )

    connector.connect()
    result = connector.place_market_order(
        symbol="EURUSD",
        side="buy",
        volume=0.1,
        stop_loss=1.0980,
        take_profit=1.1040,
    )

    assert isinstance(result, MarketOrderResult)
    assert result.symbol == "EURUSD"
    assert result.side == "buy"
    assert result.volume == pytest.approx(0.1)
    assert result.entry_price == pytest.approx(1.1002)
    request = mock_mt5.order_send.call_args.args[0]
    assert request["type"] == mock_mt5.ORDER_TYPE_BUY
    assert request["sl"] == pytest.approx(1.0980)
    assert request["tp"] == pytest.approx(1.1040)


def test_place_market_order_rejected(connector, mock_mt5):
    mock_mt5.initialize.return_value = True
    mock_mt5.symbol_info.return_value = _symbol_info()
    mock_mt5.symbol_info_tick.return_value = SimpleNamespace(bid=1.1000, ask=1.1002, time=0)
    mock_mt5.order_send.return_value = SimpleNamespace(
        retcode=10013,
        deal=0,
        order=0,
        volume=0.0,
        price=0.0,
        comment="invalid volume",
    )

    connector.connect()
    with pytest.raises(MT5OrderError, match="rejected"):
        connector.place_market_order(
            symbol="EURUSD",
            side="sell",
            volume=0.1,
            stop_loss=1.1020,
        )


def test_get_open_positions_filters_magic(connector, mock_mt5):
    mock_mt5.initialize.return_value = True
    mock_mt5.symbol_info.return_value = _symbol_info()
    mock_mt5.positions_get.return_value = [
        SimpleNamespace(
            ticket=11,
            symbol="EURUSD",
            type=mock_mt5.POSITION_TYPE_BUY,
            volume=0.1,
            price_open=1.1,
            sl=1.09,
            tp=1.12,
            magic=MT5Connector.KRAITOS_MAGIC,
            comment="kraitos",
        ),
        SimpleNamespace(
            ticket=12,
            symbol="GBPUSD",
            type=mock_mt5.POSITION_TYPE_SELL,
            volume=0.2,
            price_open=1.25,
            sl=1.26,
            tp=1.23,
            magic=999,
            comment="manual",
        ),
    ]

    connector.connect()
    positions = connector.get_open_positions()

    assert len(positions) == 1
    assert isinstance(positions[0], LivePosition)
    assert positions[0].ticket == 11
    assert positions[0].side == "buy"


def test_close_position(connector, mock_mt5):
    mock_mt5.initialize.return_value = True
    mock_mt5.symbol_info.return_value = _symbol_info()
    mock_mt5.symbol_info_tick.return_value = SimpleNamespace(bid=1.1010, ask=1.1012, time=0)
    mock_mt5.positions_get.return_value = [
        SimpleNamespace(
            ticket=42,
            symbol="EURUSD",
            type=mock_mt5.POSITION_TYPE_BUY,
            volume=0.1,
            price_open=1.1,
            sl=1.09,
            tp=1.12,
            magic=MT5Connector.KRAITOS_MAGIC,
            comment="kraitos",
        )
    ]
    mock_mt5.order_send.return_value = SimpleNamespace(
        retcode=10009,
        deal=3001,
        order=4001,
        volume=0.1,
        price=1.1010,
        comment="done",
    )

    connector.connect()
    result = connector.close_position(42)

    assert result.ticket == 42
    request = mock_mt5.order_send.call_args.args[0]
    assert request["position"] == 42
    assert request["type"] == mock_mt5.ORDER_TYPE_SELL


def test_modify_position(connector, mock_mt5):
    mock_mt5.initialize.return_value = True
    mock_mt5.symbol_info.return_value = _symbol_info()
    mock_mt5.positions_get.return_value = [
        SimpleNamespace(
            ticket=55,
            symbol="EURUSD",
            type=mock_mt5.POSITION_TYPE_BUY,
            volume=0.1,
            price_open=1.1,
            sl=1.09,
            tp=1.12,
            magic=MT5Connector.KRAITOS_MAGIC,
            comment="kraitos",
        )
    ]
    mock_mt5.order_send.return_value = SimpleNamespace(
        retcode=10009,
        deal=0,
        order=0,
        volume=0.0,
        price=0.0,
        comment="done",
    )

    connector.connect()
    connector.modify_position(55, stop_loss=1.0950)

    request = mock_mt5.order_send.call_args.args[0]
    assert request["action"] == mock_mt5.TRADE_ACTION_SLTP
    assert request["sl"] == pytest.approx(1.0950)
