"""Step 13: Log cycle outcomes."""

from __future__ import annotations

from loguru import logger

from core.models import CycleSummary, SymbolCycleState
from core.runtime import KraitosRuntime


def log_cycle(
    runtime: KraitosRuntime,
    *,
    trace_id: str,
    states: list[SymbolCycleState],
    summary: CycleSummary,
) -> None:
    """Persist a structured summary of the completed orchestration cycle."""
    symbol_payload = []
    for state in states:
        symbol_payload.append(
            {
                "symbol": state.symbol,
                "trace_id": state.trace_id,
                "regime": state.regime.regime if state.regime else None,
                "bias": state.bias.bias if state.bias else None,
                "harvest_mode": state.harvest.mode if state.harvest else None,
                "harvest_allowed": state.harvest.allowed if state.harvest else None,
                "micro_scalp": state.micro_scalp.action if state.micro_scalp else None,
                "entry_action": state.entry.action if state.entry else None,
                "risk_approved": state.risk_approved,
                "executed": state.executed,
                "execution_mode": state.execution_mode,
                "skip_reason": state.skip_reason,
            }
        )

    runtime.event_logger.system_event(
        "Orchestration cycle completed",
        event_type="cycle_completed",
        trace_id=trace_id,
        data={
            "symbols_processed": summary.symbols_processed,
            "entries_attempted": summary.entries_attempted,
            "trades_executed": summary.trades_executed,
            "exits_processed": summary.exits_processed,
            "skipped_symbols": list(summary.skipped_symbols),
            "symbols": symbol_payload,
        },
    )
    logger.info(
        "Cycle complete: "
        f"{summary.symbols_processed} symbols, "
        f"{summary.trades_executed} executed, "
        f"{summary.exits_processed} exits"
    )
