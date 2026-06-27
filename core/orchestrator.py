"""Kraitos system orchestrator."""

from __future__ import annotations

import time
from typing import Iterable

from loguru import logger

from broker.exceptions import MT5ConnectionError, MT5DataError
from core.helpers import resolve_spread_limit, spread_price_to_pips
from core.models import CycleSummary, SymbolCycleState
from core.runtime import KraitosRuntime
from core.steps.analyse_structure import analyse_structure
from core.steps.check_harvest import check_harvest
from core.steps.check_micro_scalp import check_micro_scalp
from core.steps.confirm_entry import confirm_entry
from core.steps.connect_mt5 import connect_mt5
from core.steps.detect_regime import detect_regime
from core.steps.determine_bias import determine_bias
from core.steps.execute_trade import execute_trade
from core.steps.fetch_market_data import fetch_market_data
from core.steps.log_cycle import log_cycle
from core.steps.manage_exits import manage_exits
from core.steps.run_risk_approval import run_risk_approval
from core.steps.update_analytics import update_analytics
from data.market_data import MarketDataBundle


class KraitosOrchestrator:
    """Coordinate the full Kraitos trading pipeline."""

    def __init__(self, runtime: KraitosRuntime) -> None:
        self.runtime = runtime

    def run(
        self,
        *,
        cycles: int = 1,
        interval_seconds: float = 60.0,
        symbols: Iterable[str] | None = None,
    ) -> int:
        """
        Run one or more orchestration cycles.

        Returns:
            Process exit code (0 success, 1 failure).
        """
        cycle_trace = self.runtime.event_logger.new_trace_id()
        try:
            connect_mt5(self.runtime, trace_id=cycle_trace)
            for index in range(cycles):
                trace_id = self.runtime.event_logger.new_trace_id()
                logger.info(f"Starting orchestration cycle {index + 1}/{cycles}")
                self._run_cycle(trace_id=trace_id, symbols=symbols)
                if index < cycles - 1:
                    time.sleep(interval_seconds)
            return 0
        except MT5ConnectionError:
            return 1
        finally:
            self.runtime.connector.disconnect()

    def _run_cycle(
        self,
        *,
        trace_id: str,
        symbols: Iterable[str] | None = None,
    ) -> CycleSummary:
        """Execute a single end-to-end orchestration cycle."""
        bundle = fetch_market_data(self.runtime, trace_id=trace_id)
        target_symbols = tuple(symbols) if symbols is not None else self.runtime.config.trading.symbols
        states = self._process_symbols(bundle, target_symbols, trace_id=trace_id)

        exits_processed = manage_exits(self.runtime, trace_id=trace_id)

        entries_attempted = sum(
            1
            for state in states
            if state.entry is not None and state.entry.action in {"enter_buy", "enter_sell"}
        )
        trades_executed = sum(1 for state in states if state.executed)
        skipped = tuple(state.symbol for state in states if state.skip_reason)

        summary = CycleSummary(
            symbols_processed=len(states),
            entries_attempted=entries_attempted,
            trades_executed=trades_executed,
            exits_processed=exits_processed,
            skipped_symbols=skipped,
        )
        log_cycle(self.runtime, trace_id=trace_id, states=states, summary=summary)
        update_analytics(self.runtime, trace_id=trace_id, states=states)
        return summary

    def _process_symbols(
        self,
        bundle: MarketDataBundle,
        symbols: tuple[str, ...],
        *,
        trace_id: str,
    ) -> list[SymbolCycleState]:
        """Run symbol-level analysis and execution steps."""
        states: list[SymbolCycleState] = []

        for symbol in symbols:
            symbol_trace = self.runtime.event_logger.new_trace_id()
            state = SymbolCycleState(symbol=symbol, trace_id=symbol_trace)
            try:
                state.candles = {
                    timeframe: bundle.get(symbol, timeframe)
                    for timeframe in bundle.timeframes(symbol)
                }
                quote = self.runtime.connector.get_quote(symbol)
                state.bid = quote.bid
                state.ask = quote.ask
                state.spread_pips = spread_price_to_pips(quote.spread, symbol)
                state.spread_limit = resolve_spread_limit(self.runtime.config, symbol)

                detect_regime(self.runtime, state)
                determine_bias(self.runtime, state)
                analyse_structure(self.runtime, state)
                check_harvest(self.runtime, state)

                if state.harvest is not None and not state.harvest.allowed:
                    state.skip_reason = state.harvest.reason
                    states.append(state)
                    continue

                check_micro_scalp(self.runtime, state)
                confirm_entry(self.runtime, state)
                run_risk_approval(self.runtime, state)
                execute_trade(self.runtime, state)
            except (MT5DataError, ValueError, KeyError) as exc:
                state.skip_reason = str(exc)
                self.runtime.event_logger.error(
                    f"Symbol pipeline failed for {symbol}",
                    trace_id=symbol_trace,
                    symbol=symbol,
                    exc=exc,
                )
                logger.exception(f"Symbol pipeline failed for {symbol}")
            states.append(state)

        return states
