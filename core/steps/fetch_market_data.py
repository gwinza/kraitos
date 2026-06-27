"""Step 3: Fetch market data."""

from __future__ import annotations

from loguru import logger

from core.helpers import resolve_timeframes
from core.runtime import KraitosRuntime
from data.market_data import MarketDataBundle


def fetch_market_data(runtime: KraitosRuntime, *, trace_id: str) -> MarketDataBundle:
    """Fetch multi-timeframe candles for all configured symbols."""
    symbols = runtime.config.trading.symbols
    timeframes = resolve_timeframes(runtime.config)
    bundle = runtime.market_data.fetch(symbols, timeframes)

    runtime.event_logger.system_event(
        f"Fetched market data for {len(symbols)} symbol(s)",
        event_type="market_data_fetched",
        trace_id=trace_id,
        data={
            "symbols": list(symbols),
            "timeframes": list(timeframes),
            "bars": {
                symbol: {
                    timeframe: len(bundle.get(symbol, timeframe))
                    for timeframe in timeframes
                }
                for symbol in symbols
            },
        },
    )
    logger.info(
        f"Market data ready for {len(symbols)} symbol(s) across {len(timeframes)} timeframe(s)"
    )
    return bundle
