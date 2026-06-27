"""Tests for broker data readiness checker."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from validation.broker_data_readiness import (
    REQUIRED_SYMBOLS,
    check_symbol,
    check_symbol_file,
    find_symbol_csv,
    run_broker_data_readiness,
)


def _write_m1_csv(
    path: Path,
    *,
    symbol: str = "EURUSD",
    start: str = "2022-01-03 00:00:00+00:00",
    bars: int = 120_000,
) -> None:
    """Write synthetic M1 CSV with multi-year timestamps."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = pd.date_range(start, periods=bars, freq="1min", tz="UTC")
    # Spread across years by jumping forward for year coverage in smaller fixtures
    frame = pd.DataFrame(
        {
            "time": ts.strftime("%Y-%m-%d %H:%M:%S%z"),
            "open": 1.1,
            "high": 1.1005,
            "low": 1.0995,
            "close": 1.1002,
            "volume": 100,
        }
    )
    frame.to_csv(path, index=False)


def _write_multi_year_csv(path: Path, *, bars_per_year: int = 90_000) -> None:
    """Write CSV with explicit 2022-2026 year segments."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for year in (2022, 2023, 2024, 2025, 2026):
        start = f"{year}-01-03 00:00:00+00:00"
        ts = pd.date_range(start, periods=bars_per_year if year != 2026 else 5_000, freq="1min", tz="UTC")
        for t in ts:
            rows.append(
                {
                    "time": t.strftime("%Y-%m-%d %H:%M:%S%z"),
                    "open": 1.1,
                    "high": 1.1005,
                    "low": 1.0995,
                    "close": 1.1002,
                    "volume": 100,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_find_symbol_csv_prefers_mt5_exports(tmp_path: Path) -> None:
    mt5 = tmp_path / "data" / "mt5_exports" / "EURUSD_M1.csv"
    other = tmp_path / "data" / "exness_exports" / "EURUSD-old.csv"
    mt5.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    mt5.write_text("time,open,high,low,close,volume\n", encoding="utf-8")
    other.write_text("time,open,high,low,close,volume\n", encoding="utf-8")
    found = find_symbol_csv(tmp_path, "EURUSD")
    assert found == mt5


def test_check_symbol_missing(tmp_path: Path) -> None:
    (tmp_path / "data" / "mt5_exports").mkdir(parents=True)
    result = check_symbol(tmp_path, "EURUSD")
    assert result.status == "MISSING"
    assert not result.ready


def test_check_symbol_bad_format_no_ohlc(tmp_path: Path) -> None:
    path = tmp_path / "data" / "mt5_exports" / "EURUSD_M1.csv"
    path.parent.mkdir(parents=True)
    path.write_text("time,price\n2022-01-03 00:00:00,1.1\n", encoding="utf-8")
    result = check_symbol_file(path, "EURUSD")
    assert result.status == "BAD FORMAT"
    assert "open" in result.missing_columns


def test_check_symbol_not_m1(tmp_path: Path) -> None:
    path = tmp_path / "data" / "mt5_exports" / "EURUSD_M1.csv"
    path.parent.mkdir(parents=True)
    ts = pd.date_range("2022-01-03", periods=5000, freq="5min", tz="UTC")
    pd.DataFrame(
        {
            "time": ts,
            "open": 1.1,
            "high": 1.2,
            "low": 1.0,
            "close": 1.15,
            "volume": 50,
        }
    ).to_csv(path, index=False)
    result = check_symbol_file(path, "EURUSD")
    assert result.status == "BAD FORMAT"
    assert not result.is_m1


def test_check_symbol_not_enough_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("validation.broker_data_readiness.MIN_TOTAL_BARS", 1000)
    path = tmp_path / "data" / "mt5_exports" / "EURUSD_M1.csv"
    _write_m1_csv(path, bars=500)
    result = check_symbol_file(path, "EURUSD")
    assert result.status == "NOT ENOUGH DATA"


def test_check_symbol_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("validation.broker_data_readiness.MIN_TOTAL_BARS", 1000)
    monkeypatch.setattr("validation.broker_data_readiness.MIN_YEAR_BARS_FULL", 200)
    monkeypatch.setattr("validation.broker_data_readiness.MIN_YEAR_BARS_2026", 50)
    monkeypatch.setattr("validation.broker_data_readiness.MAX_GAP_RATIO", 999_999.0)
    path = tmp_path / "data" / "mt5_exports" / "EURUSD_M1.csv"
    _write_multi_year_csv(path, bars_per_year=250)
    result = check_symbol_file(path, "EURUSD")
    assert result.status == "READY"
    assert result.is_m1
    assert result.rows >= 1000


def test_run_readiness_all_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "data" / "mt5_exports").mkdir(parents=True)
    (tmp_path / "logs").mkdir(parents=True)
    result = run_broker_data_readiness(tmp_path)
    assert not result.all_ready
    assert result.ready_count == 0
    assert len(result.symbols) == len(REQUIRED_SYMBOLS)
    report = tmp_path / "logs" / "broker_data_readiness_report.md"
    assert report.exists()


def test_run_readiness_all_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("validation.broker_data_readiness.MIN_TOTAL_BARS", 1000)
    monkeypatch.setattr("validation.broker_data_readiness.MIN_YEAR_BARS_FULL", 200)
    monkeypatch.setattr("validation.broker_data_readiness.MIN_YEAR_BARS_2026", 50)
    monkeypatch.setattr("validation.broker_data_readiness.MAX_GAP_RATIO", 999_999.0)
    (tmp_path / "logs").mkdir(parents=True)
    for sym in REQUIRED_SYMBOLS:
        _write_multi_year_csv(tmp_path / "data" / "mt5_exports" / f"{sym}_M1.csv", bars_per_year=250)
    result = run_broker_data_readiness(tmp_path)
    assert result.all_ready
    assert result.ready_count == len(REQUIRED_SYMBOLS)
