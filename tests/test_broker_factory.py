"""Tests for the multi-broker integration layer (mocked — no live orders)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pandas as pd
import pytest

from broker.exceptions import LiveTradingDisabledError
from brokers import (
    BrokerFactory,
    BrokerOrder,
    BrokerSettings,
    DerivBroker,
    IQOptionBroker,
    LiveTradingGuard,
    LiveTradingGuardError,
    MT5Broker,
)
from brokers.exceptions import BrokerConnectionError
from config import load_config
from config.broker_settings import SUPPORTED_BROKERS
from paper_trading.paper_executor import PaperExecutor
from paper_trading.virtual_account import ValidationConfig, VirtualAccount

pytestmark = pytest.mark.offline


def _safe_settings(**overrides) -> BrokerSettings:
    base = {
        "broker_name": "deriv",
        "account_id": "demo-123",
        "live_trading": False,
        "enable_live_trading": False,
        "max_risk_per_trade_pct": 1.0,
        "daily_drawdown_limit_pct": 5.0,
        "sandbox": True,
    }
    base.update(overrides)
    return BrokerSettings(**base)


def _live_settings(**overrides) -> BrokerSettings:
    base = {
        "live_trading": True,
        "enable_live_trading": True,
        "broker_name": "deriv",
        "account_id": "demo-123",
    }
    base.update(overrides)
    return _safe_settings(**base)


def _order() -> BrokerOrder:
    return BrokerOrder(
        symbol="EURUSD",
        side="buy",
        volume=0.01,
        stop_loss=1.0980,
        take_profit=1.1040,
        entry_price=1.1000,
        reason="test order",
    )


@pytest.fixture
def paper_executor(tmp_path: Path) -> PaperExecutor:
    account = VirtualAccount(
        ValidationConfig(initial_balance=100.0, spread_pips=0.0),
        journal_path=tmp_path / "trade_journal.csv",
    )
    return PaperExecutor(account)


def test_supported_brokers():
    assert SUPPORTED_BROKERS == frozenset({"mt5", "deriv", "iqoption"})
    assert BrokerFactory.supported_brokers() == SUPPORTED_BROKERS


def test_factory_creates_each_broker_type():
    for name in ("mt5", "deriv", "iqoption"):
        broker = BrokerFactory.create(name, settings=_safe_settings(broker_name=name))
        assert broker.name == name


def test_factory_rejects_unknown_broker():
    with pytest.raises(BrokerConnectionError, match="Unsupported broker"):
        BrokerFactory.create("unknown", settings=_safe_settings(broker_name="unknown"))


def test_live_trading_disabled_blocks_place_trade():
    broker = DerivBroker(_safe_settings())
    broker.connect()
    with pytest.raises(LiveTradingDisabledError, match="Live trading is disabled"):
        broker.place_trade(_order())


def test_place_trade_redirects_to_paper_executor(paper_executor: PaperExecutor):
    broker = DerivBroker(
        _safe_settings(),
        paper_executor=paper_executor,
    )
    broker.connect()
    result = broker.place_trade(_order())
    assert result.simulated is True
    assert result.message == "Redirected to paper executor"
    assert len(paper_executor.account.open_positions) == 1


def test_close_trade_blocked_when_live_disabled():
    broker = DerivBroker(_safe_settings())
    broker.connect()
    with pytest.raises(LiveTradingDisabledError):
        broker.close_trade("deriv-1")


def test_live_guard_requires_enable_live_trading():
    settings = _live_settings(enable_live_trading=False)
    with pytest.raises(LiveTradingGuardError, match="ENABLE_LIVE_TRADING"):
        LiveTradingGuard(settings).validate()


def test_live_guard_requires_live_trading_flag():
    settings = _live_settings(live_trading=False)
    with pytest.raises(LiveTradingGuardError, match="LIVE_TRADING"):
        LiveTradingGuard(settings).validate()


def test_live_guard_requires_broker_name():
    settings = _live_settings(broker_name=None)
    with pytest.raises(LiveTradingGuardError, match="BROKER_NAME"):
        LiveTradingGuard(settings).validate()


def test_live_guard_requires_account_id():
    settings = _live_settings(account_id=None)
    with pytest.raises(LiveTradingGuardError, match="account_id"):
        LiveTradingGuard(settings).validate()


def test_live_guard_rejects_risk_above_one_percent():
    settings = _live_settings(max_risk_per_trade_pct=2.0)
    with pytest.raises(LiveTradingGuardError, match="max_risk_per_trade"):
        LiveTradingGuard(settings).validate()


def test_live_guard_rejects_daily_drawdown_above_five_percent():
    settings = _live_settings(daily_drawdown_limit_pct=6.0)
    with pytest.raises(LiveTradingGuardError, match="daily_drawdown_limit"):
        LiveTradingGuard(settings).validate()


def test_live_guard_passes_with_valid_confirmation():
    LiveTradingGuard(_live_settings()).validate()


def test_deriv_broker_mock_responses():
    broker = DerivBroker(_safe_settings(broker_name="deriv"))
    broker.connect()
    assert broker.get_symbols()
    assert broker.get_balance() == pytest.approx(100.0)
    candles = broker.get_candles("frxEURUSD", "H1", count=5)
    assert len(candles) == 5
    assert "close" in candles.columns
    broker.disconnect()
    assert broker.is_connected is False


def test_iqoption_broker_mock_responses():
    broker = IQOptionBroker(_safe_settings(broker_name="iqoption"))
    broker.connect()
    assert "EURUSD" in broker.get_symbols()
    candles = broker.get_candles("EURUSD", "M5", count=3)
    assert len(candles) == 3
    broker.disconnect()


def test_deriv_stub_live_flow_when_guard_passes():
    broker = DerivBroker(_live_settings(broker_name="deriv"))
    broker.connect()
    opened = broker.place_trade(_order())
    assert opened.trade_id.startswith("deriv-")
    assert opened.simulated is False
    closed = broker.close_trade(opened.trade_id)
    assert closed.message == "deriv stub close accepted"


def test_iqoption_stub_live_flow_when_guard_passes():
    broker = IQOptionBroker(_live_settings(broker_name="iqoption"))
    broker.connect()
    opened = broker.place_trade(_order())
    assert opened.trade_id.startswith("iq-")
    assert opened.simulated is False
    closed = broker.close_trade(opened.trade_id)
    assert closed.message == "iqoption stub close accepted"


def test_deriv_raises_when_not_connected():
    broker = DerivBroker(_safe_settings(broker_name="deriv"))
    with pytest.raises(BrokerConnectionError, match="not connected"):
        broker.get_symbols()


def test_mt5_place_trade_blocked_when_live_disabled():
    connector = MagicMock()
    connector.connect = MagicMock()
    connector.disconnect = MagicMock()
    broker = MT5Broker(
        _safe_settings(broker_name="mt5"),
        connector=connector,
        symbols=("EURUSD",),
    )
    broker.connect()
    with pytest.raises(LiveTradingDisabledError, match="Live trading is disabled"):
        broker.place_trade(_order())
    connector.place_market_order.assert_not_called()


def test_broker_settings_from_config_yaml():
    config = load_config()
    settings = BrokerSettings.from_env(config_raw=config.raw)
    assert settings.broker_name == "mt5"
    assert settings.live_trading is False
    assert settings.enable_live_trading is False
    assert settings.max_risk_per_trade_pct == pytest.approx(1.0)
    assert settings.daily_drawdown_limit_pct == pytest.approx(5.0)
    assert settings.sandbox is True


def test_mt5_broker_uses_mock_connector():
    connector = MagicMock()
    connector.connect = MagicMock()
    connector.disconnect = MagicMock()
    connector.get_candles.return_value = pd.DataFrame(
        [
            {
                "time": datetime(2025, 1, 1, tzinfo=timezone.utc),
                "open": 1.1,
                "high": 1.11,
                "low": 1.09,
                "close": 1.105,
                "tick_volume": 100,
                "spread": 1,
            }
        ]
    )
    account = MagicMock(balance=100_000.0)
    connector.get_account_info.return_value = account
    type(connector).is_connected = PropertyMock(return_value=True)

    broker = MT5Broker(
        _safe_settings(broker_name="mt5"),
        connector=connector,
        symbols=("EURUSD",),
    )
    broker.connect()
    assert broker.get_symbols() == ("EURUSD",)
    assert broker.get_balance() == pytest.approx(100_000.0)
    assert len(broker.get_candles("EURUSD", "H1", 1)) == 1
    connector.connect.assert_called_once()
    broker.disconnect()


def test_broker_settings_defaults_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LIVE_TRADING", raising=False)
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("BROKER_NAME", raising=False)
    settings = BrokerSettings.from_env()
    assert settings.live_trading is False
    assert settings.enable_live_trading is False
