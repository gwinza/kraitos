"""Step 5: Determine multi-timeframe bias."""

from __future__ import annotations

from loguru import logger

from core.models import SymbolCycleState
from core.runtime import KraitosRuntime
from strategies.models import MultiTimeframeBiasResult


def determine_bias(runtime: KraitosRuntime, state: SymbolCycleState) -> MultiTimeframeBiasResult:
    """Evaluate directional bias across macro, structure, and precision layers."""
    candles_by_tf = {
        timeframe: state.candles[timeframe]
        for timeframe in ("H8", "H4", "H1", "M15", "M5", "M1")
        if timeframe in state.candles
    }
    result = runtime.bias_analyzer.evaluate(candles_by_tf)
    state.bias = result

    runtime.event_logger.system_event(
        f"{state.symbol} bias: {result.bias} ({result.confidence:.2f})",
        event_type="bias_determined",
        trace_id=state.trace_id,
        data={
            "symbol": state.symbol,
            "bias": result.bias,
            "confidence": result.confidence,
            "explanation": result.explanation,
        },
    )
    logger.info(f"{state.symbol} bias={result.bias} confidence={result.confidence:.2f}")
    return result
