"""Import MetaTrader 5 exported OHLCV CSV files."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from data.importers.base import (
    ImportReport,
    deduplicate_bars,
    fill_missing_sessions,
    import_csv_file,
    normalize_frame,
    normalized_to_m1_candles,
    write_normalized_csv,
)


class Mt5CsvImporter:
    """Parse MT5 History Center / terminal CSV exports."""

    def __init__(self, *, default_spread: float = 1.2, fill_gaps: bool = True) -> None:
        self.default_spread = default_spread
        self.fill_gaps = fill_gaps

    @staticmethod
    def infer_symbol(path: Path) -> str:
        stem = path.stem.upper()
        match = re.search(r"([A-Z]{6,7}|XAUUSD|XAGUSD)", stem)
        return match.group(1) if match else stem.split("_")[0].upper()

    def _preprocess_mt5(self, raw: pd.DataFrame) -> pd.DataFrame:
        """Handle separate Date/Time columns and tab-separated MT5 exports."""
        cols = {c.lower(): c for c in raw.columns}
        if "date" in cols and "time" in cols:
            combined = raw[cols["date"]].astype(str) + " " + raw[cols["time"]].astype(str)
            raw = raw.copy()
            raw["timestamp"] = combined
        elif "<date>" in [c.lower() for c in raw.columns]:
            mapping = {}
            for c in raw.columns:
                cl = c.strip("<>").lower()
                mapping[c] = cl
            raw = raw.rename(columns=mapping)
        return raw

    def import_file(self, path: Path, *, symbol: str | None = None) -> tuple[pd.DataFrame, ImportReport]:
        sym = (symbol or self.infer_symbol(path)).upper()
        try:
            raw = pd.read_csv(path, sep=None, engine="python")
        except Exception:
            raw = pd.read_csv(path)
        raw = self._preprocess_mt5(raw)
        report = ImportReport(
            source="mt5",
            symbol=sym,
            input_path=str(path),
            output_path="",
            rows_read=len(raw),
        )
        if raw.empty:
            report.errors.append("empty MT5 file")
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
