"""Step 9: Confirm entry."""

from __future__ import annotations

from loguru import logger

from core.helpers import compute_stop_loss, compute_take_profit, pip_size_for_symbol
from core.models import SymbolCycleState
from core.portfolio import build_portfolio_state
from core.runtime import KraitosRuntime
from execution.models import EntryContext, EntryDecision
from strategies.trend_quality_engine import TrendQualityEngine


def confirm_entry(runtime: KraitosRuntime, state: SymbolCycleState) -> EntryDecision:
    """Run the entry engine to confirm whether a trade should be opened."""
    if state.harvest is None or not state.harvest.allowed:
        decision = EntryDecision(
            action="reject",
            explanation=state.harvest.reason if state.harvest else "Harvest not evaluated",
            lot_size=0.0,
        )
        state.entry = decision
        state.skip_reason = decision.explanation
        return decision

    if not state.pair_allowed:
        decision = EntryDecision(
            action="reject",
            explanation=f"Pair blocked: {state.pair_reason}",
            lot_size=0.0,
        )
        state.entry = decision
        state.skip_reason = decision.explanation
        return decision

    if not state.news_allowed:
        decision = EntryDecision(
            action="reject",
            explanation=f"News filter blocked: {state.news_reason}",
            lot_size=0.0,
        )
        state.entry = decision
        state.skip_reason = decision.explanation
        return decision

    if (
        state.bias is None
        or state.structure is None
        or state.regime is None
        or state.micro_scalp is None
    ):
        raise ValueError(f"{state.symbol}: analysis prerequisites missing for entry")

    pip_size = pip_size_for_symbol(state.symbol)
    side = "buy" if state.bias.bias == "bullish" else "sell"
    entry_price = state.ask if side == "buy" else state.bid
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
    expected_target_pips = None
    if take_profit is not None and pip_size > 0:
        expected_target_pips = abs(take_profit - entry_price) / pip_size

    portfolio = build_portfolio_state(
        config=runtime.config,
        paper_trader=runtime.paper_trader,
        risk_manager=runtime.risk_manager,
        project_root=runtime.project_root,
        broker_balance=runtime.broker_balance,
        connector=runtime.connector,
    )
    trend_quality = None
    try:
        structure_tf = runtime.config.pipeline.structure_timeframe
        trend_quality = TrendQualityEngine().analyze(
            runtime.market_data.fetch_candles(state.symbol, structure_tf),
            symbol=state.symbol,
            timeframe=structure_tf,
        )
    except Exception as exc:
        logger.debug(f"{state.symbol} trend quality unavailable: {exc}")

    context = EntryContext(
        symbol=state.symbol,
        bias=state.bias,
        structure=state.structure,
        regime=state.regime,
        momentum=state.micro_scalp,
        current_spread=state.spread_pips,
        spread_limit=state.spread_limit,
        entry_price=entry_price,
        stop_loss=stop_loss,
        portfolio=portfolio,
        risk_manager=runtime.risk_manager,
        trace_id=state.trace_id,
        candles=runtime.market_data.fetch_candles(state.symbol, "M5"),
        trend_quality=trend_quality,
        expected_target_pips=expected_target_pips,
    )
    decision = runtime.entry_engine.evaluate(context)
    state.entry = decision

    if decision.action in {"reject", "wait"}:
        state.skip_reason = decision.explanation

    logger.info(f"{state.symbol} entry action={decision.action}")
    return decision
