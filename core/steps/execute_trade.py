"""Step 11: Execute paper trade or live trade."""

from __future__ import annotations

from loguru import logger

from broker.exceptions import LiveTradingDisabledError, MT5OrderError
from core.helpers import compute_stop_loss, compute_take_profit, pip_size_for_symbol
from core.models import SymbolCycleState
from core.runtime import KraitosRuntime


def _execution_slippage_pips(runtime: KraitosRuntime) -> float:
    execution_raw = runtime.config.raw.get("execution", {})
    return float(execution_raw.get("slippage_pips", 1.0))


def execute_trade(runtime: KraitosRuntime, state: SymbolCycleState) -> bool:
    """Open a paper trade or place a gated live MT5 market order."""
    if state.entry is None or state.entry.action not in {"enter_buy", "enter_sell"}:
        return False
    if not state.risk_approved or state.risk_lot_size <= 0:
        return False
    if state.structure is None or state.harvest is None:
        raise ValueError(f"{state.symbol}: structure and harvest required for execution")

    side = "buy" if state.entry.action == "enter_buy" else "sell"
    entry_price = state.ask if side == "buy" else state.bid
    pip_size = pip_size_for_symbol(state.symbol)
    stop_loss = compute_stop_loss(
        side=side,
        entry_price=entry_price,
        structure=state.structure,
        pip_size=pip_size,
    )
    take_profit = compute_take_profit(
        side=side,
        entry_price=entry_price,
        pip_size=pip_size,
        harvest=state.harvest,
        micro_scalp=state.micro_scalp,
    )
    lot_size = state.risk_lot_size

    if runtime.config.trading.live_enabled:
        try:
            runtime.connector.require_live_trading()
        except LiveTradingDisabledError as exc:
            runtime.event_logger.error(
                f"Live trading blocked for {state.symbol}",
                trace_id=state.trace_id,
                symbol=state.symbol,
                exc=exc,
            )
            state.skip_reason = str(exc)
            return False

        try:
            result = runtime.connector.place_market_order(
                symbol=state.symbol,
                side=side,  # type: ignore[arg-type]
                volume=lot_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
                comment=f"kraitos {state.trace_id[:8]}",
                deviation_pips=_execution_slippage_pips(runtime),
            )
        except MT5OrderError as exc:
            runtime.event_logger.error(
                f"Live order failed for {state.symbol}",
                trace_id=state.trace_id,
                symbol=state.symbol,
                exc=exc,
            )
            state.skip_reason = str(exc)
            logger.warning(f"Live order failed for {state.symbol}: {exc}")
            return False

        runtime.event_logger.trade_decision(
            f"Live {side} {state.symbol} {result.volume:.2f} lots @ {result.entry_price:.5f}",
            symbol=state.symbol,
            trace_id=state.trace_id,
            action="live_open",
            data={
                "ticket": result.ticket,
                "side": side,
                "volume": result.volume,
                "entry_price": result.entry_price,
                "stop_loss": result.stop_loss,
                "take_profit": result.take_profit,
            },
        )
        state.executed = True
        state.execution_mode = "live"
        state.live_ticket = result.ticket
        logger.info(
            f"Executed live {side} {state.symbol} {result.volume:.2f} lots "
            f"(ticket={result.ticket})"
        )
        return True

    if not runtime.config.trading.paper_enabled:
        state.skip_reason = "Neither paper nor live trading is enabled"
        return False

    trade = runtime.paper_trader.open_trade(
        symbol=state.symbol,
        side=side,  # type: ignore[arg-type]
        entry_price=entry_price,
        lot_size=lot_size,
        stop_loss=stop_loss,
        take_profit=take_profit,
        reason=state.entry.explanation,
        trace_id=state.trace_id,
    )
    state.executed = True
    state.execution_mode = "paper"
    logger.info(
        f"Executed paper {side} {state.symbol} {lot_size:.2f} lots "
        f"(trade_id={trade.trade_id})"
    )
    return True
