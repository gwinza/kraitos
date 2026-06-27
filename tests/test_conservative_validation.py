"""Tests for conservative walk-forward validation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from validation.conservative_validation import (
    RESEARCH_ONLY_LABEL,
    WalkForwardConfig,
    compute_data_quality_score,
    generate_walk_forward_universe,
    run_conservative_validation,
    validation_payload_from_result,
)
from backtesting.performance_report import PerformanceMetrics
from validation.metrics_collector import _empty_metrics
from validation.strategy_validator import StrategyValidationInput, StrategyValidator

pytestmark = pytest.mark.offline


def _config_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    config_dir.joinpath("config.yaml").write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "logs").mkdir()


def test_generate_walk_forward_universe_covers_years():
    universe = generate_walk_forward_universe(
        years=(2023, 2024),
        symbols=("EURUSD",),
        m1_bars_per_year=8_000,
    )
    m1 = universe["EURUSD"]["M1"]
    times = pd.to_datetime(m1["time"], utc=True)
    years = set(times.dt.year.tolist())
    assert 2023 in years
    assert 2024 in years


def _passing_backtest() -> PerformanceMetrics:
    return PerformanceMetrics(
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


def test_trust_verdict_blocks_live_ready():
    validator = StrategyValidator()
    result = validator.validate(
        StrategyValidationInput(
            backtest=_passing_backtest(),
            paper=_passing_backtest(),
            trust_verdict="INVALID",
        )
    )
    assert result.status == "FAILED_VALIDATION"
    assert result.status != "LIVE_READY"


def test_run_conservative_validation_quick(tmp_path: Path):
    _config_dir(tmp_path)
    result = run_conservative_validation(
        tmp_path,
        config=WalkForwardConfig(
            years=(2024, 2025),
            symbols=("EURUSD", "GBPUSD"),
            m1_bars_per_year=12_000,
            step=8,
            include_optimistic_demo=True,
        ),
    )
    assert result.conservative_metrics.total_trades >= 0
    assert result.data_source == "synthetic"
    assert result.trust_verdict == "QUESTIONABLE"
    assert result.conservative_journal_path.exists()
    payload = validation_payload_from_result(
        result,
        paper_metrics=_empty_metrics(10_000.0),
        error_summary={
            "expected_test_errors": [],
            "real_runtime_errors": [],
            "critical_runtime_errors": [],
            "expected_test_count": 0,
            "real_runtime_count": 0,
            "critical_runtime_count": 0,
        },
    )
    assert payload["validation_engine"] == "conservative"
    assert payload["data_source"] == "synthetic"
    assert payload["trust_verdict"] == "QUESTIONABLE"
    assert payload["optimistic_label"] == RESEARCH_ONLY_LABEL
    assert "conservative_metrics" in payload
    assert "walk_forward" in payload


def test_data_quality_score_caps_synthetic():
    from validation.conservative_validation import ValidationSplits

    score = compute_data_quality_score(
        years_covered=2,
        conservative_trades=600,
        trust_verdict="QUESTIONABLE",
        splits=ValidationSplits(by_symbol={"EURUSD": {}}, by_regime={"trending": {}}),
        data_source="synthetic",
        symbol_count=11,
    )
    assert score <= 75.0


def test_walk_forward_symbols_include_expanded_set():
    from validation.data_universe import WALK_FORWARD_SYMBOLS

    for symbol in ("AUDUSD", "XAUUSD", "EURJPY"):
        assert symbol in WALK_FORWARD_SYMBOLS
