"""Scan broker export directories and normalize to data/normalized/."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from data.importers.base import ImportReport, normalized_to_m1_candles, write_normalized_csv
from data.importers.dukascopy_csv_importer import DukascopyCsvImporter
from data.importers.exness_csv_importer import ExnessCsvImporter
from data.importers.mt5_csv_importer import Mt5CsvImporter

SOURCE_DIRS = {
    "mt5": ("mt5_exports", "broker_history"),
    "exness": ("exness_exports",),
    "dukascopy": ("dukascopy_exports",),
}

IMPORTERS = {
    "mt5": Mt5CsvImporter,
    "exness": ExnessCsvImporter,
    "dukascopy": DukascopyCsvImporter,
}


def import_all_sources(project_root: Path) -> list[ImportReport]:
    """Import CSVs from data/{mt5_exports,exness_exports,dukascopy_exports,broker_history,imported_csv}."""
    root = project_root.resolve()
    data_dir = root / "data"
    normalized_dir = data_dir / "normalized"
    reports: list[ImportReport] = []

    for source, importers_cls in IMPORTERS.items():
        importer = importers_cls()
        for folder in SOURCE_DIRS[source]:
            scan = data_dir / folder
            if not scan.is_dir():
                continue
            for csv_path in sorted(scan.rglob("*.csv")):
                report = importer.import_to_normalized_dir(csv_path, normalized_dir)
                reports.append(report)

    # Legacy paths
    for legacy in ("broker_history", "imported_csv"):
        scan = data_dir / legacy
        if not scan.is_dir():
            continue
        mt5 = Mt5CsvImporter()
        for csv_path in sorted(scan.rglob("*.csv")):
            report = mt5.import_to_normalized_dir(csv_path, normalized_dir)
            reports.append(report)

    return reports


def write_data_import_report(project_root: Path, reports: list[ImportReport]) -> Path:
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    ok = [r for r in reports if r.ok]
    failed = [r for r in reports if not r.ok and r.rows_read > 0]
    empty = [r for r in reports if r.rows_read == 0 and not r.errors]

    lines = [
        "# Data Import Report",
        "",
        f"**Generated:** {now}",
        "",
        "## Summary",
        "",
        f"- Files processed: **{len(reports)}**",
        f"- Successful imports: **{len(ok)}**",
        f"- Failed: **{len(failed)}**",
        f"- No CSV files found: **{len(reports) == 0}**",
        "",
        "## Expected drop locations",
        "",
        "- `data/mt5_exports/` — MT5 History Center exports",
        "- `data/exness_exports/` — Exness historical CSV",
        "- `data/dukascopy_exports/` — Dukascopy tick/minute CSV",
        "- `data/broker_history/` — legacy broker path (also scanned)",
        "",
        "Normalized output: `data/normalized/{SYMBOL}_M1.csv`",
        "",
        "## Normalized schema",
        "",
        "`timestamp, symbol, open, high, low, close, volume, spread` (UTC)",
        "",
        "## Import details",
        "",
    ]
    if not reports:
        lines.extend(
            [
                "No broker CSV files detected. Reality validation will use per-regime synthetic "
                "fallback until real files are placed in the directories above.",
                "",
            ]
        )
    for report in reports:
        status = "OK" if report.ok else "FAIL"
        lines.append(f"### {report.symbol} ({report.source}) — {status}")
        lines.append(f"- Input: `{report.input_path}`")
        lines.append(f"- Output: `{report.output_path or 'n/a'}`")
        lines.append(
            f"- Rows: {report.rows_read} read → {report.rows_written} written "
            f"(dupes removed: {report.duplicates_removed}, gaps filled: {report.missing_filled})"
        )
        if report.errors:
            lines.append(f"- Errors: {', '.join(report.errors)}")
        if report.warnings:
            lines.append(f"- Warnings: {', '.join(report.warnings)}")
        lines.append("")

    path = logs / "data_import_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_import_pipeline(project_root: Path) -> tuple[list[ImportReport], Path]:
    reports = import_all_sources(project_root)
    report_path = write_data_import_report(project_root, reports)
    return reports, report_path


def load_normalized_universe(
    project_root: Path,
    symbols: tuple[str, ...],
) -> dict[str, "pd.DataFrame"]:
    """Load normalized M1 candles for symbols that have been imported."""
    import pandas as pd

    from backtesting.candle_resampler import build_multitimeframe_candles

    normalized_dir = project_root / "data" / "normalized"
    universe: dict[str, dict] = {}
    for symbol in symbols:
        path = normalized_dir / f"{symbol.upper()}_M1.csv"
        if not path.exists():
            candidates = sorted(normalized_dir.glob(f"{symbol.upper()}*.csv"))
            path = candidates[0] if candidates else None
        if path is None or not path.exists():
            continue
        raw = pd.read_csv(path)
        raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce")
        m1 = normalized_to_m1_candles(raw)
        universe[symbol] = build_multitimeframe_candles(m1)
    return universe
