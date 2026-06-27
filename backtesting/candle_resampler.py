"""Build aligned multi-timeframe candle sets for backtesting."""

from __future__ import annotations

import pandas as pd

PIPELINE_TIMEFRAMES = ("M1", "M5", "M15", "H1", "H4", "H8")
RESAMPLE_RULES = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "H1": "1h",
    "H4": "4h",
    "H8": "8h",
}


def prepare_candles(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize OHLCV columns and sort by time."""
    required = ("time", "open", "high", "low", "close")
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Candle frame missing columns: {', '.join(missing)}")

    normalized = frame.copy()
    normalized["time"] = pd.to_datetime(normalized["time"], utc=True)
    normalized = normalized.dropna(subset=["open", "high", "low", "close"])
    normalized = normalized.sort_values("time").reset_index(drop=True)

    if "tick_volume" not in normalized.columns:
        normalized["tick_volume"] = 1000
    if "spread" not in normalized.columns:
        normalized["spread"] = 1.0
    return normalized


def build_multitimeframe_candles(base_frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Resample a base candle series (prefer M1) into all pipeline timeframes."""
    base = prepare_candles(base_frame)
    indexed = base.set_index("time")
    result: dict[str, pd.DataFrame] = {}

    for timeframe, rule in RESAMPLE_RULES.items():
        if timeframe == "M1":
            result[timeframe] = base
            continue
        resampled = indexed.resample(rule).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "tick_volume": "sum",
                "spread": "mean",
            }
        )
        resampled = resampled.dropna(subset=["open", "high", "low", "close"])
        result[timeframe] = resampled.reset_index()

    return result


def build_symbol_candles(
    candles_by_symbol: dict[str, dict[str, pd.DataFrame]],
) -> dict[str, dict[str, pd.DataFrame]]:
    """Ensure each symbol has properly resampled multi-timeframe candles."""
    normalized: dict[str, dict[str, pd.DataFrame]] = {}
    for symbol, timeframes in candles_by_symbol.items():
        if _has_distinct_timeframes(timeframes):
            normalized[symbol] = {
                tf: prepare_candles(timeframes[tf])
                for tf in PIPELINE_TIMEFRAMES
                if tf in timeframes and not timeframes[tf].empty
            }
            for tf in PIPELINE_TIMEFRAMES:
                if tf not in normalized[symbol]:
                    normalized[symbol][tf] = pd.DataFrame()
            continue

        base_tf = _select_base_timeframe(timeframes)
        base_frame = timeframes[base_tf]
        normalized[symbol] = build_multitimeframe_candles(base_frame)
    return normalized


def _has_distinct_timeframes(timeframes: dict[str, pd.DataFrame]) -> bool:
    lengths = {
        len(prepare_candles(frame))
        for tf, frame in timeframes.items()
        if tf in PIPELINE_TIMEFRAMES and frame is not None and not frame.empty
    }
    return len(lengths) >= 3 and len(lengths) > 1 and max(lengths) > min(lengths) * 1.5


def _select_base_timeframe(timeframes: dict[str, pd.DataFrame]) -> str:
    best_tf = "H1"
    best_len = 0
    priority = {"M1": 6, "M5": 5, "M15": 4, "H1": 3, "H4": 2, "H8": 1}
    for tf in PIPELINE_TIMEFRAMES:
        frame = timeframes.get(tf)
        if frame is None or frame.empty:
            continue
        length = len(frame)
        if length > best_len or (length == best_len and priority.get(tf, 0) > priority.get(best_tf, 0)):
            best_tf = tf
            best_len = length
    return best_tf
