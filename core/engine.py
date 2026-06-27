"""Kraitos integrated trading engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

from loguru import logger

from config.settings import KraitosConfig
from controls.trading_gate import TradingGate
from intelligence.opportunity_allocator import OpportunityAllocator
from core.helpers import resolve_timeframes, spread_price_to_pips
from core.pipeline import TradingPipeline
from core.risk_controller import RiskController
from core.signal_router import SignalRouter, TradeSignal
from core.trade_executor import TradeExecutor
from data.market_data import MarketDataBundle, MarketDataService
from logs.event_logger import KraitosEventLogger
from portfolio.portfolio_construction import PortfolioConstructionEngine


class KraitosEngine:
    """Coordinate market data, analysis, risk, routing, and simulated execution."""

    def __init__(
        self,
        *,
        project_root: Path,
        config: KraitosConfig,
        event_logger: KraitosEventLogger,
        runtime: object,
        trading_gate: TradingGate | None = None,
    ) -> None:
        self.project_root = project_root
        self.config = config
        self.event_logger = event_logger
        self._runtime = runtime
        self._trading_gate = trading_gate
        self._router = SignalRouter()
        self._executor = TradeExecutor(
            config=config,
            paper_trader=runtime.paper_trader,  # type: ignore[attr-defined]
            trading_gate=trading_gate,
        )
        opportunity_allocator = OpportunityAllocator(project_root)
        portfolio_engine = PortfolioConstructionEngine(project_root)
        risk_controller = RiskController(
            config=config,
            risk_manager=runtime.risk_manager,  # type: ignore[attr-defined]
            paper_trader=runtime.paper_trader,  # type: ignore[attr-defined]
            project_root=project_root,
            broker_balance=getattr(runtime, "broker_balance", None),
            connector=getattr(runtime, "connector", None),
            portfolio_engine=portfolio_engine,
        )
        self._pipeline = TradingPipeline(
            config=config,
            regime_detector=runtime.regime_detector,  # type: ignore[attr-defined]
            bias_analyzer=runtime.bias_analyzer,  # type: ignore[attr-defined]
            structure_analyzer=runtime.structure_analyzer,  # type: ignore[attr-defined]
            harvest_engine=runtime.harvest_engine,  # type: ignore[attr-defined]
            micro_scalper=runtime.micro_scalper,  # type: ignore[attr-defined]
            entry_engine=runtime.entry_engine,  # type: ignore[attr-defined]
            risk_controller=risk_controller,
            news_filter=runtime.news_filter,  # type: ignore[attr-defined]
            pair_analyzer=runtime.pair_analyzer,  # type: ignore[attr-defined]
            project_root=project_root,
            opportunity_allocator=opportunity_allocator,
            portfolio_engine=portfolio_engine,
        )
        self._market_data: MarketDataService = runtime.market_data  # type: ignore[attr-defined]
        self._connector = runtime.connector  # type: ignore[attr-defined]

    @classmethod
    def build(
        cls,
        *,
        project_root: Path,
        config: KraitosConfig,
        event_logger: KraitosEventLogger,
        trading_gate: TradingGate | None = None,
    ) -> KraitosEngine:
        """Construct an engine from project configuration."""
        from core.runtime import KraitosRuntime

        runtime = KraitosRuntime.build(
            project_root=project_root,
            config=config,
            event_logger=event_logger,
        )
        return cls(
            project_root=project_root,
            config=config,
            event_logger=event_logger,
            runtime=runtime,
            trading_gate=trading_gate,
        )

    def run(
        self,
        *,
        symbols: Sequence[str] | None = None,
        execute: bool | None = None,
        market_data: MarketDataBundle | None = None,
        connect_broker: bool = True,
    ) -> list[TradeSignal]:
        """
        Run the integrated pipeline for each symbol.

        Args:
            symbols: Symbols to evaluate (defaults to config).
            execute: Open paper trades for TRADE signals (defaults to config flag).
            market_data: Preloaded candles; skips broker fetch when provided.
            connect_broker: Connect to MT5 for quotes and optional data fetch.
        """
        should_execute = (
            self.config.pipeline.execute_trades if execute is None else execute
        )
        target_symbols = tuple(symbols) if symbols else self.config.trading.symbols
        trace_id = self.event_logger.new_trace_id()

        try:
            if connect_broker:
                self._connector.connect()
                account = self._connector.get_account_info()
                self._runtime.broker_balance = account.balance  # type: ignore[attr-defined]

            bundle = market_data or self._load_market_data(target_symbols, trace_id=trace_id)
            signals: list[TradeSignal] = []

            for symbol in target_symbols:
                symbol_signals = self._process_symbol(
                    symbol,
                    bundle=bundle,
                    trace_id=self.event_logger.new_trace_id(),
                    execute=should_execute,
                )
                for signal in symbol_signals:
                    signals.append(signal)
                    self._log_signal(signal)

            self._persist_signals(signals)
            return signals
        finally:
            if connect_broker and self._connector.is_connected:
                self._connector.disconnect()

    def _load_market_data(
        self,
        symbols: Sequence[str],
        *,
        trace_id: str,
    ) -> MarketDataBundle:
        timeframes = resolve_timeframes(self.config)
        data: dict[str, dict[str, object]] = {}
        for symbol in symbols:
            data[symbol] = {
                timeframe: self._market_data.fetch_candles(symbol, timeframe)
                for timeframe in timeframes
            }
        logger.info(
            f"Market data ready for {len(symbols)} symbol(s) across {len(timeframes)} timeframe(s)"
        )
        self.event_logger.system_event(
            "Pipeline market data loaded",
            event_type="pipeline_data_loaded",
            trace_id=trace_id,
            data={"symbols": list(symbols), "timeframes": list(timeframes)},
        )
        return MarketDataBundle(data=data)  # type: ignore[arg-type]

    def _process_symbol(
        self,
        symbol: str,
        *,
        bundle: MarketDataBundle,
        trace_id: str,
        execute: bool,
    ) -> list[TradeSignal]:
        quote = self._connector.get_quote(symbol)
        spread_pips = spread_price_to_pips(quote.spread, symbol)
        candles = bundle.data[symbol]

        pipeline_results = self._pipeline.run(
            symbol=symbol,
            candles=candles,
            bid=quote.bid,
            ask=quote.ask,
            spread_pips=spread_pips,
            trace_id=trace_id,
        )
        signals = self._router.route_all(
            pipeline_results,
            risk_pct=self.config.risk.per_trade_pct,
        )
        routed: list[TradeSignal] = []
        for signal in signals:
            if execute and signal.decision == "TRADE":
                routed.append(self._executor.execute(signal))
            else:
                routed.append(signal)
        if routed:
            return routed
        return [
            TradeSignal(
                symbol=symbol,
                decision="NO_TRADE",
                direction="none",
                confidence=0.0,
                entry=None,
                stop_loss=None,
                take_profit=None,
                risk_pct=self.config.risk.per_trade_pct,
                lot_size=0.0,
                reason="No pipeline candidates",
                mode="normal",
                trace_id=trace_id,
            )
        ]

    def _log_signal(self, signal: TradeSignal) -> None:
        logger.info(
            f"{signal.symbol} {signal.decision} {signal.direction} "
            f"mode={signal.mode} confidence={signal.confidence:.2f} - {signal.reason}"
        )
        self.event_logger.trade_decision(
            f"{signal.symbol} {signal.decision}",
            symbol=signal.symbol,
            trace_id=signal.trace_id,
            action=signal.decision.lower(),
            data=signal.to_dict(),
        )

    def _persist_signals(self, signals: list[TradeSignal]) -> None:
        path = self.project_root / "logs" / "pipeline_signals.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [signal.to_dict() for signal in signals]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info(f"Pipeline signals saved to {path}")

        if self.config.pipeline.output_json:
            print(json.dumps(payload, indent=2))
