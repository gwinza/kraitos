"""Pytest configuration and shared offline fixtures."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests import fixtures

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def valid_config_data() -> dict:
    return fixtures.valid_config_data()


@pytest.fixture
def kraitos_config(valid_config_data: dict):
    return fixtures.load_validated_config(valid_config_data)


@pytest.fixture
def write_config(tmp_path: Path):
    def _write(data: dict) -> Path:
        return fixtures.write_config(tmp_path, data)

    return _write


@pytest.fixture
def trending_candles():
    return fixtures.ohlcv_from_closes(fixtures.trending_closes())


@pytest.fixture
def ranging_candles():
    return fixtures.ohlcv_from_closes(fixtures.ranging_closes())


@pytest.fixture
def bullish_structure_candles():
    return fixtures.ohlcv_from_closes(fixtures.bullish_structure_closes())


@pytest.fixture
def mock_mt5_module():
    """Provide a mocked MetaTrader5 module for connector tests."""
    mock = MagicMock()
    mock.TIMEFRAME_M1 = 1
    mock.TIMEFRAME_M5 = 5
    mock.TIMEFRAME_M15 = 15
    mock.TIMEFRAME_M30 = 30
    mock.TIMEFRAME_H1 = 16385
    mock.TIMEFRAME_H4 = 16388
    mock.TIMEFRAME_D1 = 16408
    mock.TIMEFRAME_W1 = 32769
    mock.TIMEFRAME_MN1 = 49153
    mock.SYMBOL_TRADE_MODE_DISABLED = 0
    mock.last_error.return_value = (0, "")
    mock.account_info.return_value = SimpleNamespace(
        login=12345,
        name="Demo",
        server="Broker-Demo",
        currency="USD",
        balance=10_000.0,
        equity=10_000.0,
        margin=0.0,
        margin_free=10_000.0,
        leverage=100,
        trade_mode=0,
    )
    mock.terminal_info.return_value = SimpleNamespace(
        name="MetaTrader 5",
        company="Broker",
        connected=True,
    )
    with patch("broker.mt5_connector.mt5", mock):
        yield mock


@pytest.fixture(autouse=True)
def _offline_environment(monkeypatch: pytest.MonkeyPatch):
    """
    Ensure tests never attempt a real MT5 connection.

    Removes live-trading credentials from the environment and blocks
    accidental terminal initialization when the package is present.
    """
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    monkeypatch.delenv("MT5_LOGIN", raising=False)
    monkeypatch.delenv("MT5_PASSWORD", raising=False)
    monkeypatch.delenv("MT5_SERVER", raising=False)
    monkeypatch.delenv("MT5_PATH", raising=False)

    try:
        import MetaTrader5 as mt5  # noqa: WPS433
    except ImportError:
        return

    monkeypatch.setattr(mt5, "initialize", lambda *args, **kwargs: False, raising=False)
    monkeypatch.setattr(mt5, "shutdown", lambda *args, **kwargs: None, raising=False)
