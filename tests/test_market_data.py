"""Tests for market data preparation and fetching."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from broker.exceptions import MT5DataError
from data import MarketDataBundle, MarketDataError, MarketDataService, prepare_candles


def _sample_raw(rows: int = 3, freq: str = "h") -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    times = [start + timedelta(hours=index) for index in range(rows)]
    base = 1.1
    return pd.DataFrame(
        {
            "time": times,
            "open": [base + index * 0.1 for index in range(rows)],
            "high": [base + index * 0.1 + 0.1 for index in range(rows)],
            "low": [base + index * 0.1 - 0.1 for index in range(rows)],
            "close": [base + index * 0.1 + 0.05 for index in range(rows)],
            "tick_volume": [100 + index * 10 for index in range(rows)],
            "spread": [2 + (index % 2) for index in range(rows)],
            "real_volume": [0 for _ in range(rows)],
        }
    )


def test_prepare_candles_keeps_required_columns():
    frame = prepare_candles(_sample_raw())

    assert list(frame.columns) == [
        "time",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread",
    ]
    assert len(frame) == 3
    assert frame["time"].is_monotonic_increasing


def test_prepare_candles_drops_invalid_rows():
    raw = _sample_raw()
    raw.loc[1, ["open", "high", "low", "close"]] = pd.NA
    raw.loc[2, "close"] = 0

    frame = prepare_candles(raw)

    assert len(frame) == 1
    assert frame.iloc[0]["open"] == 1.1


def test_prepare_candles_deduplicates_timestamps():
    raw = _sample_raw(rows=2)
    duplicate = raw.iloc[[0, 0, 1]].copy()
    duplicate.loc[duplicate.index[1], "close"] = 9.99

    frame = prepare_candles(duplicate)

    assert len(frame) == 2
    assert frame.iloc[0]["close"] == 9.99


def test_fetch_native_timeframe():
    connector = MagicMock()
    connector.get_candles.return_value = _sample_raw()

    service = MarketDataService(connector, default_count=10)
    frame = service.fetch_candles("eurusd", "m5")

    connector.get_candles.assert_called_once_with("EURUSD", "M5", count=10)
    assert len(frame) == 3


def test_fetch_h8_builds_from_h1():
    connector = MagicMock()
    h1_rows = 16
    connector.get_candles.return_value = _sample_raw(rows=h1_rows)

    service = MarketDataService(connector, default_count=2)
    frame = service.fetch_candles("EURUSD", "H8", count=2)

    connector.get_candles.assert_called_once_with("EURUSD", "H1", count=16)
    assert list(frame.columns) == [
        "time",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread",
    ]
    assert len(frame) <= 2


def test_fetch_multiple_symbols_and_timeframes():
    connector = MagicMock()
    connector.get_candles.return_value = _sample_raw()

    service = MarketDataService(connector, default_count=5)
    bundle = service.fetch(["EURUSD", "GBPUSD"], ["M1", "H1"])

    assert isinstance(bundle, MarketDataBundle)
    assert bundle.symbols() == ("EURUSD", "GBPUSD")
    assert bundle.timeframes("EURUSD") == ("H1", "M1")
    assert len(bundle.get("EURUSD", "H1")) == 3


def test_bundle_get_missing_raises():
    bundle = MarketDataBundle(data={"EURUSD": {"H1": _sample_raw()}})

    with pytest.raises(MarketDataError, match="No market data"):
        bundle.get("EURUSD", "M5")


def test_fetch_wraps_mt5_errors():
    connector = MagicMock()
    connector.get_candles.side_effect = MT5DataError("symbol unavailable")

    service = MarketDataService(connector)

    with pytest.raises(MarketDataError, match="symbol unavailable"):
        service.fetch_candles("EURUSD", "H1")


def test_rejects_unsupported_timeframe():
    connector = MagicMock()
    service = MarketDataService(connector)

    with pytest.raises(MarketDataError, match="Unsupported timeframe"):
        service.fetch_candles("EURUSD", "D1")
