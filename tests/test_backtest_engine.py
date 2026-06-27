"""Tests for the pipeline-backed backtest engine."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from backtesting.backtest_engine import BacktestEngine, BacktestEngineConfig
from backtesting.performance_report import PerformanceReport
from config import load_config
from core.pipeline import TradingPipeline
from core.pipeline_models import PipelineResult
from core.risk_controller import RiskController
from core.runtime import KraitosRuntime
from core.signal_router import SignalRouter, TradeSignal
from logs.event_logger import KraitosEventLogger
from paper_trading.virtual_account import ValidationConfig
from risk.models import RiskDecision
from strategies.models import HarvestDecision, RegimeResult

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


def _build_stack(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    config_dir.joinpath("config.yaml").write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "logs").mkdir()
    config = load_config(config_dir / "config.yaml")
    event_logger = KraitosEventLogger(tmp_path / "logs")
    runtime = KraitosRuntime.build(
        project_root=tmp_path,
        config=config,
        event_logger=event_logger,
    )
    risk_controller = RiskController(
        config=config,
        risk_manager=runtime.risk_manager,
        paper_trader=runtime.paper_trader,
        project_root=tmp_path,
    )
    pipeline = TradingPipeline(
        config=config,
        regime_detector=runtime.regime_detector,
        bias_analyzer=runtime.bias_analyzer,
        structure_analyzer=runtime.structure_analyzer,
        harvest_engine=runtime.harvest_engine,
        micro_scalper=runtime.micro_scalper,
        entry_engine=runtime.entry_engine,
        risk_controller=risk_controller,
        news_filter=runtime.news_filter,
        pair_analyzer=runtime.pair_analyzer,
        project_root=tmp_path,
    )
    return config, pipeline, risk_controller


def test_backtest_engine_runs_pipeline_without_live_orders(tmp_path: Path):
    config, pipeline, risk_controller = _build_stack(tmp_path)
    frame = _candle_frame(150)
    candles = {
        "EURUSD": {tf: frame for tf in PIPELINE_TIMEFRAMES},
        "GBPUSD": {tf: frame for tf in PIPELINE_TIMEFRAMES},
    }

    engine = BacktestEngine(
        config=config,
        pipeline=pipeline,
        risk_controller=risk_controller,
        engine_config=BacktestEngineConfig(
            step=30,
            min_warmup_bars=60,
            validation=ValidationConfig(initial_balance=100.0, risk_per_trade_pct=1.0),
        ),
        journal_path=tmp_path / "logs" / "trade_journal.csv",
    )
    engine.risk_controller.set_portfolio_builder(
        lambda: engine.account.portfolio_state(risk_controller.risk_manager)
    )

    result = engine.run(candles)

    assert result.account is not None
    assert result.account.balance == pytest.approx(100.0, rel=0.5)
    assert result.report is not None
    assert "Kraitos Validation Performance" in result.summary
    assert (tmp_path / "logs" / "trade_journal.csv").exists()
    assert isinstance(result.signals, list)


def test_backtest_engine_simulates_trade_from_mocked_signal(tmp_path: Path):
    config, pipeline, risk_controller = _build_stack(tmp_path)
    frame = _candle_frame(80)

    router = SignalRouter()
    router.route = MagicMock(
        return_value=TradeSignal(
            symbol="EURUSD",
            decision="TRADE",
            direction="buy",
            confidence=0.9,
            entry=1.1010,
            stop_loss=1.0990,
            take_profit=1.1030,
            risk_pct=1.0,
            lot_size=0.01,
            reason="mock trade",
            mode="harvest",
            trace_id="mock",
        )
    )

    pipeline.run = MagicMock(
        return_value=[
            PipelineResult(
                symbol="EURUSD",
                trace_id="mock",
                bid=1.1008,
                ask=1.1010,
                spread_pips=0.2,
                spread_limit=2.0,
                harvest=HarvestDecision(
                    mode="full",
                    allowed=True,
                    target_pips=5.0,
                    reason="ok",
                ),
                risk=RiskDecision(approved=True, reason="ok", lot_size=0.01),
                regime=RegimeResult(regime="trending", confidence=0.8, reason="ok"),  # type: ignore[arg-type]
            )
        ]
    )

    engine = BacktestEngine(
        config=config,
        pipeline=pipeline,
        risk_controller=risk_controller,
        router=router,
        engine_config=BacktestEngineConfig(
            driver_timeframe="H1",
            step=10,
            min_warmup_bars=60,
        ),
        journal_path=tmp_path / "logs" / "trade_journal.csv",
    )
    engine._has_warmup = lambda candles: True  # type: ignore[method-assign]
    engine.risk_controller.set_portfolio_builder(
        lambda: engine.account.portfolio_state(risk_controller.risk_manager)
    )

    candles = {"EURUSD": {tf: frame for tf in PIPELINE_TIMEFRAMES}}
    result = engine.run(candles, symbols=["EURUSD"])

    assert result.account is not None
    assert len(result.account.closed_entries) >= 1
    metrics = PerformanceReport(result.account).metrics()
    assert metrics.initial_balance == pytest.approx(100.0)
    assert metrics.total_trades >= 1
    assert "Win rate" in result.summary
