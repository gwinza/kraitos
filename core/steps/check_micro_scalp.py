"""Step 8: Check micro-scalp opportunity."""

from __future__ import annotations

from loguru import logger

from core.models import SymbolCycleState
from core.runtime import KraitosRuntime
from strategies.models import MicroScalpSignal


def check_micro_scalp(runtime: KraitosRuntime, state: SymbolCycleState) -> MicroScalpSignal:
    """Scan M1 and M5 for a micro-scalp entry signal."""
    m1 = state.candles["M1"]
    m5 = state.candles["M5"]
    result = runtime.micro_scalper.scan(
        m1,
        m5,
        spread_limit=state.spread_limit,
        current_spread=state.spread_pips,
    )
    state.micro_scalp = result

    runtime.event_logger.system_event(
        f"{state.symbol} micro-scalp: {result.action}",
        event_type="micro_scalp_checked",
        trace_id=state.trace_id,
        data={
            "symbol": state.symbol,
            "action": result.action,
            "reason": result.reason,
            "target_pips": result.target_pips,
        },
    )
    logger.info(f"{state.symbol} micro-scalp action={result.action} reason={result.reason}")
    return result
