"""Tests for the Kraitos orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from config import load_config
from core.orchestrator import KraitosOrchestrator
from core.runtime import KraitosRuntime
from logs.event_logger import KraitosEventLogger


def _candle_frame(rows: int = 120) -> pd.DataFrame:
    times = pd.date_range("2025-01-01", periods=rows, freq="h", tz="UTC")
    close = pd.Series([1.10 + (index * 0.0001) for index in range(rows)])
    return pd.DataFrame(
        {
            "time": times,
            "open": close - 0.0002,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
            "tick_volume": 1000,
            "spread": 1.5,
        }
    )


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    (config_dir / "config.yaml").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "logs").mkdir()
    return tmp_path


@pytest.fixture
def runtime(project_root: Path) -> KraitosRuntime:
    config = load_config(project_root / "config" / "config.yaml")
    event_logger = KraitosEventLogger(project_root / "logs")
    return KraitosRuntime.build(
        project_root=project_root,
        config=config,
        event_logger=event_logger,
    )


def test_orchestrator_runs_cycle_with_mocked_mt5(runtime: KraitosRuntime):
    frame = _candle_frame()
    bundle_data = {
        symbol: {
            timeframe: frame
            for timeframe in ("M1", "M5", "M15", "H1", "H4", "H8")
        }
        for symbol in runtime.config.trading.symbols
    }

    quote = MagicMock()
    quote.bid = 1.1000
    quote.ask = 1.10015
    quote.spread = 0.00015
    quote.time = datetime.now(timezone.utc)

    account = MagicMock()
    account.login = 12345
    account.server = "demo"
    account.balance = 10_000.0
    account.equity = 10_000.0

    runtime.connector.connect = MagicMock()
    runtime.connector.disconnect = MagicMock()
    runtime.connector.get_account_info = MagicMock(return_value=account)
    runtime.connector.get_quote = MagicMock(return_value=quote)
    runtime.connector.require_live_trading = MagicMock()

    with patch("core.orchestrator.fetch_market_data") as fetch_mock:
        from data.market_data import MarketDataBundle

        fetch_mock.return_value = MarketDataBundle(data=bundle_data)
        orchestrator = KraitosOrchestrator(runtime)
        summary = orchestrator._run_cycle(trace_id="test-trace")

    assert summary.symbols_processed == len(runtime.config.trading.symbols)
    runtime.connector.connect.assert_not_called()
    assert (runtime.project_root / "logs" / "dashboard_state.json").exists()


def test_main_module_importable():
    import main

    assert callable(main.main)
