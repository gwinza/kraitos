"""
Market data fetching and preparation for Kraitos.

Fetches OHLCV candles from MetaTrader 5, cleans missing values, and returns
structured pandas DataFrames keyed by symbol and timeframe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import pandas as pd
from loguru import logger

from broker import MT5Connector
from broker.exceptions import MT5DataError
from data.exceptions import MarketDataError

SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("M1", "M5", "M15", "M30", "H1", "H4", "H8")
NATIVE_TIMEFRAMES: frozenset[str] = frozenset({"M1", "M5", "M15", "M30", "H1", "H4"})
DERIVED_TIMEFRAMES: dict[str, str] = {"H8": "H1"}

CANDLE_COLUMNS: tuple[str, ...] = (
    "time",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
)

H8_RESAMPLE_RULE = "8h"
H8_SOURCE_MULTIPLIER = 8


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(CANDLE_COLUMNS))


def prepare_candles(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize and clean a raw candle DataFrame.

    - Keeps only required columns
    - Drops rows with missing or invalid OHLC values
    - Removes duplicate timestamps
    - Sorts chronologically
    """
    if raw is None or raw.empty:
        logger.debug("Received empty candle data; returning empty frame")
        return _empty_frame()

    frame = raw.copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True)

    for column in ("tick_volume", "spread"):
        if column not in frame.columns:
            frame[column] = 0

    missing_columns = [column for column in CANDLE_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise MarketDataError(f"Missing required candle columns: {', '.join(missing_columns)}")

    frame = frame.loc[:, list(CANDLE_COLUMNS)]
    initial_rows = len(frame)

    frame = frame.dropna(subset=["open", "high", "low", "close", "time"])
    frame = frame[
        (frame["open"] > 0)
        & (frame["high"] > 0)
        & (frame["low"] > 0)
        & (frame["close"] > 0)
    ]
    frame = frame.drop_duplicates(subset=["time"], keep="last")
    frame = frame.sort_values("time")

    frame["tick_volume"] = (
        pd.to_numeric(frame["tick_volume"], errors="coerce").fillna(0).astype(int)
    )
    frame["spread"] = pd.to_numeric(frame["spread"], errors="coerce").fillna(0.0)

    frame = frame.reset_index(drop=True)
    removed = initial_rows - len(frame)
    if removed:
        logger.debug(f"Cleaned {removed} invalid or duplicate candle row(s)")

    return frame


def _normalize_timeframe(timeframe: str) -> str:
    normalized = timeframe.strip().upper()
    if normalized not in SUPPORTED_TIMEFRAMES:
        allowed = ", ".join(SUPPORTED_TIMEFRAMES)
        raise MarketDataError(f"Unsupported timeframe '{timeframe}'. Allowed: {allowed}")
    return normalized


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise MarketDataError("Symbol must be a non-empty string")
    return normalized


def _build_h8_from_h1(h1_frame: pd.DataFrame, count: int) -> pd.DataFrame:
    """Aggregate H1 candles into H8 bars."""
    cleaned = prepare_candles(h1_frame)
    if cleaned.empty:
        return _empty_frame()

    indexed = cleaned.set_index("time").sort_index()
    resampled = (
        indexed.resample(H8_RESAMPLE_RULE, label="left", closed="left")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "tick_volume": "sum",
                "spread": "mean",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
    )

    if resampled.empty:
        return _empty_frame()

    trimmed = resampled.tail(count).reset_index()
    return prepare_candles(trimmed)


@dataclass
class MarketDataBundle:
    """Structured candle data keyed by symbol and timeframe."""

    data: dict[str, dict[str, pd.DataFrame]] = field(default_factory=dict)

    def get(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Return candles for a symbol/timeframe pair."""
        symbol_key = _normalize_symbol(symbol)
        timeframe_key = _normalize_timeframe(timeframe)
        try:
            return self.data[symbol_key][timeframe_key]
        except KeyError as exc:
            raise MarketDataError(
                f"No market data for {symbol_key} {timeframe_key}"
            ) from exc

    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.data))

    def timeframes(self, symbol: str) -> tuple[str, ...]:
        symbol_key = _normalize_symbol(symbol)
        if symbol_key not in self.data:
            raise MarketDataError(f"No market data for symbol: {symbol_key}")
        return tuple(sorted(self.data[symbol_key]))


class MarketDataService:
    """Fetch and prepare multi-symbol, multi-timeframe candle data."""

    def __init__(
        self,
        connector: MT5Connector,
        *,
        default_count: int = 500,
    ) -> None:
        if default_count <= 0:
            raise MarketDataError("default_count must be a positive integer")
        self._connector = connector
        self._default_count = default_count

    def fetch(
        self,
        symbols: Iterable[str],
        timeframes: Iterable[str] | None = None,
        *,
        count: int | None = None,
    ) -> MarketDataBundle:
        """
        Fetch and prepare candles for multiple symbols and timeframes.

        Returns:
            MarketDataBundle mapping symbol -> timeframe -> DataFrame.
        """
        symbol_list = [_normalize_symbol(symbol) for symbol in symbols]
        if not symbol_list:
            raise MarketDataError("At least one symbol is required")

        timeframe_list = (
            [_normalize_timeframe(tf) for tf in timeframes]
            if timeframes is not None
            else list(SUPPORTED_TIMEFRAMES)
        )
        bar_count = count if count is not None else self._default_count
        if bar_count <= 0:
            raise MarketDataError("count must be a positive integer")

        bundle: dict[str, dict[str, pd.DataFrame]] = {}

        for symbol in symbol_list:
            bundle[symbol] = {}
            for timeframe in timeframe_list:
                frame = self.fetch_candles(symbol, timeframe, count=bar_count)
                bundle[symbol][timeframe] = frame
                logger.info(
                    f"Prepared {len(frame)} candle(s) for {symbol} {timeframe}"
                )

        return MarketDataBundle(data=bundle)

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        count: int | None = None,
    ) -> pd.DataFrame:
        """Fetch and prepare candles for a single symbol and timeframe."""
        symbol_key = _normalize_symbol(symbol)
        timeframe_key = _normalize_timeframe(timeframe)
        bar_count = count if count is not None else self._default_count

        try:
            if timeframe_key in NATIVE_TIMEFRAMES:
                raw = self._connector.get_candles(symbol_key, timeframe_key, count=bar_count)
                return prepare_candles(raw)

            source_timeframe = DERIVED_TIMEFRAMES[timeframe_key]
            source_count = bar_count * H8_SOURCE_MULTIPLIER
            logger.debug(
                f"Building {timeframe_key} from {source_count} {source_timeframe} bar(s) "
                f"for {symbol_key}"
            )
            source_raw = self._connector.get_candles(
                symbol_key,
                source_timeframe,
                count=source_count,
            )
            return _build_h8_from_h1(source_raw, bar_count)
        except MT5DataError as exc:
            raise MarketDataError(str(exc)) from exc
