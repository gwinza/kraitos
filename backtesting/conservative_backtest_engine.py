"""Backtest replay with conservative, red-team-safe execution assumptions.

Architecture: TraderBrain (via TradingPipeline) generates trade intent;
AuditorBrain / execution_model apply conservative fill simulation here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Sequence

import pandas as pd
from loguru import logger

from backtesting.backtest_engine import BacktestEngineConfig, BacktestRunResult, BacktestSkipStats
from backtesting.candle_resampler import PIPELINE_TIMEFRAMES, build_symbol_candles
from backtesting.execution_model import (
    TIMEFRAME_MINUTES,
    ExecutionCostConfig,
    PendingEntry,
    bar_close_time,
    commission_cost,
    entry_fill_price,
    exit_fill_price,
    next_bar_open,
    resolve_position_exit,
    slice_closed_candles,
)
from backtesting.performance_report import PerformanceReport
from config.settings import KraitosConfig
from core.helpers import pip_size_for_symbol, pip_value_per_lot, spread_price_to_pips
from risk.risk_manager import RiskManager
from core.pipeline import TradingPipeline
from core.risk_controller import RiskController
from core.signal_router import SignalRouter, TradeSignal
from paper_trading.virtual_account import OpenVirtualPosition, ValidationConfig, VirtualAccount
from strategies.multitimeframe_bias import MIN_CANDLES_BY_TIMEFRAME


@dataclass(frozen=True)
class ConservativeBacktestConfig:
    """Conservative replay settings."""

    engine: BacktestEngineConfig = field(default_factory=BacktestEngineConfig)
    costs: ExecutionCostConfig = field(default_factory=ExecutionCostConfig)


class ConservativeBacktestEngine:
    """
    Replay candles with red-team execution rules:

    - Signals evaluated only on fully closed candles
    - Higher timeframes exclude in-progress periods
    - Entries fill on the next bar open after confirmation
    - Stop loss prioritized when TP and SL share a bar
    - Spread, commission, and slippage applied
    """

    def __init__(
        self,
        *,
        config: KraitosConfig,
        pipeline: TradingPipeline,
        risk_controller: RiskController,
        router: SignalRouter | None = None,
        conservative_config: ConservativeBacktestConfig | None = None,
        journal_path: object | None = None,
        portfolio_builder: Callable[[], object] | None = None,
        on_timeline_progress: Callable[[datetime, str], None] | None = None,
        auditor: object | None = None,
    ) -> None:
        self.config = config
        self.pipeline = pipeline
        self.risk_controller = risk_controller
        self.router = router or SignalRouter()
        self.conservative_config = conservative_config or ConservativeBacktestConfig()
        self.engine_config = self.conservative_config.engine
        self.costs = self.conservative_config.costs
        self._auditor = auditor
        self._portfolio_builder = portfolio_builder
        self._on_timeline_progress = on_timeline_progress
        if portfolio_builder is not None:
            self.risk_controller.set_portfolio_builder(portfolio_builder)

        validation = self.engine_config.validation
        self.account = VirtualAccount(validation, journal_path=journal_path)  # type: ignore[arg-type]
        self._pending: list[PendingEntry] = []

    def run(
        self,
        candles_by_symbol: dict[str, dict[str, pd.DataFrame]],
        *,
        symbols: Sequence[str] | None = None,
    ) -> BacktestRunResult:
        target_symbols = tuple(symbols) if symbols else tuple(candles_by_symbol.keys())
        driver_tf = self.engine_config.driver_timeframe
        signals: list[TradeSignal] = []
        stats = BacktestSkipStats()

        normalized = build_symbol_candles(candles_by_symbol)
        timeline = self._build_close_timeline(normalized, target_symbols, driver_tf)
        if not timeline:
            report = PerformanceReport(self.account)
            return BacktestRunResult(account=self.account, report=report, summary=report.render())

        for moment, kind, symbol, bar in timeline:
            if kind == "open":
                self._fill_pending_entries(moment, symbol, bar, stats)
                continue

            self._monitor_completed_bar(symbol, bar, stats, normalized.get(symbol), moment)
            if self._on_timeline_progress is not None:
                self._on_timeline_progress(moment, symbol)

            sliced = slice_closed_candles(normalized[symbol], moment)
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
                spread_pips=self.costs.spread_pips,
            )
            trace_id = f"cbt-{symbol}-{moment.isoformat()}"

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
            for signal in cycle_signals:
                signals.append(signal)
                if signal.decision == "TRADE":
                    stats.trade_signals += 1
                    if self.costs.entry_on_next_bar:
                        self._queue_next_bar_entry(symbol, bar, normalized[symbol], signal)
                    else:
                        self._pending.append(
                            PendingEntry(fill_moment=moment, signal=signal, symbol=symbol)
                        )
                else:
                    stats.no_trade_records += 1

        self._finalize_open_positions(normalized, target_symbols, driver_tf, stats)

        report = PerformanceReport(self.account)
        summary = report.render()
        logger.info(summary)
        self._refresh_harvest_memory()
        self._refresh_portfolio_memory()
        self._refresh_forecast_feedback()
        self._refresh_trader_memory()
        self._refresh_projection_learning()
        return BacktestRunResult(
            signals=signals,
            account=self.account,
            report=report,
            summary=summary,
            skip_stats=stats,
        )

    def _refresh_harvest_memory(self) -> None:
        """Store closed trade results into strategy and archetype memory."""
        allocator = getattr(self.pipeline, "_allocator", None)
        if allocator is None:
            return
        journal = getattr(self.account, "journal_path", None)
        if journal is None:
            from pathlib import Path
            journal = Path("logs") / "conservative_trade_journal.csv"
        try:
            allocator.refresh_fitness(journal)  # type: ignore[union-attr]
            allocator.maybe_write_reports(force=True)  # type: ignore[union-attr]
        except Exception:
            logger.debug("Harvest memory refresh skipped")

    def _record_forecast_outcome(
        self,
        *,
        symbol: str,
        result: str,
        r_multiple: float,
    ) -> None:
        feedback = getattr(self.pipeline, "_forecast_feedback", None)
        if feedback is None:
            return
        pending = getattr(feedback, "_pending", {})
        match_id = None
        for trace_id, payload in list(pending.items()):
            if str(payload.get("symbol", "")).strip().upper() == symbol.strip().upper():
                match_id = trace_id
                break
        if match_id is None:
            return
        feedback.record_trade_outcome(
            trace_id=match_id,
            result=result,
            r_multiple=r_multiple,
        )

    def _refresh_forecast_feedback(self) -> None:
        """Record forecast outcomes and update council memory."""
        feedback = getattr(self.pipeline, "_forecast_feedback", None)
        council = getattr(self.pipeline, "_council", None)
        if feedback is None:
            return
        journal = getattr(self.account, "journal_path", None)
        if journal is None:
            from pathlib import Path
            journal = Path("logs") / "conservative_trade_journal.csv"
        try:
            feedback.refresh_from_journal(journal)  # type: ignore[arg-type]
            if council is not None:
                feedback.update_council_memory(council.memory)
            feedback.write_accuracy_report()
        except Exception:
            logger.debug("Forecast feedback refresh skipped")

    def _refresh_portfolio_memory(self) -> None:
        """Feed closed trades into portfolio rotation and write reports."""
        engine = getattr(self.pipeline, "_portfolio_engine", None)
        if engine is None:
            return
        journal = getattr(self.account, "journal_path", None)
        if journal is None:
            from pathlib import Path
            journal = Path("logs") / "conservative_trade_journal.csv"
        try:
            import pandas as pd
            from validation.r_metrics import CLOSED_RESULTS

            frame = pd.read_csv(journal)
            if frame.empty:
                return
            closed = frame[frame["result"].isin(CLOSED_RESULTS)]
            for _, row in closed.iterrows():
                engine.record_trade_result(
                    symbol=str(row.get("symbol", "")),
                    mode=str(row.get("mode", "harvest")),
                    result=str(row.get("result", "")),
                    r_multiple=float(row.get("r_multiple", 0.0)),
                    drawdown_pct=float(row.get("drawdown_pct", 0.0) if "drawdown_pct" in row else 0.0),
                    side=str(row.get("direction", "")),
                    trade_theme=str(row.get("trade_theme", "")) if "trade_theme" in row else None,
                )
            engine.allocator.maybe_write_reports(force=True)
            engine.write_doctrine_reports()
        except Exception:
            logger.debug("Portfolio memory refresh skipped")

    def _refresh_projection_learning(self) -> None:
        """Update self-learning thesis projection parameters from closed journal rows."""
        trader_brain = getattr(self.pipeline, "_trader_brain", None)
        learning = getattr(trader_brain, "_projection_learning", None) if trader_brain else None
        if learning is None:
            return
        journal = getattr(self.account, "journal_path", None)
        if journal is None:
            from pathlib import Path
            journal = Path("logs") / "conservative_trade_journal.csv"
        try:
            learning.refresh_from_journal(journal)  # type: ignore[arg-type]
            learning.write_report()
        except Exception:
            logger.debug("Thesis projection learning refresh skipped")

    def _refresh_trader_memory(self) -> None:
        """Update trader memory outcomes from closed journal rows."""
        trader_brain = getattr(self.pipeline, "_trader_brain", None)
        memory = getattr(trader_brain, "_memory_engine", None) if trader_brain else None
        if memory is None:
            return
        journal = getattr(self.account, "journal_path", None)
        if journal is None:
            from pathlib import Path
            journal = Path("logs") / "conservative_trade_journal.csv"
        try:
            memory.refresh_from_journal(journal)  # type: ignore[arg-type]
            memory.write_trader_memory_report()
        except Exception:
            logger.debug("Trader memory refresh skipped")

    def _queue_next_bar_entry(
        self,
        symbol: str,
        bar: pd.Series,
        candles: dict[str, pd.DataFrame],
        signal: TradeSignal,
    ) -> None:
        frame = candles.get(self.engine_config.driver_timeframe)
        if frame is None or frame.empty:
            return
        times = pd.to_datetime(frame["time"], utc=True)
        matches = frame.loc[times == pd.Timestamp(bar["time"])]
        if matches.empty:
            return
        idx = matches.index[-1]
        position = frame.index.get_loc(idx)
        if isinstance(position, slice):
            return
        if position + 1 >= len(frame):
            return
        next_open = pd.Timestamp(frame.iloc[position + 1]["time"]).to_pydatetime()
        if next_open.tzinfo is None:
            next_open = next_open.replace(tzinfo=timezone.utc)
        self._pending.append(PendingEntry(fill_moment=next_open, signal=signal, symbol=symbol))

    def _fill_pending_entries(
        self,
        moment: datetime,
        symbol: str,
        bar: pd.Series,
        stats: BacktestSkipStats,
    ) -> None:
        due = [
            entry
            for entry in self._pending
            if entry.fill_moment == moment and entry.symbol == symbol
        ]
        if not due:
            return

        open_price = float(bar["open"])

        for entry in due:
            signal: TradeSignal = entry.signal  # type: ignore[assignment]
            if signal.decision != "TRADE" or signal.direction not in {"buy", "sell"}:
                continue
            if signal.stop_loss is None or signal.lot_size <= 0:
                continue

            allowed, reason = self.account.can_trade(moment)
            if not allowed:
                stats.executor_events[reason or "account_halt"] += 1
                continue

            fill = entry_fill_price(
                direction=signal.direction,
                open_price=open_price,
                symbol=signal.symbol,
                costs=self.costs,
            )
            commission = commission_cost(signal.lot_size, self.costs) / 2.0
            self.account.balance -= commission

            risk_amount = RiskManager.position_risk_amount(
                volume=signal.lot_size,
                entry_price=fill,
                stop_loss=signal.stop_loss,
                pip_size=pip_size_for_symbol(signal.symbol),
                pip_value_per_lot=pip_value_per_lot(signal.symbol, fill),
            )
            partial_tp = getattr(signal, "partial_tp", None)
            runner_tp = getattr(signal, "runner_tp", None)
            take_profit = runner_tp if partial_tp is not None else signal.take_profit
            trade_id = signal.trace_id.replace(":", "-")[:64] or VirtualAccount._new_trade_id()
            position = OpenVirtualPosition(
                trade_id=trade_id,
                symbol=signal.symbol,
                timeframe=self.engine_config.driver_timeframe,
                direction=signal.direction,  # type: ignore[arg-type]
                entry=fill,
                stop_loss=signal.stop_loss,
                take_profit=take_profit,
                lot_size=signal.lot_size,
                confidence=signal.confidence,
                mode=signal.mode,
                reason=signal.reason,
                risk_amount=risk_amount,
                entry_time=moment,
                partial_tp=partial_tp,
                runner_tp=runner_tp,
                partial_fraction=getattr(signal, "partial_fraction", 0.5),
                move_stop_to_breakeven=getattr(signal, "move_stop_to_breakeven", False),
                enable_early_exit=getattr(signal, "enable_early_exit", True),
                spread_limit_pips=getattr(signal, "spread_limit_pips", 3.0),
                best_price=fill,
                conviction_score=getattr(signal, "conviction_score", 0.0),
                invalidation_level=getattr(signal, "invalidation_level", 0.0),
                trade_theme=getattr(signal, "trade_theme", ""),
                theme_confidence=getattr(signal, "theme_confidence", 0.0),
                thesis_snapshot=getattr(signal, "thesis_snapshot", ""),
                entry_stage=getattr(signal, "entry_stage", ""),
                scout_or_commit=getattr(signal, "scout_or_commit", ""),
                setup_kind=getattr(signal, "setup_kind", "") or (
                    "micro_scalp" if signal.mode == "scalp" else "harvest"
                ),
                acceptance_score_at_entry=int(
                    getattr(signal, "acceptance_score_at_entry", 50) or 50
                ),
                rejection_score_at_entry=int(
                    getattr(signal, "rejection_score_at_entry", 50) or 50
                ),
                momentum_clarity_at_entry=getattr(signal, "momentum_clarity_at_entry", ""),
                location_quality_at_entry=int(
                    getattr(signal, "location_quality_at_entry", 0) or 0
                ),
                timing_quality_at_entry=int(
                    getattr(signal, "timing_quality_at_entry", 0) or 0
                ),
                scratch_eligible=bool(getattr(signal, "scratch_eligible", False)),
                cio_confidence=float(getattr(signal, "cio_confidence", 0.0) or 0.0),
                cio_allocation=float(getattr(signal, "cio_allocation", 0.0) or 0.0),
                cio_mode=str(getattr(signal, "cio_mode", "") or ""),
                cio_summary=str(getattr(signal, "cio_summary", "") or ""),
                cognitive_snapshot=str(getattr(signal, "cognitive_snapshot", "") or ""),
                picture_clarity=str(getattr(signal, "picture_clarity", "") or ""),
                picture_confidence=float(getattr(signal, "picture_confidence", 0.0) or 0.0),
                selected_strategy=str(getattr(signal, "selected_strategy", "") or ""),
                strategy_fit=float(getattr(signal, "strategy_fit", 0.0) or 0.0),
                narrator_story=str(getattr(signal, "narrator_story", "") or ""),
                storyteller_snapshot=str(getattr(signal, "storyteller_snapshot", "") or ""),
            )
            self.account.open_position(position)
            stats.positions_opened += 1
            from intelligence.kraitos_thesis_doctrine import get_thesis_tracker

            get_thesis_tracker().record_position_opened()
            from portfolio.unlimited_opportunity_tracker import get_unlimited_opportunity_tracker
            from intelligence.participation_tracker import get_participation_tracker

            get_unlimited_opportunity_tracker().record_open_count(
                len(self.account.open_positions)
            )
            get_participation_tracker().record_simultaneous(len(self.account.open_positions))
            tier = "HARVEST" if signal.mode == "harvest" else "SCOUT"
            target_pips = 0.0
            if signal.take_profit is not None and signal.entry is not None:
                pip_size = pip_size_for_symbol(signal.symbol)
                target_pips = abs(signal.take_profit - signal.entry) / pip_size
            get_participation_tracker().record_opportunity_taken(
                symbol=signal.symbol,
                tier=tier,
                target_pips=target_pips,
            )

        self._pending = [
            entry
            for entry in self._pending
            if not (entry.fill_moment == moment and entry.symbol == symbol)
        ]

    def _evaluate_early_exit(
        self,
        position: object,
        close_price: float,
        high: float,
        low: float,
        candles: dict[str, pd.DataFrame] | None = None,
    ) -> tuple[float, str] | None:
        from intelligence.individual_trade_doctrine import DynamicExitEngine, DynamicExitPlan
        from paper_trading.virtual_account import OpenVirtualPosition

        if not isinstance(position, OpenVirtualPosition):
            return None

        driver = self.engine_config.driver_timeframe
        frame = (candles or {}).get(driver)
        m15 = (candles or {}).get("M15")
        m5 = frame if frame is not None and len(frame) > 0 else None

        spread_pips = float(getattr(self.costs, "spread_pips", 1.0))
        scratch_exit = self._evaluate_scout_scratch(
            position, close_price, m5, spread_pips=spread_pips
        )
        if scratch_exit is not None:
            return scratch_exit
        lifecycle_exit = self._evaluate_lifecycle_exit(position, close_price, frame)
        if lifecycle_exit is not None:
            return lifecycle_exit
        exit_plan = DynamicExitPlan(enable_early_exit=True)
        evaluation = DynamicExitEngine.evaluate_open_position(
            side=position.direction,
            entry_price=position.entry,
            stop_loss=position.stop_loss,
            current_price=close_price,
            bars_since_entry=position.bars_since_entry,
            partial_taken=position.partial_taken,
            tp2_taken=position.tp2_taken,
            spread_pips=spread_pips,
            spread_limit=position.spread_limit_pips,
            exit_plan=exit_plan,
            candles=m5,
            best_price=position.best_price,
            invalidation_level=position.invalidation_level or None,
            candles_m15=m15,
        )
        if evaluation.decision == "EXIT_EARLY":
            from intelligence.thesis_trade_management import (
                get_trade_memory_tracker,
                resolve_exit_phase,
            )

            phase = resolve_exit_phase(
                partial_taken=position.partial_taken,
                tp2_taken=position.tp2_taken,
            )
            if phase == "thesis_protection":
                get_trade_memory_tracker().record_premature_exit(would_have_tp=False)
            reason_tag = (
                "thesis_invalidation"
                if "invalidation" in (evaluation.reason or "").lower()
                else "early_exit_stagnation"
            )
            return (
                exit_fill_price(
                    direction=position.direction,
                    raw_price=close_price,
                    symbol=position.symbol,
                    costs=self.costs,
                ),
                reason_tag,
            )
        if evaluation.decision == "MOVE_TO_BREAKEVEN" and evaluation.new_stop is not None:
            if position.direction == "buy":
                position.stop_loss = max(position.stop_loss, evaluation.new_stop)
            else:
                position.stop_loss = min(position.stop_loss, evaluation.new_stop)
        return None

    def _evaluate_scout_scratch(
        self,
        position: object,
        close_price: float,
        frame: pd.DataFrame | None,
        *,
        spread_pips: float,
    ) -> tuple[float, str] | None:
        from paper_trading.virtual_account import OpenVirtualPosition, VirtualAccount
        from strategies.fast_failure_engine import FastFailureEngine
        from strategies.market_acceptance_engine import MarketAcceptanceEngine

        if not isinstance(position, OpenVirtualPosition):
            return None
        if not position.enable_early_exit:
            return None
        is_true_commit = (
            position.scout_or_commit == "commit"
            and position.momentum_clarity_at_entry in {"clear", "aligned"}
            and position.acceptance_score_at_entry >= 58
        )
        eligible = (
            position.scratch_eligible
            or position.scout_or_commit in {"scout", "probe", "micro_probe"}
            or position.momentum_clarity_at_entry == "unclear"
            or position.entry_stage in {"idea", "developing", "scout"}
        )
        if not eligible and not is_true_commit:
            eligible = position.setup_kind == "micro_scalp" or position.mode == "scalp"
        if is_true_commit:
            return None
        if not eligible:
            return None

        accept = MarketAcceptanceEngine().evaluate(
            side=position.direction,
            candles=frame,
            invalidation_level=position.invalidation_level or None,
            spread_pips=spread_pips,
        )
        position.acceptance_score_after_entry = accept.acceptance_score
        position.rejection_score_after_entry = accept.rejection_score
        position.peak_acceptance_score = max(
            position.peak_acceptance_score, accept.acceptance_score
        )
        if (
            position.scout_or_commit == "scout"
            and accept.acceptance_score >= 65
            and position.bars_since_entry >= 2
        ):
            position.thesis_matured = True

        setup_kind = position.setup_kind or (
            "micro_scalp" if position.mode == "scalp" else "harvest"
        )
        scratch = FastFailureEngine().evaluate_scout_scratch(
            symbol=position.symbol,
            side=position.direction,
            entry_price=position.entry,
            stop_loss=position.stop_loss,
            current_price=close_price,
            bars_since_entry=position.bars_since_entry,
            setup_kind=setup_kind,
            scout_or_commit=position.scout_or_commit or "scout",
            momentum_clarity=position.momentum_clarity_at_entry or "unclear",
            entry_acceptance_score=position.acceptance_score_at_entry,
            current_acceptance_score=accept.acceptance_score,
            entry_rejection_score=position.rejection_score_at_entry,
            current_rejection_score=accept.rejection_score,
            spread_pips=spread_pips,
            spread_limit=position.spread_limit_pips,
            candles=frame,
            partial_taken=position.partial_taken,
        )
        if not scratch.should_scratch:
            position.why_not_scratch = scratch.why_not_scratch
            return None

        position.scratch_triggered = True
        position.why_not_scratch = ""
        return (
            exit_fill_price(
                direction=position.direction,
                raw_price=close_price,
                symbol=position.symbol,
                costs=self.costs,
            ),
            f"scout_scratch:{scratch.scratch_reason}",
        )

    def _evaluate_lifecycle_exit(
        self,
        position: object,
        close_price: float,
        frame: pd.DataFrame | None,
    ) -> tuple[float, str] | None:
        from paper_trading.virtual_account import OpenVirtualPosition

        if not isinstance(position, OpenVirtualPosition):
            return None
        if frame is None or len(frame) < 40:
            return None
        try:
            from strategies.trend_quality_engine import TrendQualityEngine

            lifecycle = TrendQualityEngine().analyze(
                frame,
                symbol=position.symbol,
                timeframe=self.engine_config.driver_timeframe,
            )
        except Exception:
            return None

        position.market_phase = lifecycle.trend_phase
        position.trend_quality_score = lifecycle.trend_quality_score
        position.reversal_pressure_score = lifecycle.reversal_probability
        position.continuation_probability = lifecycle.continuation_probability

        expected_trend = "bullish" if position.direction == "buy" else "bearish"
        against_thesis = (
            lifecycle.trend_direction not in {"neutral", expected_trend}
            and lifecycle.reversal_probability > lifecycle.continuation_probability
        )
        confirmed_reversal = lifecycle.trend_phase == "confirmed_reversal" and against_thesis
        distribution_failure = (
            lifecycle.trend_phase in {"distribution", "reversal_warning"}
            and lifecycle.reversal_probability >= 0.65
            and not position.partial_taken
        )
        if confirmed_reversal or distribution_failure:
            return (
                exit_fill_price(
                    direction=position.direction,
                    raw_price=close_price,
                    symbol=position.symbol,
                    costs=self.costs,
                ),
                "thesis_lifecycle_invalidation",
            )
        return None

    def _monitor_completed_bar(
        self,
        symbol: str,
        bar: pd.Series,
        stats: BacktestSkipStats,
        candles: dict[str, pd.DataFrame] | None = None,
        moment: datetime | None = None,
    ) -> None:
        bar_time = pd.Timestamp(bar["time"]).to_pydatetime()
        if bar_time.tzinfo is None:
            bar_time = bar_time.replace(tzinfo=timezone.utc)
        driver_tf = self.engine_config.driver_timeframe
        exit_moment = bar_close_time(pd.Timestamp(bar_time), driver_tf).to_pydatetime()
        if exit_moment.tzinfo is None:
            exit_moment = exit_moment.replace(tzinfo=timezone.utc)

        high = float(bar["high"])
        low = float(bar["low"])
        sliced = (
            slice_closed_candles(candles, moment)
            if candles is not None and moment is not None
            else candles
        )

        for trade_id, position in list(self.account.open_positions.items()):
            if position.symbol != symbol:
                continue
            position.bars_since_entry += 1
            if position.direction == "buy":
                position.best_price = max(position.best_price, high)
                if (
                    position.partial_taken
                    and position.runner_tp is not None
                    and high >= position.runner_tp
                ):
                    position.tp2_taken = True
            else:
                position.best_price = min(position.best_price, low)
                if (
                    position.partial_taken
                    and position.runner_tp is not None
                    and low <= position.runner_tp
                ):
                    position.tp2_taken = True
            close_price = float(bar["close"])
            early = self._evaluate_early_exit(position, close_price, high, low, sliced)
            if early is not None:
                early_price, early_reason = early
                closed = self.account.close_position(
                    trade_id,
                    exit_price=early_price,
                    exit_time=exit_moment,
                    reason=early_reason,
                )
                if closed is not None:
                    from intelligence.individual_trade_doctrine import get_individual_trade_tracker

                    get_individual_trade_tracker().record_early_exit()
                    result_label = "win" if closed.profit_loss > 0 else (
                        "loss" if closed.profit_loss < 0 else "breakeven"
                    )
                    self.risk_controller.drawdown_risk.record_trade_result(
                        symbol=position.symbol,
                        mode=position.mode,
                        result=result_label,
                        evaluation_moment=exit_moment,
                    )
                    stats.positions_closed += 1
                    stats.executor_events["early_exit_stagnation"] += 1
                continue
            event = resolve_position_exit(
                position,
                high=high,
                low=low,
                sl_first=self.costs.sl_first_on_ambiguity,
            )
            if event is None:
                continue
            fill = exit_fill_price(
                direction=position.direction,
                raw_price=event.price,
                symbol=position.symbol,
                costs=self.costs,
            )
            if event.partial:
                pip_size = pip_size_for_symbol(position.symbol)
                new_stop = position.stop_loss
                if event.move_stop_to_breakeven:
                    buffer = self.costs.spread_pips * pip_size
                    new_stop = (
                        position.entry + buffer
                        if position.direction == "buy"
                        else position.entry - buffer
                    )
                closed = self.account.scale_out_position(
                    trade_id,
                    exit_price=fill,
                    exit_time=exit_moment,
                    fraction=event.fraction,
                    reason=event.reason,
                    new_stop_loss=new_stop,
                    runner_tp=event.runner_tp,
                )
                if closed is not None:
                    from intelligence.kraitos_thesis_doctrine import get_thesis_tracker
                    get_thesis_tracker().record_tp1_hit()
                    self.account.balance -= commission_cost(closed.lot_size, self.costs) / 2.0
                    result_label = "win" if closed.profit_loss > 0 else (
                        "loss" if closed.profit_loss < 0 else "breakeven"
                    )
                    self.risk_controller.drawdown_risk.record_trade_result(
                        symbol=position.symbol,
                        mode=position.mode,
                        result=result_label,
                        evaluation_moment=exit_moment,
                    )
                    self._record_forecast_outcome(
                        symbol=position.symbol,
                        result=result_label,
                        r_multiple=float(getattr(closed, "r_multiple", 0.0)),
                    )
                stats.executor_events[event.reason] += 1
                continue

            position_before = self.account.open_positions.get(trade_id)
            was_runner = position_before is not None and position_before.partial_taken
            closed = self.account.close_position(
                trade_id, exit_price=fill, exit_time=exit_moment, reason=event.reason
            )
            self.account.balance -= commission_cost(position_before.lot_size if position_before else closed.lot_size, self.costs) / 2.0
            if closed is not None:
                result_label = "win" if closed.profit_loss > 0 else (
                    "loss" if closed.profit_loss < 0 else "breakeven"
                )
                if was_runner:
                    from intelligence.kraitos_thesis_doctrine import get_thesis_tracker

                    get_thesis_tracker().record_runner_close(
                        pnl=float(closed.profit_loss),
                        r_multiple=float(closed.r_multiple),
                        reason=event.reason,
                    )
                self.risk_controller.drawdown_risk.record_trade_result(
                    symbol=position.symbol,
                    mode=position.mode,
                    result=result_label,
                    evaluation_moment=exit_moment,
                )
                self._record_forecast_outcome(
                    symbol=position.symbol,
                    result=result_label,
                    r_multiple=float(getattr(closed, "r_multiple", 0.0)),
                )
            stats.positions_closed += 1
            stats.executor_events[event.reason] += 1

    def _finalize_open_positions(
        self,
        candles_by_symbol: dict[str, dict[str, pd.DataFrame]],
        symbols: Sequence[str],
        driver_tf: str,
        stats: BacktestSkipStats,
    ) -> None:
        if not self.costs.mark_open_at_backtest_end:
            return
        for symbol in symbols:
            frame = candles_by_symbol[symbol][driver_tf]
            if frame.empty:
                continue
            final_bar = frame.iloc[-1]
            close_price = float(final_bar["close"])
            final_open = pd.Timestamp(final_bar["time"]).to_pydatetime()
            if final_open.tzinfo is None:
                final_open = final_open.replace(tzinfo=timezone.utc)
            final_time = bar_close_time(pd.Timestamp(final_open), driver_tf).to_pydatetime()
            if final_time.tzinfo is None:
                final_time = final_time.replace(tzinfo=timezone.utc)

            for trade_id, position in list(self.account.open_positions.items()):
                if position.symbol != symbol:
                    continue
                was_runner = position.partial_taken
                fill = exit_fill_price(
                    direction=position.direction,
                    raw_price=close_price,
                    symbol=position.symbol,
                    costs=self.costs,
                )
                closed = self.account.close_position(
                    trade_id,
                    exit_price=fill,
                    exit_time=final_time,
                    reason="backtest_end_mark",
                )
                self.account.balance -= commission_cost(position.lot_size, self.costs) / 2.0
                if closed is not None and was_runner:
                    from intelligence.kraitos_thesis_doctrine import get_thesis_tracker

                    get_thesis_tracker().record_runner_close(
                        pnl=float(closed.profit_loss),
                        r_multiple=float(closed.r_multiple),
                        reason="backtest_end_mark",
                    )
                stats.positions_closed += 1
                stats.executor_events["backtest_end_mark"] += 1

    def _build_close_timeline(
        self,
        candles_by_symbol: dict[str, dict[str, pd.DataFrame]],
        symbols: Sequence[str],
        driver_tf: str,
    ) -> list[tuple[datetime, str, str, pd.Series]]:
        events: list[tuple[datetime, int, str, str, pd.Series]] = []
        step = max(1, self.engine_config.step)
        warmup = self._resolve_warmup_bars(driver_tf)

        for symbol in symbols:
            frame = candles_by_symbol[symbol][driver_tf]
            for offset in range(warmup, len(frame), step):
                bar = frame.iloc[offset]
                open_time = pd.Timestamp(bar["time"])
                if open_time.tzinfo is None:
                    open_time = open_time.tz_localize("UTC")
                close_time = bar_close_time(open_time, driver_tf)
                events.append((close_time.to_pydatetime(), 0, "close", symbol, bar))
                if self.costs.entry_on_next_bar and offset + 1 < len(frame):
                    next_bar = frame.iloc[offset + 1]
                    next_open = pd.Timestamp(next_bar["time"]).to_pydatetime()
                    if next_open.tzinfo is None:
                        next_open = next_open.replace(tzinfo=timezone.utc)
                    events.append((next_open, 1, "open", symbol, next_bar))

        ordered = sorted(events, key=lambda item: (item[0], item[1]))
        return [(moment, kind, symbol, bar) for moment, _prio, kind, symbol, bar in ordered]

    @staticmethod
    def _bar_at(frame: pd.DataFrame, moment: datetime) -> pd.Series | None:
        times = pd.to_datetime(frame["time"], utc=True)
        matches = frame.loc[times == pd.Timestamp(moment)]
        if matches.empty:
            return None
        return matches.iloc[-1]

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
        required_m1 = max(
            minimum * TIMEFRAME_MINUTES.get(timeframe, 60)
            for timeframe, minimum in MIN_CANDLES_BY_TIMEFRAME.items()
        )
        return max(1, int(required_m1 / driver_minutes))

    @staticmethod
    def _quote_from_bar(
        bar: pd.Series,
        symbol: str,
        *,
        spread_pips: float,
    ) -> tuple[float, float, float]:
        close = float(bar["close"])
        pip_size = pip_size_for_symbol(symbol)
        half = spread_pips * pip_size / 2.0
        bid = close - half
        ask = close + half
        return bid, ask, spread_price_to_pips(ask - bid, symbol)
