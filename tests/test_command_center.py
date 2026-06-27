"""Tests for the Kraitos command center and runtime controls."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from backtesting.performance_report import PerformanceMetrics
from config import load_config
from controls.emergency_stop import EmergencyStop
from controls.manual_override import ManualOverride
from controls.trading_gate import TradingGate
from core.signal_router import TradeSignal
from dashboard.cli_dashboard import CommandCenter
from monitoring.error_reporter import ErrorReporter
from monitoring.health_monitor import HealthMonitor
from validation.strategy_validator import ValidationResult

pytestmark = pytest.mark.offline

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _passing_metrics(trades: int) -> PerformanceMetrics:
    winners = int(trades * 0.55)
    return PerformanceMetrics(
        initial_balance=100.0,
        final_balance=110.0,
        equity=110.0,
        total_return_pct=10.0,
        max_drawdown_pct=8.0,
        daily_drawdown_pct=0.0,
        win_rate=0.55,
        profit_factor=1.5,
        average_r=0.4,
        total_trades=trades,
        winning_trades=winners,
        losing_trades=trades - winners,
        gross_profit=15.0,
        gross_loss=10.0,
        daily_pnl={},
        trading_disabled=False,
        trading_halted_daily=False,
    )


def _write_validation_metrics(tmp_path: Path) -> None:
    conservative = asdict(_passing_metrics(500))
    payload = {
        "validation_engine": "conservative",
        "conservative_metrics": conservative,
        "backtest": conservative,
        "optimistic_metrics": asdict(_passing_metrics(100)),
        "optimistic_label": "research_demo_only",
        "trust_verdict": "TRUSTWORTHY",
        "data_quality_score": 60.0,
        "paper": asdict(_passing_metrics(30)),
    }
    path = tmp_path / "logs" / "validation_metrics.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def config(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source = PROJECT_ROOT / "config" / "config.yaml"
    config_dir.joinpath("config.yaml").write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "logs").mkdir()
    return load_config(config_dir / "config.yaml")


def test_emergency_stop_blocks_trading(tmp_path: Path, config):
    stop = EmergencyStop(tmp_path)
    gate = TradingGate(project_root=tmp_path, config=config, emergency_stop=stop)

    stop.activate("test halt")
    allowed, reason = gate.can_execute()
    assert allowed is False
    assert "Emergency stop" in reason


def test_manual_override_pause_blocks_trading(tmp_path: Path, config):
    override = ManualOverride(tmp_path)
    gate = TradingGate(project_root=tmp_path, config=config, manual_override=override)

    override.pause("maintenance")
    allowed, reason = gate.can_execute()
    assert allowed is False
    assert "paused" in reason.lower()


def test_live_trading_blocked_without_live_ready(tmp_path: Path, config):
    gate = TradingGate(project_root=tmp_path, config=config)
    allowed, reason = gate.live_allowed()
    assert allowed is False
    assert "disabled" in reason.lower() or "LIVE_READY" in reason


def test_live_trading_allowed_when_validation_live_ready(tmp_path: Path, config):
    _write_validation_metrics(tmp_path)
    live_config = config
    validation = ValidationResult(
        status="LIVE_READY",
        strategy_name="test",
        live_trading_enabled=True,
    )

    class LiveConfig:
        def __init__(self, base):
            self.account = base.account
            self.risk = base.risk
            self.trading = base.trading
            self.pipeline = base.pipeline
            self.raw = dict(base.raw)

        @property
        def simulation_only(self):
            return False

    patched = LiveConfig(live_config)
    patched.trading = type(
        "T",
        (),
        {
            "live_enabled": True,
            "paper_enabled": False,
            "symbols": live_config.trading.symbols,
            "timeframes": live_config.trading.timeframes,
            "spread_limits": live_config.trading.spread_limits,
            "sessions": live_config.trading.sessions,
            "news_filter_enabled": live_config.trading.news_filter_enabled,
        },
    )()
    patched.pipeline = type(
        "P",
        (),
        {"execution_mode": "live", "execute_trades": True},
    )()

    from config.broker_settings import BrokerSettings

    broker_settings = BrokerSettings(
        broker_name="mt5",
        account_id="demo-1",
        live_trading=True,
        enable_live_trading=True,
        max_risk_per_trade_pct=1.0,
        daily_drawdown_limit_pct=5.0,
    )
    gate = TradingGate(
        project_root=tmp_path,
        config=patched,  # type: ignore[arg-type]
        validation_result=validation,
        broker_settings=broker_settings,
    )

    allowed, reason = gate.live_allowed()
    assert allowed is True
    assert "approved" in reason.lower()


def test_command_center_renders_mode_and_account(tmp_path: Path, config):
    center = CommandCenter(project_root=tmp_path, config=config)
    text = center.render()

    assert "KRAITOS COMMAND CENTER" in text
    assert "Mode:" in text
    assert "Balance:" in text
    assert "LATEST SIGNAL" in text


def test_command_center_shows_paper_mode_by_default(tmp_path: Path, config):
    snapshot = CommandCenter(project_root=tmp_path, config=config).collect_snapshot()
    assert snapshot.mode == "paper"
    assert snapshot.live_trading_allowed is False


def test_error_reporter_logs_critical_errors(tmp_path: Path):
    reporter = ErrorReporter(project_root=tmp_path, event_logger=None)
    reporter.report("disk failure", critical=True)
    assert reporter.critical_errors == ("disk failure",)


def test_health_monitor_reports_emergency_stop(tmp_path: Path, config):
    EmergencyStop(tmp_path).activate("halt")
    gate = TradingGate(project_root=tmp_path, config=config)
    reporter = ErrorReporter(project_root=tmp_path)
    monitor = HealthMonitor(
        project_root=tmp_path,
        config=config,
        trading_gate=gate,
        error_reporter=reporter,
    )
    health = monitor.evaluate()
    emergency = next(c for c in health.checks if c.name == "emergency_stop")
    assert emergency.healthy is False


def test_command_center_updates_latest_signal(tmp_path: Path, config):
    center = CommandCenter(project_root=tmp_path, config=config)
    signals = [
        TradeSignal(
            symbol="EURUSD",
            decision="TRADE",
            direction="buy",
            confidence=0.8,
            entry=1.1,
            stop_loss=1.098,
            take_profit=1.104,
            risk_pct=1.0,
            lot_size=0.01,
            reason="test signal",
            mode="harvest",
            trace_id="trace-1",
        )
    ]
    center.update_signals(signals)
    snapshot = center.collect_snapshot()
    assert "EURUSD TRADE buy" in snapshot.latest_signal
    assert snapshot.latest_reason == "test signal"


def test_main_launches_command_center(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source = PROJECT_ROOT / "config" / "config.yaml"
    config_dir.joinpath("config.yaml").write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "logs").mkdir()

    monkeypatch.setattr("main.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        "core.bootstrap.load_application_config",
        lambda root: load_config(config_dir / "config.yaml"),
    )
    monkeypatch.setattr(
        "core.bootstrap.init_event_logger",
        lambda log_dir: __import__("logs", fromlist=["KraitosEventLogger"]).KraitosEventLogger(
            log_dir
        ),
    )

    mock_engine = MagicMock()
    mock_engine.run.return_value = []
    mock_engine._runtime.paper_trader = MagicMock()
    mock_engine._runtime.paper_trader.snapshot.return_value = MagicMock(
        balance=10_000.0,
        equity=10_000.0,
        initial_balance=10_000.0,
        open_trades=(),
        trade_history=(),
    )
    monkeypatch.setattr("main.KraitosEngine.build", lambda **kwargs: mock_engine)

    from main import cli

    result = CliRunner().invoke(cli, ["--no-execute"])
    assert result.exit_code == 0
    assert "KRAITOS COMMAND CENTER" in result.output


def test_main_emergency_stop_blocks_execute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source = PROJECT_ROOT / "config" / "config.yaml"
    config_dir.joinpath("config.yaml").write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "logs").mkdir()

    monkeypatch.setattr("main.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        "core.bootstrap.load_application_config",
        lambda root: load_config(config_dir / "config.yaml"),
    )
    monkeypatch.setattr(
        "core.bootstrap.init_event_logger",
        lambda log_dir: __import__("logs", fromlist=["KraitosEventLogger"]).KraitosEventLogger(
            log_dir
        ),
    )

    mock_engine = MagicMock()
    mock_engine.run.return_value = []
    mock_engine._runtime.paper_trader = MagicMock()
    mock_engine._runtime.paper_trader.snapshot.return_value = MagicMock(
        balance=10_000.0,
        equity=10_000.0,
        initial_balance=10_000.0,
        open_trades=(),
        trade_history=(),
    )
    monkeypatch.setattr("main.KraitosEngine.build", lambda **kwargs: mock_engine)

    from main import cli

    result = CliRunner().invoke(cli, ["--emergency-stop", "--execute", "--no-dashboard"])
    assert result.exit_code == 0
    mock_engine.run.assert_called_once()
    assert mock_engine.run.call_args.kwargs.get("execute") is False
