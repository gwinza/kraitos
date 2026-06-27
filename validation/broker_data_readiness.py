"""
Broker data readiness checker for Kraitos DNA v1.0 proof testing.

Scans import folders, validates M1 CSV quality, and reports per-symbol status.
Does NOT run full validation or modify trading logic.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd

REQUIRED_SYMBOLS: tuple[str, ...] = (
    "EURUSD",
    "GBPUSD",
    "AUDUSD",
    "USDJPY",
    "GBPJPY",
    "XAUUSD",
)

REQUIRED_YEARS: tuple[int, ...] = (2022, 2023, 2024, 2025, 2026)

SCAN_FOLDERS: tuple[str, ...] = (
    "mt5_exports",
    "exness_exports",
    "dukascopy_exports",
    "broker_history",
    "imported_csv",
)

SymbolStatus = Literal["READY", "MISSING", "INCOMPLETE", "BAD FORMAT", "NOT ENOUGH DATA"]

# ~70 weekday days of M1 bars minimum for meaningful multi-year validation
MIN_TOTAL_BARS = 100_000
MIN_YEAR_BARS_FULL = 80_000
MIN_YEAR_BARS_2026 = 3_000
MAX_DUPLICATE_RATIO = 0.01
MAX_GAP_RATIO = 0.05
M1_MEDIAN_TOLERANCE = 0.5  # minutes from 1.0


@dataclass
class SymbolReadiness:
    symbol: str
    status: SymbolStatus
    file_path: str | None = None
    rows: int = 0
    years_present: dict[int, int] = field(default_factory=dict)
    years_missing: list[int] = field(default_factory=list)
    is_m1: bool = False
    median_interval_minutes: float = 0.0
    duplicate_timestamps: int = 0
    missing_candle_gaps: int = 0
    missing_columns: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == "READY"


@dataclass
class ReadinessResult:
    symbols: dict[str, SymbolReadiness] = field(default_factory=dict)
    generated_at: str = ""
    report_path: str = ""

    @property
    def all_ready(self) -> bool:
        return bool(self.symbols) and all(s.ready for s in self.symbols.values())

    @property
    def ready_count(self) -> int:
        return sum(1 for s in self.symbols.values() if s.ready)


def _symbol_pattern(symbol: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(symbol)}\b", re.IGNORECASE)


def find_symbol_csv(project_root: Path, symbol: str) -> Path | None:
    """Locate best CSV for symbol; prefer data/mt5_exports/{SYMBOL}_M1.csv."""
    data = project_root / "data"
    preferred = data / "mt5_exports" / f"{symbol}_M1.csv"
    if preferred.is_file():
        return preferred

    pattern = _symbol_pattern(symbol)
    candidates: list[tuple[int, Path]] = []
    for folder in SCAN_FOLDERS:
        scan = data / folder
        if not scan.is_dir():
            continue
        for csv_path in scan.rglob("*.csv"):
            if pattern.search(csv_path.stem) or pattern.search(csv_path.name):
                score = 0
                if csv_path.stem.upper() == f"{symbol}_M1":
                    score += 100
                if "M1" in csv_path.stem.upper():
                    score += 50
                if folder == "mt5_exports":
                    score += 10
                candidates.append((score, csv_path))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], str(x[1])))
    return candidates[0][1]


def _resolve_timestamp_series(raw: pd.DataFrame) -> pd.Series | None:
    col_map = {c.lower().strip().strip("<>"): c for c in raw.columns}
    if "timestamp" in col_map:
        return pd.to_datetime(raw[col_map["timestamp"]], utc=True, errors="coerce")
    if "datetime" in col_map:
        return pd.to_datetime(raw[col_map["datetime"]], utc=True, errors="coerce")
    if "time" in col_map and "date" not in col_map:
        return pd.to_datetime(raw[col_map["time"]], utc=True, errors="coerce")
    if "date" in col_map and "time" in col_map:
        combined = raw[col_map["date"]].astype(str) + " " + raw[col_map["time"]].astype(str)
        return pd.to_datetime(combined, utc=True, errors="coerce")
    return None


def _has_ohlc(raw: pd.DataFrame) -> tuple[bool, list[str]]:
    col_map = {c.lower().strip().strip("<>"): c for c in raw.columns}
    missing = []
    for name in ("open", "high", "low", "close"):
        if name not in col_map:
            missing.append(name)
    return len(missing) == 0, missing


def _check_m1_frequency(ts: pd.Series) -> tuple[bool, float]:
    if len(ts) < 10:
        return False, 0.0
    sorted_ts = ts.dropna().sort_values()
    deltas = sorted_ts.diff().dt.total_seconds().div(60.0).dropna()
    if deltas.empty:
        return False, 0.0
    median = float(deltas.median())
    is_m1 = abs(median - 1.0) <= M1_MEDIAN_TOLERANCE
    return is_m1, median


def _year_coverage(ts: pd.Series) -> dict[int, int]:
    valid = ts.dropna()
    if valid.empty:
        return {}
    years = valid.dt.year.value_counts().sort_index()
    return {int(y): int(c) for y, c in years.items()}


def _count_duplicate_timestamps(ts: pd.Series) -> int:
    valid = ts.dropna()
    return int(valid.duplicated().sum())


def _count_missing_candle_gaps(ts: pd.Series, *, max_gap_minutes: int = 5) -> int:
    """Count intra-session gaps larger than max_gap_minutes (excludes weekends)."""
    valid = ts.dropna().sort_values()
    if len(valid) < 2:
        return 0
    gaps = 0
    for i in range(1, len(valid)):
        prev, cur = valid.iloc[i - 1], valid.iloc[i]
        if cur.weekday() >= 5 or prev.weekday() >= 5:
            continue
        delta_min = (cur - prev).total_seconds() / 60.0
        if delta_min > max_gap_minutes:
            gaps += int(delta_min) - 1
    return gaps


def check_symbol_file(path: Path, symbol: str) -> SymbolReadiness:
    """Validate a single broker CSV for readiness."""
    result = SymbolReadiness(symbol=symbol, status="BAD FORMAT", file_path=str(path))

    try:
        raw = pd.read_csv(path, sep=None, engine="python")
    except Exception:
        try:
            raw = pd.read_csv(path)
        except Exception as exc:
            result.issues.append(f"Cannot read CSV: {exc}")
            result.status = "BAD FORMAT"
            return result

    if raw.empty:
        result.issues.append("CSV file is empty")
        result.status = "BAD FORMAT"
        return result

    has_ohlc, missing_cols = _has_ohlc(raw)
    if not has_ohlc:
        result.missing_columns = missing_cols
        result.issues.append(f"Missing OHLC columns: {', '.join(missing_cols)}")
        result.status = "BAD FORMAT"
        return result

    ts = _resolve_timestamp_series(raw)
    if ts is None:
        result.issues.append(
            "No readable timestamp column (expected: time, timestamp, datetime, or Date+Time)"
        )
        result.status = "BAD FORMAT"
        return result

    valid_mask = ts.notna()
    valid_rows = int(valid_mask.sum())
    if valid_rows == 0:
        result.issues.append("No parseable timestamps")
        result.status = "BAD FORMAT"
        return result

    result.rows = valid_rows
    ts_valid = ts[valid_mask]

    is_m1, median = _check_m1_frequency(ts_valid)
    result.is_m1 = is_m1
    result.median_interval_minutes = median
    if not is_m1:
        result.issues.append(
            f"Data does not appear to be M1 (median interval {median:.2f} min, expected ~1.0)"
        )
        result.status = "BAD FORMAT"
        return result

    result.years_present = _year_coverage(ts_valid)
    result.duplicate_timestamps = _count_duplicate_timestamps(ts_valid)
    result.missing_candle_gaps = _count_missing_candle_gaps(ts_valid)

    for year in REQUIRED_YEARS:
        count = result.years_present.get(year, 0)
        min_needed = MIN_YEAR_BARS_2026 if year == 2026 else MIN_YEAR_BARS_FULL
        if count < min_needed:
            result.years_missing.append(year)

    if result.rows < MIN_TOTAL_BARS:
        result.issues.append(
            f"Only {result.rows:,} rows (minimum {MIN_TOTAL_BARS:,} for meaningful validation)"
        )
        result.status = "NOT ENOUGH DATA"
        return result

    if result.years_missing:
        result.issues.append(
            f"Missing or thin year coverage: {', '.join(str(y) for y in result.years_missing)}"
        )
        result.status = "INCOMPLETE"
        return result

    dup_ratio = result.duplicate_timestamps / max(result.rows, 1)
    if dup_ratio > MAX_DUPLICATE_RATIO:
        result.issues.append(
            f"Too many duplicate timestamps: {result.duplicate_timestamps:,} "
            f"({dup_ratio:.1%} of rows)"
        )
        result.status = "INCOMPLETE"
        return result

    gap_ratio = result.missing_candle_gaps / max(result.rows, 1)
    if gap_ratio > MAX_GAP_RATIO:
        result.issues.append(
            f"Excessive missing candles (gaps): {result.missing_candle_gaps:,} "
            f"({gap_ratio:.1%} of row span)"
        )
        result.status = "INCOMPLETE"
        return result

    result.status = "READY"
    return result


def check_symbol(project_root: Path, symbol: str) -> SymbolReadiness:
    """Check readiness for one symbol (file discovery + validation)."""
    path = find_symbol_csv(project_root, symbol)
    if path is None:
        return SymbolReadiness(
            symbol=symbol,
            status="MISSING",
            issues=[f"No CSV found for {symbol} in data/*_exports/"],
        )
    return check_symbol_file(path, symbol)


def run_broker_data_readiness(project_root: Path | None = None) -> ReadinessResult:
    """Scan all required symbols and build readiness result."""
    root = (project_root or Path.cwd()).resolve()
    for folder in SCAN_FOLDERS:
        (root / "data" / folder).mkdir(parents=True, exist_ok=True)

    result = ReadinessResult(generated_at=datetime.now(timezone.utc).isoformat())
    for symbol in REQUIRED_SYMBOLS:
        result.symbols[symbol] = check_symbol(root, symbol)

    report_path = write_broker_data_readiness_report(root, result)
    result.report_path = str(report_path)

    payload = {
        "generated_at": result.generated_at,
        "all_ready": result.all_ready,
        "ready_count": result.ready_count,
        "required_count": len(REQUIRED_SYMBOLS),
        "symbols": {
            sym: {
                "status": s.status,
                "file_path": s.file_path,
                "rows": s.rows,
                "years_present": s.years_present,
                "years_missing": s.years_missing,
                "issues": s.issues,
            }
            for sym, s in result.symbols.items()
        },
    }
    (root / "logs" / "broker_data_readiness.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    return result


def write_broker_data_readiness_report(
    project_root: Path,
    result: ReadinessResult,
) -> Path:
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Broker Data Readiness Report",
        "",
        f"**Generated:** {result.generated_at}",
        f"**Overall:** {result.ready_count}/{len(REQUIRED_SYMBOLS)} symbols READY",
        "",
    ]
    if result.all_ready:
        lines.extend(
            [
                "## Status: ALL READY",
                "",
                "Broker data passes readiness checks. Run broker-grade proof:",
                "",
                "```",
                "python -m validation.broker_grade_proof",
                "```",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Status: NOT READY",
                "",
                "Fix issues below, then re-run:",
                "",
                "```",
                "python -m validation.broker_data_readiness",
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "## Per-symbol status",
            "",
            "| Symbol | Status | File | Rows | M1 | Years | Issues |",
            "|--------|--------|------|------|-----|-------|--------|",
        ]
    )
    for sym in REQUIRED_SYMBOLS:
        s = result.symbols[sym]
        file_disp = f"`{s.file_path}`" if s.file_path else "—"
        years = ", ".join(str(y) for y in sorted(s.years_present)) or "—"
        issues = "; ".join(s.issues) if s.issues else "—"
        m1 = "yes" if s.is_m1 else "no"
        lines.append(
            f"| {sym} | **{s.status}** | {file_disp} | {s.rows:,} | {m1} | {years} | {issues} |"
        )

    lines.extend(
        [
            "",
            "## Required coverage",
            "",
            f"- Symbols: {', '.join(REQUIRED_SYMBOLS)}",
            f"- Timeframe: M1",
            f"- Years: {', '.join(str(y) for y in REQUIRED_YEARS)} (2026 = YTD)",
            "",
            "## Accepted filename examples",
            "",
        ]
    )
    for sym in REQUIRED_SYMBOLS:
        lines.append(f"- `data/mt5_exports/{sym}_M1.csv`")

    lines.extend(
        [
            "",
            "## Export guide",
            "",
            "See `logs/how_to_export_mt5_m1_data.md` for MT5/Exness export steps.",
            "",
        ]
    )

    path = logs / "broker_data_readiness_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _print_failure_details(result: ReadinessResult) -> None:
    print("BROKER DATA NOT READY")
    print("")
    for sym in REQUIRED_SYMBOLS:
        s = result.symbols[sym]
        if s.ready:
            continue
        print(f"  {sym}: {s.status}")
        if s.status == "MISSING":
            print(f"    - Missing file: data/mt5_exports/{sym}_M1.csv")
        if s.file_path:
            print(f"    - Found: {s.file_path}")
        if s.missing_columns:
            print(f"    - Missing columns: {', '.join(s.missing_columns)}")
        for issue in s.issues:
            print(f"    - {issue}")
        if s.years_missing:
            print(f"    - Years missing/thin: {', '.join(str(y) for y in s.years_missing)}")
    print("")
    print(f"Report: {result.report_path}")
    print("Guide:  logs/how_to_export_mt5_m1_data.md")


def main() -> int:
    result = run_broker_data_readiness()
    if result.all_ready:
        print("BROKER DATA READY — RUN:")
        print("python -m validation.broker_grade_proof")
        return 0
    _print_failure_details(result)
    return 1


if __name__ == "__main__":
    sys.exit(main())
