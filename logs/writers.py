"""CSV and JSON log writers."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from logs.models import ALL_CATEGORIES, EventCategory, LogRecord

CSV_COLUMNS = [
    "event_id",
    "trace_id",
    "timestamp",
    "category",
    "event_type",
    "symbol",
    "message",
    "data_json",
]


class DualFormatWriter:
    """Write log records to category-specific CSV and JSONL files."""

    def __init__(self, base_dir: Path) -> None:
        self._csv_dir = base_dir / "csv"
        self._json_dir = base_dir / "json"
        self._csv_dir.mkdir(parents=True, exist_ok=True)
        self._json_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_csv_headers()

    def write(self, record: LogRecord) -> None:
        self._append_csv(record)
        self._append_jsonl(record)

    def _ensure_csv_headers(self) -> None:
        for category in ALL_CATEGORIES:
            path = self._csv_path(category)
            if path.exists():
                continue
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
                writer.writeheader()

    def _append_csv(self, record: LogRecord) -> None:
        row = {
            "event_id": record.event_id,
            "trace_id": record.trace_id,
            "timestamp": record.timestamp,
            "category": record.category,
            "event_type": record.event_type,
            "symbol": record.symbol or "",
            "message": record.message,
            "data_json": json.dumps(record.data, default=str),
        }
        with self._csv_path(record.category).open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writerow(row)

    def _append_jsonl(self, record: LogRecord) -> None:
        payload = {
            "event_id": record.event_id,
            "trace_id": record.trace_id,
            "timestamp": record.timestamp,
            "category": record.category,
            "event_type": record.event_type,
            "symbol": record.symbol,
            "message": record.message,
            "data": record.data,
        }
        with self._json_path(record.category).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")

    def _csv_path(self, category: EventCategory) -> Path:
        return self._csv_dir / f"{category}.csv"

    def _json_path(self, category: EventCategory) -> Path:
        return self._json_dir / f"{category}.jsonl"
