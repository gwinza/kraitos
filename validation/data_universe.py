"""Walk-forward data universe: synthetic, imported CSV, or broker history."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Sequence

import pandas as pd

from backtesting.candle_resampler import build_multitimeframe_candles
from backtesting.synthetic_market import generate_trending_m1
DataSource = Literal["synthetic", "imported_csv", "broker_history"]

WALK_FORWARD_YEARS = (2022, 2023)

YEAR_REGIME_LABELS: dict[int, str] = {
    2022: "ranging",
    2023: "trending",
    2024: "volatile",
    2025: "trending",
    2026: "ranging",
}

WALK_FORWARD_SYMBOLS: tuple[str, ...] = (
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "NZDUSD",
    "USDCAD",
    "USDCHF",
    "EURGBP",
    "EURJPY",
    "GBPJPY",
    "XAUUSD",
)

SYMBOL_STARTS: dict[str, float] = {
    "EURUSD": 1.1000,
    "GBPUSD": 1.2700,
    "USDJPY": 145.50,
    "AUDUSD": 0.6700,
    "NZDUSD": 0.6100,
    "USDCAD": 1.3500,
    "USDCHF": 0.8800,
    "EURGBP": 0.8600,
    "EURJPY": 158.50,
    "GBPJPY": 184.00,
    "XAUUSD": 1950.00,
}

_BROKER_DIR = "broker_history"
_IMPORTED_DIR = "imported_csv"


def resolve_data_source(project_root: Path) -> DataSource:
    """Detect whether walk-forward data is synthetic or loaded from disk."""
    root = project_root.resolve()
    broker_dir = root / "data" / _BROKER_DIR
    imported_dir = root / "data" / _IMPORTED_DIR
    if broker_dir.is_dir() and any(broker_dir.rglob("*.csv")):
        return "broker_history"
    if imported_dir.is_dir() and any(imported_dir.rglob("*.csv")):
        return "imported_csv"
    return "synthetic"


def _csv_search_roots(project_root: Path, data_source: DataSource) -> list[Path]:
    root = project_root.resolve()
    if data_source == "broker_history":
        return [root / "data" / _BROKER_DIR]
    if data_source == "imported_csv":
        return [root / "data" / _IMPORTED_DIR]
    return []


def _load_symbol_m1_csv(path: Path) -> pd.DataFrame | None:
    frame = pd.read_csv(path)
    if frame.empty:
        return None
    time_col = "time" if "time" in frame.columns else frame.columns[0]
    frame = frame.rename(columns={time_col: "time"})
    required = {"time", "open", "high", "low", "close"}
    if not required.issubset(frame.columns):
        return None
    if "volume" not in frame.columns:
        frame["volume"] = 1000.0
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    return frame if not frame.empty else None


def _find_symbol_csv(project_root: Path, symbol: str, data_source: DataSource) -> Path | None:
    symbol_key = symbol.upper()
    for root in _csv_search_roots(project_root, data_source):
        candidates = sorted(root.rglob(f"{symbol_key}*.csv"))
        if candidates:
            return candidates[0]
    return None


def generate_synthetic_year_frames(
    *,
    years: Sequence[int],
    symbols: Sequence[str],
    m1_bars_per_year: int,
) -> dict[str, list[pd.DataFrame]]:
    """Build per-symbol M1 frames for each walk-forward year."""
    frames_by_symbol: dict[str, list[pd.DataFrame]] = {symbol: [] for symbol in symbols}
    for year in years:
        start = f"{year}-01-06 08:00:00"
        regime = YEAR_REGIME_LABELS.get(year, "trending")
        trend_scale = {
            "trending": 0.000003,
            "ranging": 0.0000004,
            "volatile": 0.0000015,
        }.get(regime, 0.000002)
        wave_scale = {
            "trending": 0.0012,
            "ranging": 0.0008,
            "volatile": 0.0020,
        }.get(regime, 0.0012)

        for offset, symbol in enumerate(symbols):
            m1 = generate_trending_m1(
                bars=m1_bars_per_year,
                start=start,
                start_price=SYMBOL_STARTS.get(symbol, 1.1000 + offset * 0.01),
                trend_slope=trend_scale * (1.0 + offset * 0.15),
                wave_amplitude=wave_scale * (1.0 + offset * 0.1),
            )
            frames_by_symbol[symbol].append(m1)
    return frames_by_symbol


def build_walk_forward_universe(
    project_root: Path,
    *,
    years: Sequence[int] = WALK_FORWARD_YEARS,
    symbols: Sequence[str] = WALK_FORWARD_SYMBOLS,
    m1_bars_per_year: int = 12_000,
    data_source: DataSource | None = None,
) -> tuple[dict[str, dict[str, pd.DataFrame]], DataSource]:
    """
    Build multi-timeframe candles for walk-forward validation.

    Uses broker/imported CSV when present for a symbol; otherwise synthetic M1.
    """
    source = data_source or resolve_data_source(project_root)
    universe: dict[str, dict[str, pd.DataFrame]] = {symbol: {} for symbol in symbols}
    synthetic_frames = generate_synthetic_year_frames(
        years=years,
        symbols=symbols,
        m1_bars_per_year=m1_bars_per_year,
    )

    for symbol in symbols:
        csv_path = _find_symbol_csv(project_root, symbol, source) if source != "synthetic" else None
        if csv_path is not None:
            loaded = _load_symbol_m1_csv(csv_path)
            if loaded is not None:
                universe[symbol] = build_multitimeframe_candles(loaded)
                continue

        combined = pd.concat(synthetic_frames[symbol], ignore_index=True)
        combined = combined.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)
        universe[symbol] = build_multitimeframe_candles(combined)

    effective_source: DataSource = source
    if source != "synthetic":
        any_csv = any(
            _find_symbol_csv(project_root, symbol, source) is not None for symbol in symbols
        )
        if not any_csv:
            effective_source = "synthetic"

    return universe, effective_source
