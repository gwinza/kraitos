"""Import Exness historical export CSV files."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from data.importers.base import (
    ImportReport,
    deduplicate_bars,
    fill_missing_sessions,
    normalize_frame,
    normalized_to_m1_candles,
    write_normalized_csv,
)


class ExnessCsvImporter:
    """Parse Exness terminal / API historical exports."""

    def __init__(self, *, default_spread: float = 1.0, fill_gaps: bool = True) -> None:
        self.default_spread = default_spread
        self.fill_gaps = fill_gaps

    @staticmethod
    def infer_symbol(path: Path) -> str:
        stem = path.stem.upper()
        match = re.search(r"([A-Z]{6,7}|XAUUSD)", stem)
        return match.group(1) if match else stem.split("-")[0].upper()

    def _preprocess_exness(self, raw: pd.DataFrame) -> pd.DataFrame:
        cols = {c.lower().strip(): c for c in raw.columns}
        if "datetime" in cols:
            raw = raw.rename(columns={cols["datetime"]: "timestamp"})
        elif "date" in cols and "time" in cols:
            raw = raw.copy()
            raw["timestamp"] = raw[cols["date"]].astype(str) + " " + raw[cols["time"]].astype(str)
        if "tick_volume" in cols and "volume" not in cols:
            raw = raw.rename(columns={cols["tick_volume"]: "volume"})
        return raw

    def import_file(self, path: Path, *, symbol: str | None = None) -> tuple[pd.DataFrame, ImportReport]:
        sym = (symbol or self.infer_symbol(path)).upper()
        raw = pd.read_csv(path)
        raw = self._preprocess_exness(raw)
        report = ImportReport(
            source="exness",
            symbol=sym,
            input_path=str(path),
            output_path="",
            rows_read=len(raw),
        )
        if raw.empty:
            report.errors.append("empty Exness file")
            return pd.DataFrame(), report

        normalized = normalize_frame(raw, symbol=sym, default_spread=self.default_spread)
        normalized, report.duplicates_removed = deduplicate_bars(normalized)
        if self.fill_gaps:
            normalized, report.missing_filled = fill_missing_sessions(normalized)
        report.rows_written = len(normalized)
        return normalized, report

    def import_to_normalized_dir(
        self,
        input_path: Path,
        output_dir: Path,
        *,
        symbol: str | None = None,
    ) -> ImportReport:
        frame, report = self.import_file(input_path, symbol=symbol)
        out_path = output_dir / f"{report.symbol}_M1.csv"
        if not frame.empty:
            write_normalized_csv(frame, out_path)
            report.output_path = str(out_path)
        return report

    def to_m1(self, normalized: pd.DataFrame) -> pd.DataFrame:
        return normalized_to_m1_candles(normalized)
