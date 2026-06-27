"""Step 12: Manage exits for open positions — adaptive exit engine first."""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from broker.exceptions import MT5OrderError
from core.expectancy_learning import get_expectancy_learning
from core.runtime import KraitosRuntime
from execution.models import ExitContext, ExitDecision, OpenTrade


@dataclass
class _LiveExitState:
    bars_since_entry: int = 0
    best_price: float = 0.0


_live_exit_state: dict[str, _LiveExitState] = {}


def _execution_slippage_pips(runtime: KraitosRuntime) -> float:
    execution_raw = runtime.config.raw.get("execution", {})
    return float(execution_raw.get("slippage_pips", 1.0))


def _live_state_key(symbol: str, ticket: int) -> str:
    return f"{symbol}:{ticket}"


def _update_live_state(
    *,
    key: str,
    side: str,
    entry_price: float,
    current_price: float,
) -> _LiveExitState:
    state = _live_exit_state.get(key)
    if state is None:
        state = _LiveExitState(bars_since_entry=0, best_price=entry_price)
        _live_exit_state[key] = state
    state.bars_since_entry += 1
    if side == "buy":
        state.best_price = max(state.best_price, current_price)
    else:
        state.best_price = min(state.best_price, current_price)
    return state


def _notify_trade_closed(
    runtime: KraitosRuntime,
    *,
    trade_id: str,
    exit_action: str,
) -> None:
    """Steps 6–7: personality memory and trade review after full close."""
    snapshot = runtime.paper_trader.snapshot()
    closed = next(
        (t for t in snapshot.trade_history if t.trade_id == trade_id and t.status == "closed"),
        None,
    )
    if closed is None:
        return
    learning = get_expectancy_learning(runtime)
    learning.on_trade_closed(closed, exit_action=exit_action)


def _evaluate_exit(
    runtime: KraitosRuntime,
    *,
    trade: OpenTrade,
    trade_id: str,
    trace_id: str,
) -> tuple[ExitDecision, float]:
    quote = runtime.connector.get_quote(trade.symbol)
    current_price = quote.bid if trade.side == "sell" else quote.ask
    candles = runtime.market_data.fetch_candles(trade.symbol, "M5")
    structure = runtime.structure_analyzer.analyze(
        runtime.market_data.fetch_candles(trade.symbol, "H1"),
        symbol=trade.symbol,
        timeframe="H1",
    )

    learning = get_expectancy_learning(runtime)
    decision = learning.evaluate_adaptive_exit(
        trade=trade,
        current_price=current_price,
        candles=candles,
        structure=structure,
        structure_analyzer=runtime.structure_analyzer,
        symbol=trade.symbol,
    )
    if decision.action == "hold_trade":
        legacy = runtime.exit_engine.evaluate(
            ExitContext(
                trade=trade,
                current_price=current_price,
                candles=candles,
                structure=structure,
            )
        )
        decision = legacy

    runtime.event_logger.trade_decision(
        f"{trade.symbol} exit: {decision.action} — {decision.reason}",
        symbol=trade.symbol,
        trace_id=trace_id,
        action=decision.action,
        data={
            "trade_id": trade_id,
            "reason": decision.reason,
            "current_price": current_price,
        },
    )
    return decision, current_price


def _apply_paper_exit(
    runtime: KraitosRuntime,
    *,
    trade_id: str,
    decision: ExitDecision,
    current_price: float,
    trace_id: str,
) -> bool:
    action = decision.action
    if action == "cut_loss":
        runtime.paper_trader.close_trade(
            trade_id,
            current_price,
            reason=decision.reason,
            trace_id=trace_id,
        )
        _notify_trade_closed(runtime, trade_id=trade_id, exit_action=action)
        return True
    if action == "take_profit":
        runtime.paper_trader.close_trade(
            trade_id,
            current_price,
            reason=decision.reason,
            trace_id=trace_id,
        )
        _notify_trade_closed(runtime, trade_id=trade_id, exit_action=action)
        return True
    if action == "close_early":
        runtime.paper_trader.close_trade(
            trade_id,
            current_price,
            reason=decision.reason,
            trace_id=trace_id,
        )
        _notify_trade_closed(runtime, trade_id=trade_id, exit_action=action)
        return True
    if action == "scale_out" and decision.scale_fraction:
        runtime.paper_trader.scale_out(
            trade_id,
            current_price,
            decision.scale_fraction,
            reason=decision.reason,
            trace_id=trace_id,
        )
        return True
    if action == "trail_stop" and decision.new_stop_loss is not None:
        runtime.paper_trader.update_stop_loss(
            trade_id,
            decision.new_stop_loss,
            reason=decision.reason,
        )
        return True
    return False


def _apply_live_exit(
    runtime: KraitosRuntime,
    *,
    ticket: int,
    trade: OpenTrade,
    decision: ExitDecision,
    trace_id: str,
) -> bool:
    slippage = _execution_slippage_pips(runtime)
    action = decision.action
    try:
        if action in {"cut_loss", "take_profit", "close_early"}:
            runtime.connector.close_position(
                ticket,
                deviation_pips=slippage,
                comment=f"kraitos {action}",
            )
            return True
        if action == "scale_out" and decision.scale_fraction:
            close_volume = trade.volume * decision.scale_fraction
            runtime.connector.close_position(
                ticket,
                volume=close_volume,
                deviation_pips=slippage,
                comment="kraitos scale_out",
            )
            return True
        if action == "trail_stop" and decision.new_stop_loss is not None:
            runtime.connector.modify_position(
                ticket,
                stop_loss=decision.new_stop_loss,
            )
            return True
    except MT5OrderError as exc:
        runtime.event_logger.error(
            f"Live exit failed for {trade.symbol}",
            trace_id=trace_id,
            symbol=trade.symbol,
            exc=exc,
        )
        logger.warning(f"Live exit failed for {trade.symbol} ticket={ticket}: {exc}")
    return False


def manage_exits(runtime: KraitosRuntime, *, trace_id: str) -> int:
    """Evaluate and apply exit actions for open paper or live positions."""
    processed = 0

    if runtime.config.trading.live_enabled and runtime.connector.is_connected:
        for position in runtime.connector.get_open_positions():
            try:
                quote = runtime.connector.get_quote(position.symbol)
                current_price = quote.bid if position.side == "sell" else quote.ask
                state_key = _live_state_key(position.symbol, position.ticket)
                live_state = _update_live_state(
                    key=state_key,
                    side=position.side,
                    entry_price=position.entry_price,
                    current_price=current_price,
                )
                open_trade = OpenTrade(
                    symbol=position.symbol,
                    side=position.side,
                    entry_price=position.entry_price,
                    stop_loss=position.stop_loss,
                    volume=position.volume,
                    take_profit=position.take_profit or None,
                    bars_since_entry=live_state.bars_since_entry,
                    best_price=live_state.best_price,
                )
                decision, _ = _evaluate_exit(
                    runtime,
                    trade=open_trade,
                    trade_id=str(position.ticket),
                    trace_id=trace_id,
                )
                if _apply_live_exit(
                    runtime,
                    ticket=position.ticket,
                    trade=open_trade,
                    decision=decision,
                    trace_id=trace_id,
                ):
                    _live_exit_state.pop(state_key, None)
                    processed += 1
                else:
                    logger.debug(
                        f"{position.symbol} hold live position ticket={position.ticket}"
                    )
            except Exception as exc:
                runtime.event_logger.error(
                    f"Exit management failed for {position.symbol}",
                    trace_id=trace_id,
                    symbol=position.symbol,
                    exc=exc,
                )
                logger.exception(f"Exit management failed for {position.symbol}")
        if processed:
            logger.info(f"Processed {processed} live exit action(s)")
        return processed

    snapshot = runtime.paper_trader.snapshot()
    for trade in snapshot.open_trades:
        try:
            quote = runtime.connector.get_quote(trade.symbol)
            current_price = quote.bid if trade.side == "sell" else quote.ask
            runtime.paper_trader.record_exit_tick(trade.trade_id, current_price)
            refreshed = runtime.paper_trader.snapshot()
            paper_trade = next(
                t for t in refreshed.open_trades if t.trade_id == trade.trade_id
            )
            open_trade = OpenTrade(
                symbol=paper_trade.symbol,
                side=paper_trade.side,
                entry_price=paper_trade.entry_price,
                stop_loss=paper_trade.stop_loss,
                volume=paper_trade.lot_size,
                take_profit=paper_trade.take_profit,
                bars_since_entry=paper_trade.bars_since_entry,
                best_price=(
                    paper_trade.best_price
                    if paper_trade.best_price > 0
                    else paper_trade.entry_price
                ),
                partial_taken=paper_trade.partial_taken,
                invalidation_level=paper_trade.invalidation_level,
            )
            decision, current_price = _evaluate_exit(
                runtime,
                trade=open_trade,
                trade_id=trade.trade_id,
                trace_id=trace_id,
            )
            if _apply_paper_exit(
                runtime,
                trade_id=paper_trade.trade_id,
                decision=decision,
                current_price=current_price,
                trace_id=trace_id,
            ):
                processed += 1
            else:
                logger.debug(f"{trade.symbol} hold open trade {trade.trade_id}")
        except Exception as exc:
            runtime.event_logger.error(
                f"Exit management failed for {trade.symbol}",
                trace_id=trace_id,
                symbol=trade.symbol,
                exc=exc,
            )
            logger.exception(f"Exit management failed for {trade.symbol}")

    if processed:
        logger.info(f"Processed {processed} exit action(s)")
    return processed
