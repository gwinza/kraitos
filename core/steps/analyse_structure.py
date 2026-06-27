"""Step 6: Analyse market structure."""

from __future__ import annotations

from loguru import logger

from core.models import SymbolCycleState
from core.runtime import KraitosRuntime
from strategies.models import MarketContext


def analyse_structure(runtime: KraitosRuntime, state: SymbolCycleState) -> MarketContext:
    """Analyse swing structure, zones, and events on the structure timeframe."""
    h1 = state.candles["H1"]
    result = runtime.structure_analyzer.analyze(h1, symbol=state.symbol, timeframe="H1")
    state.structure = result

    runtime.event_logger.system_event(
        f"{state.symbol} structure trend: {result.trend}",
        event_type="structure_analysed",
        trace_id=state.trace_id,
        data={
            "symbol": state.symbol,
            "trend": result.trend,
            "higher_highs": result.higher_highs,
            "higher_lows": result.higher_lows,
            "lower_highs": result.lower_highs,
            "lower_lows": result.lower_lows,
            "swing_highs": len(result.swing_highs),
            "swing_lows": len(result.swing_lows),
        },
    )
    logger.info(f"{state.symbol} structure trend={result.trend}")
    return result
