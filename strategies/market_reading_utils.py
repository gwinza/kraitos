"""Shared candle analysis helpers for market reading engines."""

from __future__ import annotations

import pandas as pd

REQUIRED_OHLCV = ("open", "high", "low", "close", "tick_volume", "spread")


def validate_candles(candles: pd.DataFrame, *, min_candles: int, engine: str) -> pd.DataFrame:
    if candles is None or candles.empty:
        raise ValueError(f"{engine}: candle data is empty")
    missing = [col for col in ("open", "high", "low", "close") if col not in candles.columns]
    if missing:
        raise ValueError(f"{engine}: missing columns {', '.join(missing)}")
    frame = candles.copy()
    if "time" in frame.columns:
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frame = frame.sort_values("time")
    frame = frame.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    if len(frame) < min_candles:
        raise ValueError(f"{engine}: need at least {min_candles} candles")
    return frame


def atr_series(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=3).mean().bfill()


def swing_points(
    frame: pd.DataFrame,
    *,
    window: int = 2,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for index in range(window, len(frame) - window):
        high = float(frame["high"].iloc[index])
        low = float(frame["low"].iloc[index])
        high_slice = frame["high"].iloc[index - window : index + window + 1]
        low_slice = frame["low"].iloc[index - window : index + window + 1]
        if high >= float(high_slice.max()):
            highs.append((index, high))
        if low <= float(low_slice.min()):
            lows.append((index, low))
    return highs, lows


def volume_participation(frame: pd.DataFrame) -> float:
    if "tick_volume" not in frame.columns:
        return 0.5
    volume = frame["tick_volume"].astype(float)
    if len(volume) < 20:
        return 0.5
    recent = float(volume.tail(10).mean())
    baseline = float(volume.iloc[-40:-10].mean()) if len(volume) >= 40 else float(volume.mean())
    if baseline <= 0:
        return 0.5
    ratio = recent / baseline
    return max(0.0, min(1.0, (ratio - 0.6) / 0.8))


def trend_direction_from_swings(
    highs: list[tuple[int, float]],
    lows: list[tuple[int, float]],
    frame: pd.DataFrame,
    atr_value: float,
) -> str:
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1][1] > highs[-2][1] and lows[-1][1] > lows[-2][1]:
            return "bullish"
        if highs[-1][1] < highs[-2][1] and lows[-1][1] < lows[-2][1]:
            return "bearish"
    slope = (float(frame["close"].iloc[-1]) - float(frame["close"].iloc[-20])) / max(atr_value, 1e-9)
    if slope > 1.0:
        return "bullish"
    if slope < -1.0:
        return "bearish"
    return "neutral"
