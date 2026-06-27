"""Tests for broker CSV importers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from data.importers.base import deduplicate_bars, normalize_frame
from data.importers.dukascopy_csv_importer import DukascopyCsvImporter
from data.importers.exness_csv_importer import ExnessCsvImporter
from data.importers.mt5_csv_importer import Mt5CsvImporter


def test_normalize_frame_basic() -> None:
    raw = pd.DataFrame(
        {
            "time": ["2023-01-10 08:00:00+00:00", "2023-01-10 08:01:00+00:00"],
            "open": [1.1, 1.1001],
            "high": [1.1005, 1.1006],
            "low": [1.0998, 1.0999],
            "close": [1.1002, 1.1003],
            "volume": [100, 120],
        }
    )
    out = normalize_frame(raw, symbol="EURUSD", default_spread=1.2)
    assert len(out) == 2
    assert out.iloc[0]["symbol"] == "EURUSD"
    assert out.iloc[0]["spread"] == 1.2


def test_deduplicate_bars() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2023-01-10 08:00:00+00:00", "2023-01-10 08:00:00+00:00"], utc=True
            ),
            "symbol": ["EURUSD", "EURUSD"],
            "open": [1.1, 1.1],
            "high": [1.2, 1.2],
            "low": [1.0, 1.0],
            "close": [1.15, 1.16],
            "volume": [1, 2],
            "spread": [1.0, 1.0],
        }
    )
    deduped, removed = deduplicate_bars(frame)
    assert len(deduped) == 1
    assert removed == 1


def test_mt5_date_time_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "EURUSD_M1.csv"
    csv_path.write_text(
        "Date,Time,Open,High,Low,Close,TickVolume\n"
        "2023.01.10,08:00,1.1000,1.1005,1.0995,1.1002,500\n"
        "2023.01.10,08:01,1.1002,1.1008,1.1000,1.1006,480\n",
        encoding="utf-8",
    )
    importer = Mt5CsvImporter()
    frame, report = importer.import_file(csv_path)
    assert report.ok
    assert len(frame) >= 2


def test_dukascopy_bid_ask(tmp_path: Path) -> None:
    csv_path = tmp_path / "EURUSD_dukascopy.csv"
    csv_path.write_text(
        "time,bid,ask\n"
        "2023-01-10 08:00:00,1.09990,1.10010\n"
        "2023-01-10 08:01:00,1.10000,1.10020\n",
        encoding="utf-8",
    )
    importer = DukascopyCsvImporter()
    frame, report = importer.import_file(csv_path, symbol="EURUSD")
    assert report.rows_written == 2
    assert "spread" in frame.columns


def test_exness_datetime_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "GBPUSD-exness.csv"
    csv_path.write_text(
        "datetime,open,high,low,close,tick_volume\n"
        "2023-01-10 08:00:00+00:00,1.2700,1.2705,1.2695,1.2702,900\n",
        encoding="utf-8",
    )
    importer = ExnessCsvImporter()
    frame, report = importer.import_file(csv_path)
    assert report.ok
    assert frame.iloc[0]["symbol"] == "GBPUSD"


def test_thesis_tracker_runner_close() -> None:
    from intelligence.kraitos_thesis_doctrine import reset_thesis_tracker

    tracker = reset_thesis_tracker()
    tracker.record_tp1_hit()
    tracker.record_runner_close(pnl=12.0, r_multiple=0.25, reason="take_profit")
    assert tracker.runner_continuations == 1
    assert tracker.runner_wins == 1
    assert tracker.runner_pnl_total == 12.0
