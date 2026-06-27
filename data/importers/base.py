"""Common normalized bar format and import utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd

NORMALIZED_COLUMNS = (
    "timestamp",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "spread",
)

SourceKind = Literal["mt5", "exness", "dukascopy", "generic"]


@dataclass
class NormalizedBar:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread: float


@dataclass
class ImportReport:
    source: SourceKind
    symbol: str
    input_path: str
    output_path: str
    rows_read: int = 0
    rows_written: int = 0
    duplicates_removed: int = 0
    missing_filled: int = 0
    timezone: str = "UTC"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.rows_written > 0 and not self.errors


def _ensure_utc(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, utc=True, errors="coerce")
    return parsed


def deduplicate_bars(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    before = len(frame)
    out = frame.drop_duplicates(subset=["timestamp", "symbol"], keep="last")
    out = out.sort_values("timestamp").reset_index(drop=True)
    return out, before - len(out)


def fill_missing_sessions(frame: pd.DataFrame, *, max_gap_minutes: int = 5) -> tuple[pd.DataFrame, int]:
    """Forward-fill small gaps within session; do not invent overnight bars."""
    if frame.empty or len(frame) < 2:
        return frame, 0
    filled = 0
    rows: list[dict] = []
    prev = frame.iloc[0].to_dict()
    rows.append(prev)
    for i in range(1, len(frame)):
        cur = frame.iloc[i].to_dict()
        gap = (cur["timestamp"] - prev["timestamp"]).total_seconds() / 60.0
        if 1 < gap <= max_gap_minutes:
            steps = int(gap) - 1
            for step in range(steps):
                ts = prev["timestamp"] + pd.Timedelta(minutes=step + 1)
                if ts.weekday() >= 5:
                    continue
                rows.append(
                    {
                        **prev,
                        "timestamp": ts.to_pydatetime(),
                        "volume": 0.0,
                    }
                )
                filled += 1
        rows.append(cur)
        prev = cur
    return pd.DataFrame(rows), filled


def normalize_frame(
    frame: pd.DataFrame,
    *,
    symbol: str,
    default_spread: float = 1.2,
) -> pd.DataFrame:
    """Map arbitrary OHLCV columns to NORMALIZED_COLUMNS."""
    col_map = {c.lower(): c for c in frame.columns}
    time_col = None
    for candidate in ("timestamp", "time", "datetime", "date"):
        if candidate in col_map:
            time_col = col_map[candidate]
            break
    if time_col is None:
        time_col = frame.columns[0]

    out = pd.DataFrame()
    out["timestamp"] = _ensure_utc(frame[time_col])
    out["symbol"] = symbol.strip().upper()

    def _col(*names: str, default: float = 0.0) -> pd.Series:
        for name in names:
            if name in col_map:
                return pd.to_numeric(frame[col_map[name]], errors="coerce").fillna(default)
        return pd.Series(default, index=frame.index)

    out["open"] = _col("open")
    out["high"] = _col("high")
    out["low"] = _col("low")
    out["close"] = _col("close")
    out["volume"] = _col("volume", "tick_volume", "vol", "tickvolume", default=1000.0)
    if "spread" in col_map:
        out["spread"] = pd.to_numeric(frame[col_map["spread"]], errors="coerce").fillna(default_spread)
    elif "spread_pips" in col_map:
        out["spread"] = pd.to_numeric(frame[col_map["spread_pips"]], errors="coerce").fillna(default_spread)
    else:
        out["spread"] = default_spread

    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"])
    out = out[(out["high"] >= out["low"]) & (out["open"] > 0) & (out["close"] > 0)]
    return out


def write_normalized_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    export = frame.copy()
    export["timestamp"] = pd.to_datetime(export["timestamp"], utc=True).dt.strftime(
        "%Y-%m-%d %H:%M:%S%z"
    )
    export.to_csv(path, index=False)


def validate_timestamp_continuity(
    frame: pd.DataFrame,
    *,
    expected_freq_minutes: int = 1,
    max_gap_minutes: int = 60,
) -> dict:
    """Audit timestamp continuity for broker proof reporting."""
    if frame.empty or len(frame) < 2:
        return {
            "bars": len(frame),
            "gaps_over_threshold": 0,
            "max_gap_minutes": 0.0,
            "duplicate_timestamps": 0,
            "year_coverage": {},
        }
    ts = pd.to_datetime(frame["timestamp"], utc=True).sort_values()
    deltas = ts.diff().dt.total_seconds().div(60.0).dropna()
    gaps = deltas[deltas > max_gap_minutes]
    years = ts.dt.year.value_counts().sort_index()
    return {
        "bars": len(frame),
        "gaps_over_threshold": int(len(gaps)),
        "max_gap_minutes": float(deltas.max()) if len(deltas) else 0.0,
        "duplicate_timestamps": int(ts.duplicated().sum()),
        "year_coverage": {str(y): int(c) for y, c in years.items()},
        "start": ts.iloc[0].isoformat(),
        "end": ts.iloc[-1].isoformat(),
    }


def import_csv_file(
    path: Path,
    *,
    symbol: str,
    source: SourceKind = "generic",
    default_spread: float = 1.2,
    fill_gaps: bool = True,
) -> tuple[pd.DataFrame, ImportReport]:
    report = ImportReport(
        source=source,
        symbol=symbol.upper(),
        input_path=str(path),
        output_path="",
    )
    try:
        raw = pd.read_csv(path)
    except Exception as exc:
        report.errors.append(str(exc))
        return pd.DataFrame(columns=list(NORMALIZED_COLUMNS)), report

    report.rows_read = len(raw)
    if raw.empty:
        report.errors.append("empty file")
        return pd.DataFrame(columns=list(NORMALIZED_COLUMNS)), report

    normalized = normalize_frame(raw, symbol=symbol, default_spread=default_spread)
    deduped, dup_count = deduplicate_bars(normalized)
    report.duplicates_removed = dup_count
    if fill_gaps:
        deduped, filled = fill_missing_sessions(deduped)
        report.missing_filled = filled

    report.rows_written = len(deduped)
    return deduped, report


def normalized_to_m1_candles(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert normalized import to backtest M1 candle format."""
    if frame.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume", "spread"])
    out = pd.DataFrame(
        {
            "time": pd.to_datetime(frame["timestamp"], utc=True),
            "open": frame["open"],
            "high": frame["high"],
            "low": frame["low"],
            "close": frame["close"],
            "tick_volume": frame["volume"],
            "spread": frame["spread"],
        }
    )
    return out.sort_values("time").reset_index(drop=True)
