"""Step 7: Check harvest mode."""

from __future__ import annotations

from loguru import logger

from core.helpers import is_in_trading_session, resolve_spread_limit
from core.models import SymbolCycleState
from core.pair_gating import pair_trading_allowed
from core.runtime import KraitosRuntime
from strategies.models import HarvestContext, HarvestDecision


def check_harvest(runtime: KraitosRuntime, state: SymbolCycleState) -> HarvestDecision:
    """Evaluate whether harvest mode permits trading on this symbol."""
    if state.regime is None or state.bias is None or state.structure is None:
        raise ValueError(f"{state.symbol}: regime, bias, and structure are required")

    pair_allowed, pair_reason = pair_trading_allowed(
        state.symbol,
        analyzer=runtime.pair_analyzer,
        output_path=runtime.project_root / "logs" / "pair_specialisation.json",
    )
    state.pair_allowed = pair_allowed
    state.pair_reason = pair_reason

    news_allowed = True
    news_reason = ""
    if runtime.config.trading.news_filter_enabled:
        news_result = runtime.news_filter.check_symbol(state.symbol)
        news_allowed = news_result.allowed
        news_reason = news_result.reason
    state.news_allowed = news_allowed
    state.news_reason = news_reason

    spread_limit = resolve_spread_limit(runtime.config, state.symbol)
    state.spread_limit = spread_limit

    context = HarvestContext(
        symbol=state.symbol,
        bias=state.bias,
        structure=state.structure,
        regime=state.regime,
        current_spread=state.spread_pips,
        spread_limit=spread_limit,
        in_active_session=is_in_trading_session(runtime.config),
        news_risk_active=not news_allowed,
    )
    result = runtime.harvest_engine.evaluate(context)
    state.harvest = result

    if not pair_allowed:
        result = HarvestDecision(
            mode="none",
            allowed=False,
            target_pips=0.0,
            reason=f"Pair blocked: {pair_reason}",
        )
        state.harvest = result

    runtime.event_logger.system_event(
        f"{state.symbol} harvest: {result.mode} allowed={result.allowed}",
        event_type="harvest_checked",
        trace_id=state.trace_id,
        data={
            "symbol": state.symbol,
            "mode": result.mode,
            "allowed": result.allowed,
            "target_pips": result.target_pips,
            "reason": result.reason,
            "pair_allowed": pair_allowed,
            "news_allowed": news_allowed,
        },
    )
    logger.info(
        f"{state.symbol} harvest mode={result.mode} allowed={result.allowed} "
        f"target={result.target_pips:.1f}p"
    )
    return result
