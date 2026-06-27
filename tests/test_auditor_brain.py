"""Tests for Auditor Brain — conservative model, no story/harvest scoring imports."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backtesting.execution_model import ExecutionCostConfig
from backtesting.performance_report import PerformanceMetrics
from brains.auditor_brain import AuditorBrain

pytestmark = pytest.mark.offline

FORBIDDEN_AUDITOR_IMPORTS = frozenset({
    "intelligence.market_story_engine",
    "intelligence.story_forecast_engine",
    "intelligence.harvest_opportunity_score",
    "strategies.harvest_engine",
    "council.opportunity_hunter_council",
})


def _project_root(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    config_dir.joinpath("config.yaml").write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "logs").mkdir()
    return tmp_path


def test_auditor_brain_module_has_no_story_scoring_imports():
    source = Path(__file__).resolve().parent.parent / "brains" / "auditor_brain.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    violations = imported & FORBIDDEN_AUDITOR_IMPORTS
    assert not violations, f"Auditor brain imports discovery modules: {violations}"


def test_apply_conservative_execution_adds_spread(tmp_path: Path):
    auditor = AuditorBrain(_project_root(tmp_path))
    costs = ExecutionCostConfig(spread_pips=1.2, slippage_pips=0.3)
    result = auditor.apply_conservative_execution(
        direction="buy",
        open_price=1.1000,
        symbol="EURUSD",
        costs=costs,
        lot_size=0.10,
    )
    assert result.fill_price > 1.1000
    assert result.commission > 0


def test_apply_conservative_exit_works_against_trader(tmp_path: Path):
    auditor = AuditorBrain(_project_root(tmp_path))
    costs = ExecutionCostConfig(spread_pips=1.2, slippage_pips=0.3)
    result = auditor.apply_conservative_exit(
        direction="buy",
        raw_price=1.1050,
        symbol="EURUSD",
        costs=costs,
        lot_size=0.10,
    )
    assert result.fill_price < 1.1050


def test_validation_gates_are_diagnostic_only(tmp_path: Path):
    auditor = AuditorBrain(_project_root(tmp_path))
    metrics = PerformanceMetrics(
        initial_balance=10_000.0,
        final_balance=11_000.0,
        equity=11_000.0,
        total_return_pct=10.0,
        max_drawdown_pct=5.0,
        daily_drawdown_pct=0.0,
        win_rate=0.55,
        profit_factor=1.5,
        average_r=0.4,
        total_trades=500,
        winning_trades=275,
        losing_trades=225,
        gross_profit=15.0,
        gross_loss=10.0,
        daily_pnl={},
        trading_disabled=False,
        trading_halted_daily=False,
    )
    report = auditor.check_validation_gates(metrics)
    assert report.diagnostic_only is True
    assert isinstance(report.gates, dict)


def test_auditor_verify_run_quick(tmp_path: Path):
    auditor = AuditorBrain(_project_root(tmp_path))
    from validation.conservative_validation import WalkForwardConfig

    result = auditor.verify_run(
        config=WalkForwardConfig(
            years=(2024, 2025),
            symbols=("EURUSD", "GBPUSD"),
            m1_bars_per_year=8_000,
            step=8,
            include_optimistic_demo=False,
        ),
        reset_journal=True,
    )
    assert result.conservative_metrics.total_trades >= 0
    assert auditor.stats.validation_runs == 1
    assert result.conservative_journal_path.exists()
