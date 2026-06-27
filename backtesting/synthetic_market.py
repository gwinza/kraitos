"""Generate synthetic multi-timeframe candles with tradable structure."""

from __future__ import annotations

import math

import pandas as pd

from backtesting.candle_resampler import build_multitimeframe_candles


def generate_trending_m1(
    *,
    bars: int = 10_000,
    start_price: float = 1.1000,
    start: str = "2025-01-06 08:00:00",
    wave_amplitude: float = 0.0015,
    trend_slope: float = 0.000003,
    noise: float = 0.00005,
) -> pd.DataFrame:
    """
    Build M1 candles with oscillating structure suitable for swing detection.

    Uses UTC session hours (08:00-20:00) so backtest session checks pass.
    """
    times = pd.date_range(start, periods=bars, freq="min", tz="UTC")
    rows = []
    bar_index = 0
    for moment in times:
        if moment.weekday() >= 5:
            continue

        cycle = math.sin(bar_index / 18.0) + 0.5 * math.sin(bar_index / 7.0)
        impulse = 0.0
        if bar_index % 24 == 0:
            impulse = wave_amplitude * 0.45
        elif bar_index % 37 == 0:
            impulse = -wave_amplitude * 0.35

        close = start_price + bar_index * trend_slope + cycle * wave_amplitude + impulse
        jitter = ((bar_index % 5) - 2) * noise
        close += jitter
        high = close + abs(wave_amplitude) * 0.35 + noise
        low = close - abs(wave_amplitude) * 0.35 - noise
        open_price = close - noise * 0.5

        rows.append(
            {
                "time": moment,
                "open": round(open_price, 5),
                "high": round(high, 5),
                "low": round(low, 5),
                "close": round(close, 5),
                "tick_volume": 900 + (bar_index % 200),
                "spread": 1.0,
            }
        )
        bar_index += 1

    return pd.DataFrame(rows)


def generate_symbol_universe(
    symbols: tuple[str, ...] = ("EURUSD", "GBPUSD", "USDJPY"),
    *,
    bars: int = 10_000,
) -> dict[str, dict[str, pd.DataFrame]]:
    """Create resampled candles for multiple symbols."""
    start_prices = {
        "EURUSD": 1.1000,
        "GBPUSD": 1.2700,
        "USDJPY": 145.50,
    }
    result: dict[str, dict[str, pd.DataFrame]] = {}
    for offset, symbol in enumerate(symbols):
        m1 = generate_trending_m1(
            bars=bars,
            start_price=start_prices.get(symbol, 1.1000 + offset * 0.01),
            trend_slope=0.000002 + offset * 0.0000005,
            wave_amplitude=0.0012 + offset * 0.0002,
        )
        result[symbol] = build_multitimeframe_candles(m1)
    return result
