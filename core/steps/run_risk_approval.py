"""Step 10: Run risk approval."""

from __future__ import annotations

from loguru import logger

from core.models import SymbolCycleState
from core.runtime import KraitosRuntime
from execution.entry_engine import EntryEngine


def run_risk_approval(runtime: KraitosRuntime, state: SymbolCycleState) -> bool:
    """Record risk approval from the entry engine without re-evaluating risk."""
    if state.entry is None or state.entry.action not in {"enter_buy", "enter_sell"}:
        state.risk_approved = False
        state.risk_reason = state.skip_reason or "No actionable entry"
        return False

    risk_check = next(
        (check for check in state.entry.confirmations if check.name == "risk"),
        None,
    )
    if risk_check is None or not risk_check.passed:
        reason = risk_check.detail if risk_check else "Risk confirmation missing"
        state.risk_approved = False
        state.risk_lot_size = 0.0
        state.risk_reason = reason
        state.skip_reason = reason
        runtime.event_logger.risk_rejection(
            f"Risk rejected for {state.symbol}: {reason}",
            symbol=state.symbol,
            trace_id=state.trace_id,
            reason=reason,
        )
        logger.info(f"{state.symbol} risk rejected: {reason}")
        return False

    lot_size = state.entry.lot_size
    if lot_size <= 0 and risk_check.detail:
        lot_size = EntryEngine._extract_lot_size(risk_check.detail)

    state.risk_approved = True
    state.risk_lot_size = lot_size
    state.risk_reason = risk_check.detail

    runtime.event_logger.risk_approval(
        f"Risk approved for {state.symbol} with {lot_size:.2f} lots",
        symbol=state.symbol,
        trace_id=state.trace_id,
        lot_size=lot_size,
        data={"reason": risk_check.detail},
    )
    logger.info(f"{state.symbol} risk approved lot_size={lot_size:.2f}")
    return True
