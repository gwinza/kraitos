"""Smoke tests for the application entry point."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from config import load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_config_file_exists_and_is_valid():
    """config/config.yaml should load through the validated config system."""
    config_path = PROJECT_ROOT / "config" / "config.yaml"
    config = load_config(config_path)

    assert config.raw["app"]["name"] == "Kraitos"
    assert config.account.balance > 0
    assert config.trading.paper_enabled or config.trading.live_enabled
    assert config.pipeline.execution_mode == "simulation"


def test_project_modules_exist():
    """All top-level module directories should be present."""
    modules = [
        "broker",
        "config",
        "controls",
        "core",
        "data",
        "strategies",
        "risk",
        "execution",
        "backtesting",
        "analytics",
        "dashboard",
        "monitoring",
        "validation",
        "logs",
        "tests",
    ]
    for module in modules:
        assert (PROJECT_ROOT / module).is_dir(), f"Missing module directory: {module}"


def test_integrated_pipeline_modules_exist():
    """Integrated pipeline entry points should be present."""
    required_files = [
        "main.py",
        "config/settings.py",
        "core/engine.py",
        "core/pipeline.py",
        "core/pipeline_models.py",
        "core/signal_router.py",
        "core/risk_controller.py",
        "core/trade_executor.py",
        "tests/test_full_pipeline.py",
    ]
    for relative in required_files:
        assert (PROJECT_ROOT / relative).is_file(), f"Missing file: {relative}"


def test_main_cli_help_exits_zero():
    """main.py --help should run without import errors."""
    from main import cli

    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "integrated kraitos pipeline" in result.output.lower()
    assert "command center" in result.output.lower()


def test_command_center_modules_exist():
    required_files = [
        "dashboard/cli_dashboard.py",
        "controls/manual_override.py",
        "controls/emergency_stop.py",
        "monitoring/health_monitor.py",
        "monitoring/error_reporter.py",
        "tests/test_command_center.py",
    ]
    for relative in required_files:
        assert (PROJECT_ROOT / relative).is_file(), f"Missing file: {relative}"
