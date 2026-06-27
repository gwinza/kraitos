"""Backtest engine that replays historical candles through the live signal pipeline."""



from __future__ import annotations



from collections import Counter

from dataclasses import dataclass, field

from datetime import datetime, timezone

from pathlib import Path

from typing import Callable, Sequence



import pandas as pd

from loguru import logger



from backtesting.candle_resampler import PIPELINE_TIMEFRAMES, build_symbol_candles
from strategies.multitimeframe_bias import MIN_CANDLES_BY_TIMEFRAME

from backtesting.performance_report import PerformanceReport

from config.settings import KraitosConfig

from core.helpers import pip_size_for_symbol, spread_price_to_pips

from core.pipeline import TradingPipeline

from core.pipeline_models import PipelineResult

from core.risk_controller import RiskController

from core.signal_router import SignalRouter, TradeSignal

from paper_trading.paper_executor import PaperExecutor, PaperExecutorConfig

from paper_trading.virtual_account import ValidationConfig, VirtualAccount



TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "H1": 60,
    "H4": 240,
    "H8": 480,
}





@dataclass(frozen=True)

class BacktestEngineConfig:

    """Settings for pipeline-backed historical replay."""



    driver_timeframe: str = "M5"

    step: int = 1

    min_warmup_bars: int = 0

    validation: ValidationConfig = field(default_factory=ValidationConfig)





@dataclass

class BacktestSkipStats:

    """Counters explaining why bars did not become closed trades."""



    timeline_evaluations: int = 0

    warmup_skips: int = 0

    account_halt_skips: int = 0

    trade_signals: int = 0

    positions_opened: int = 0

    positions_closed: int = 0

    no_trade_records: int = 0

    no_trade_reasons: Counter[str] = field(default_factory=Counter)

    mandatory_failures: Counter[str] = field(default_factory=Counter)

    stage_failures: Counter[str] = field(default_factory=Counter)

    executor_events: Counter[str] = field(default_factory=Counter)





@dataclass

class BacktestRunResult:

    """Output from a validation backtest run."""



    signals: list[TradeSignal] = field(default_factory=list)

    account: VirtualAccount | None = None

    report: PerformanceReport | None = None

    summary: str = ""

    skip_stats: BacktestSkipStats = field(default_factory=BacktestSkipStats)





class BacktestEngine:

    """

    Replay historical candles through the same pipeline used by main.py.

    RESEARCH/DEMO ONLY — optimistic execution assumptions.
    Live readiness uses ConservativeBacktestEngine via AuditorBrain.

    Architecture: TraderBrain (via TradingPipeline) generates signals;
    this engine applies optimistic fills. Conservative fills are auditor-only.

    No live orders are placed. Trades are simulated via PaperExecutor.

    """



    def __init__(

        self,

        *,

        config: KraitosConfig,

        pipeline: TradingPipeline,

        risk_controller: RiskController,

        router: SignalRouter | None = None,

        engine_config: BacktestEngineConfig | None = None,

        journal_path: Path | None = None,

        portfolio_builder: Callable[[], object] | None = None,

    ) -> None:

        self.config = config

        self.pipeline = pipeline

        self.risk_controller = risk_controller

        self.router = router or SignalRouter()

        self.engine_config = engine_config or BacktestEngineConfig()

        self._portfolio_builder = portfolio_builder

        if portfolio_builder is not None:

            self.risk_controller.set_portfolio_builder(portfolio_builder)



        validation = self.engine_config.validation

        self.account = VirtualAccount(validation, journal_path=journal_path)

        self.executor = PaperExecutor(

            self.account,

            config=PaperExecutorConfig(

                driver_timeframe=self.engine_config.driver_timeframe,

                spread_pips=validation.spread_pips,

            ),

        )



    def run(

        self,

        candles_by_symbol: dict[str, dict[str, pd.DataFrame]],

        *,

        symbols: Sequence[str] | None = None,

    ) -> BacktestRunResult:

        """Walk historical candles and simulate pipeline signals."""

        target_symbols = tuple(symbols) if symbols else tuple(candles_by_symbol.keys())

        driver_tf = self.engine_config.driver_timeframe

        signals: list[TradeSignal] = []

        stats = BacktestSkipStats()



        normalized = build_symbol_candles(candles_by_symbol)

        timeline = self._build_timeline(normalized, target_symbols, driver_tf)

        if not timeline:

            logger.warning("No historical bars available for backtest")

            report = PerformanceReport(self.account)

            return BacktestRunResult(

                signals=signals,

                account=self.account,

                report=report,

                summary=report.render(),

                skip_stats=stats,

            )



        for moment, active_symbols in timeline:

            for symbol in active_symbols:

                bar = self._bar_at(normalized[symbol][driver_tf], moment)

                if bar is None:

                    continue



                closed_before = len(self.account.closed_entries)

                closed_ids = self.executor.monitor_symbol(symbol, bar)

                stats.positions_closed += len(closed_ids)

                if len(self.account.closed_entries) > closed_before:

                    for _ in range(len(self.account.closed_entries) - closed_before):

                        stats.executor_events["take_profit_or_stop_loss"] += 1



                sliced = self._slice_candles(normalized[symbol], moment)

                if not self._has_warmup(sliced):

                    stats.warmup_skips += 1

                    continue



                allowed, halt_reason = self.account.can_trade(moment)

                if not allowed:

                    stats.account_halt_skips += 1

                    stats.executor_events[halt_reason or "account_halt"] += 1

                    continue



                stats.timeline_evaluations += 1

                bid, ask, spread_pips = self._quote_from_bar(

                    bar,

                    symbol,

                    spread_pips=self.engine_config.validation.spread_pips,

                )

                trace_id = f"bt-{symbol}-{moment.isoformat()}"



                pipeline_results = self.pipeline.run(

                    symbol=symbol,

                    candles=sliced,

                    bid=bid,

                    ask=ask,

                    spread_pips=spread_pips,

                    trace_id=trace_id,

                    evaluation_moment=moment,

                )

                cycle_signals = self.router.route_all(

                    pipeline_results,

                    risk_pct=self.engine_config.validation.risk_per_trade_pct,

                )

                for pipeline_result, signal in zip(pipeline_results, cycle_signals):

                    signals.append(signal)

                    self._track_pipeline_stats(stats, pipeline_result, signal)



                    if signal.decision == "TRADE":

                        stats.trade_signals += 1

                        opens_before = len(self.account.open_positions)

                        self.executor.try_open(signal, candles=sliced, moment=moment)

                        if len(self.account.open_positions) > opens_before:

                            stats.positions_opened += 1

                            from portfolio.unlimited_opportunity_tracker import (
                                get_unlimited_opportunity_tracker,
                            )

                            get_unlimited_opportunity_tracker().record_open_count(
                                len(self.account.open_positions)
                            )

                        else:

                            stats.executor_events["trade_open_blocked"] += 1

                    else:

                        self._record_no_trade(signal, moment)

                        stats.no_trade_records += 1



        self._close_remaining_positions(normalized, target_symbols, driver_tf, stats)



        report = PerformanceReport(self.account)

        summary = report.render()

        logger.info(summary)

        return BacktestRunResult(

            signals=signals,

            account=self.account,

            report=report,

            summary=summary,

            skip_stats=stats,

        )



    def _track_pipeline_stats(

        self,

        stats: BacktestSkipStats,

        pipeline_result: PipelineResult,

        signal: TradeSignal,

    ) -> None:

        if pipeline_result.harvest is not None and not pipeline_result.harvest.allowed:

            reason = pipeline_result.harvest.reason

            if reason.startswith("Mandatory conditions failed:"):

                failed = reason.split(":", 1)[1].strip()

                for name in failed.split(","):

                    stats.mandatory_failures[name.strip()] += 1

            else:

                stats.stage_failures["harvest_secondary"] += 1



        if pipeline_result.entry is not None:

            action = pipeline_result.entry.action

            if action == "reject":

                stats.stage_failures["entry_reject"] += 1

            elif action == "wait":

                stats.stage_failures["entry_wait"] += 1



        if pipeline_result.risk is not None and not pipeline_result.risk.approved:

            stats.stage_failures["risk_reject"] += 1



        if signal.decision == "NO_TRADE" and signal.reason:

            stats.no_trade_reasons[signal.reason] += 1



    def _record_no_trade(self, signal: TradeSignal, moment: datetime) -> None:

        self.account.record_skipped(

            symbol=signal.symbol,

            timeframe=self.engine_config.driver_timeframe,

            direction=signal.direction,  # type: ignore[arg-type]

            entry=signal.entry,

            stop_loss=signal.stop_loss,

            take_profit=signal.take_profit,

            confidence=signal.confidence,

            mode=signal.mode,

            reason=signal.reason,

            moment=moment,

        )



    def _close_remaining_positions(

        self,

        candles_by_symbol: dict[str, dict[str, pd.DataFrame]],

        symbols: Sequence[str],

        driver_tf: str,

        stats: BacktestSkipStats,

    ) -> None:

        for symbol in symbols:

            frame = candles_by_symbol[symbol][driver_tf]

            if frame.empty:

                continue

            final_bar = frame.iloc[-1]

            final_time = pd.Timestamp(final_bar["time"]).to_pydatetime()

            if final_time.tzinfo is None:

                final_time = final_time.replace(tzinfo=timezone.utc)

            for trade_id, position in list(self.account.open_positions.items()):

                if position.symbol != symbol:

                    continue

                self.account.close_position(

                    trade_id,

                    exit_price=float(final_bar["close"]),

                    exit_time=final_time,

                    reason="backtest_end",

                )

                stats.positions_closed += 1

                stats.executor_events["backtest_end_close"] += 1



    def _build_timeline(

        self,

        candles_by_symbol: dict[str, dict[str, pd.DataFrame]],

        symbols: Sequence[str],

        driver_tf: str,

    ) -> list[tuple[datetime, tuple[str, ...]]]:

        events: dict[datetime, list[str]] = {}

        step = max(1, self.engine_config.step)

        warmup = self._resolve_warmup_bars(driver_tf)



        for symbol in symbols:

            frame = candles_by_symbol[symbol][driver_tf]

            for offset, row in enumerate(frame.itertuples(index=False)):

                if offset < warmup or offset % step != 0:

                    continue

                moment = pd.Timestamp(row.time).to_pydatetime()

                if moment.tzinfo is None:

                    moment = moment.replace(tzinfo=timezone.utc)

                events.setdefault(moment, []).append(symbol)



        return [

            (moment, tuple(sorted(set(symbols_list))))

            for moment, symbols_list in sorted(events.items(), key=lambda item: item[0])

        ]



    @staticmethod

    def _bar_at(frame: pd.DataFrame, moment: datetime) -> pd.Series | None:

        times = pd.to_datetime(frame["time"], utc=True)

        matches = frame.loc[times == pd.Timestamp(moment)]

        if matches.empty:

            return None

        return matches.iloc[-1]



    @staticmethod

    def _slice_candles(

        candles: dict[str, pd.DataFrame],

        moment: datetime,

    ) -> dict[str, pd.DataFrame]:

        sliced: dict[str, pd.DataFrame] = {}

        cutoff = pd.Timestamp(moment)

        for timeframe in PIPELINE_TIMEFRAMES:

            frame = candles.get(timeframe)

            if frame is None or frame.empty:

                sliced[timeframe] = frame if frame is not None else pd.DataFrame()

                continue

            times = pd.to_datetime(frame["time"], utc=True)

            sliced[timeframe] = frame.loc[times <= cutoff].copy()

        return sliced



    def _has_warmup(self, candles: dict[str, pd.DataFrame]) -> bool:

        for timeframe, minimum in MIN_CANDLES_BY_TIMEFRAME.items():

            frame = candles.get(timeframe)

            if frame is None or len(frame) < minimum:

                return False

        return True



    def _resolve_warmup_bars(self, driver_tf: str) -> int:

        configured = self.engine_config.min_warmup_bars

        if configured > 0:

            return configured



        driver_minutes = TIMEFRAME_MINUTES.get(driver_tf, 60)

        required_m1 = 0

        for timeframe, minimum in MIN_CANDLES_BY_TIMEFRAME.items():

            tf_minutes = TIMEFRAME_MINUTES.get(timeframe, 60)

            required_m1 = max(required_m1, minimum * tf_minutes)

        return max(1, int(required_m1 / driver_minutes))



    @staticmethod

    def _quote_from_bar(

        bar: pd.Series,

        symbol: str,

        *,

        spread_pips: float = 1.0,

    ) -> tuple[float, float, float]:

        close = float(bar["close"])

        pip_size = pip_size_for_symbol(symbol)

        half = spread_pips * pip_size / 2.0

        bid = close - half

        ask = close + half

        return bid, ask, spread_price_to_pips(ask - bid, symbol)

