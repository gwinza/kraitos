"""End-to-end tests for the integrated Kraitos pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from config import load_config
from core.engine import KraitosEngine
from core.signal_router import TradeSignal
from data.market_data import MarketDataBundle
from logs.event_logger import KraitosEventLogger

pytestmark = pytest.mark.offline

PIPELINE_TIMEFRAMES = ("M1", "M5", "M15", "H1", "H4", "H8")


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
            "spread": 1.0,
        }
    )


def _project_with_paper_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    text = source.read_text(encoding="utf-8")
    text = text.replace("live_enabled: true", "live_enabled: false")
    text = text.replace("paper_enabled: false", "paper_enabled: true")
    if "pipeline:" not in text:
        text += """
pipeline:
  execution_mode: simulation
  execute_trades: false
  structure_timeframe: H1
  precision_timeframes:
    - M1
    - M5
"""
    (config_dir / "config.yaml").write_text(text, encoding="utf-8")
    (tmp_path / "logs").mkdir()
    return tmp_path


@pytest.fixture
def pipeline_engine(tmp_path: Path) -> KraitosEngine:
    root = _project_with_paper_config(tmp_path)
    config = load_config(root / "config" / "config.yaml")
    event_logger = KraitosEventLogger(root / "logs")
    engine = KraitosEngine.build(
        project_root=root,
        config=config,
        event_logger=event_logger,
    )
    return engine


def test_full_pipeline_returns_signals_for_all_symbols(pipeline_engine: KraitosEngine):
    frame = _candle_frame()
    bundle_data = {
        symbol: {tf: frame for tf in PIPELINE_TIMEFRAMES}
        for symbol in pipeline_engine.config.trading.symbols
    }
    quote = SimpleNamespace(bid=1.1000, ask=1.1001, spread=0.0001)

    pipeline_engine._connector.get_quote = MagicMock(return_value=quote)

    signals = pipeline_engine.run(
        execute=False,
        connect_broker=False,
        market_data=MarketDataBundle(data=bundle_data),
    )

    assert len(signals) == len(pipeline_engine.config.trading.symbols)
    for signal in signals:
        assert isinstance(signal, TradeSignal)
        assert signal.decision in {"TRADE", "NO_TRADE"}
        assert signal.direction in {"buy", "sell", "none"}
        assert signal.mode in {"scalp", "harvest", "normal"}
        assert signal.reason
        assert signal.trace_id
        assert 0.0 <= signal.confidence <= 1.0


def test_full_pipeline_signal_schema(pipeline_engine: KraitosEngine):
    frame = _candle_frame()
    symbol = pipeline_engine.config.trading.symbols[0]
    bundle = MarketDataBundle(
        data={symbol: {tf: frame for tf in PIPELINE_TIMEFRAMES}}
    )
    quote = SimpleNamespace(bid=1.1000, ask=1.1001, spread=0.0001)

    pipeline_engine._connector.get_quote = MagicMock(return_value=quote)

    signals = pipeline_engine.run(
        symbols=[symbol],
        execute=False,
        connect_broker=False,
        market_data=bundle,
    )
    payload = signals[0].to_dict()
    expected_keys = {
        "symbol",
        "decision",
        "direction",
        "confidence",
        "entry",
        "stop_loss",
        "take_profit",
        "risk_pct",
        "lot_size",
        "reason",
        "mode",
        "trace_id",
        "executed",
        "execution_id",
    }
    assert expected_keys.issubset(payload.keys())


def test_simulated_execution_never_calls_live_orders(pipeline_engine: KraitosEngine):
    frame = _candle_frame()
    symbol = "EURUSD"
    bundle = MarketDataBundle(
        data={symbol: {tf: frame for tf in PIPELINE_TIMEFRAMES}}
    )
    quote = SimpleNamespace(bid=1.1000, ask=1.1001, spread=0.0001)

    pipeline_engine._connector.get_quote = MagicMock(return_value=quote)
    pipeline_engine._connector.place_market_order = MagicMock(
        side_effect=AssertionError("live orders must not be placed")
    )

    signals = pipeline_engine.run(
        symbols=[symbol],
        execute=True,
        connect_broker=False,
        market_data=bundle,
    )

    assert len(signals) == 1
    pipeline_engine._connector.place_market_order.assert_not_called()


def test_main_entrypoint_runs_offline(tmp_path: Path):
    root = _project_with_paper_config(tmp_path)
    config_path = root / "config" / "config.yaml"

    with patch("main.initialize_runtime") as init_mock, patch(
        "main.KraitosEngine.build"
    ) as build_mock:
        config = load_config(config_path)
        event_logger = KraitosEventLogger(root / "logs")
        init_mock.return_value = (config, event_logger, root / "logs")

        engine = MagicMock()
        engine.run.return_value = [
            TradeSignal(
                symbol="EURUSD",
                decision="NO_TRADE",
                direction="none",
                confidence=0.5,
                entry=None,
                stop_loss=None,
                take_profit=None,
                risk_pct=1.0,
                lot_size=0.0,
                reason="test",
                mode="normal",
                trace_id="abc",
            )
        ]
        build_mock.return_value = engine

        from main import main

        assert main(symbols=("EURUSD",), execute=False) == 0
        engine.run.assert_called_once()
