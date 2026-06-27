"""Step 4: Detect market regime."""

from __future__ import annotations

from loguru import logger

from core.helpers import resolve_spread_limit
from core.models import SymbolCycleState
from core.runtime import KraitosRuntime
from strategies.models import RegimeResult


def detect_regime(runtime: KraitosRuntime, state: SymbolCycleState) -> RegimeResult:
    """Classify the current market regime for a symbol."""
    h1 = state.candles["H1"]
    spread_limit = resolve_spread_limit(runtime.config, state.symbol)
    result = runtime.regime_detector.detect(h1, spread_limit=spread_limit)
    state.regime = result

    runtime.event_logger.system_event(
        f"{state.symbol} regime: {result.regime} ({result.confidence:.2f})",
        event_type="regime_detected",
        trace_id=state.trace_id,
        data={
            "symbol": state.symbol,
            "regime": result.regime,
            "confidence": result.confidence,
            "reason": result.reason,
        },
    )
    logger.info(f"{state.symbol} regime={result.regime} confidence={result.confidence:.2f}")
    return result
