"""
Trade exit engine for Kraitos.

Hard exits: stop loss and take profit levels.
Exit management: ATR regret trailing, 20-bar extreme grace, EMA12/EMA50 slope
override via should_exit().
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from loguru import logger

from execution.atr_timing_engine import EMA_SLOW, should_exit
from intelligence.thesis_trade_management import (
    check_thesis_invalidation,
    resolve_exit_phase,
)
from execution.models import ExitAction, ExitContext, ExitDecision, OpenTrade

REQUIRED_COLUMNS = ("time", "open", "high", "low", "close", "tick_volume", "spread")


@dataclass(frozen=True)
class ExitEngineConfig:
    """Thresholds for exit evaluation."""

    min_candles: int = EMA_SLOW + 2


class ExitEngineError(Exception):
    """Raised when exit context is invalid."""


class ExitEngine:
    """Evaluate open trades and recommend exit actions."""

    def __init__(
        self,
        config: ExitEngineConfig | None = None,
        *,
        execution_quality: object | None = None,
    ) -> None:
        self.config = config or ExitEngineConfig()
        if execution_quality is None:
            from strategies.execution_quality_engine import ExecutionQualityEngine

            self._execution_quality = ExecutionQualityEngine()
        else:
            self._execution_quality = execution_quality

    def evaluate(self, context: ExitContext) -> ExitDecision:
        """
        Evaluate an open trade and return an exit action with reason.

        Priority:
            1. cut_loss (hard stop)
            2. take_profit (hard target)
            3. close_early (ATR regret / grace break via should_exit)
            4. trail_stop (ATR trail via should_exit)
            5. hold_trade
        """
        self._validate_context(context)
        trade = context.trade

        if self._stop_hit(trade, context.current_price):
            reason = f"Stop loss hit at {context.current_price:.5f}"
            return self._decision("cut_loss", reason, trade.symbol)

        if self._take_profit_hit(trade, context.current_price):
            reason = f"Take profit reached at {context.current_price:.5f}"
            return self._decision("take_profit", reason, trade.symbol)

        exit_phase = resolve_exit_phase(
            partial_taken=trade.partial_taken,
            tp2_taken=trade.tp2_taken,
        )
        if exit_phase == "thesis_protection":
            if trade.invalidation_level is not None and trade.invalidation_level > 0:
                invalidated, inv_reason = check_thesis_invalidation(
                    side=trade.side,
                    current_price=context.current_price,
                    invalidation_level=trade.invalidation_level,
                    structure=context.structure,
                )
                if invalidated:
                    return self._decision(
                        "close_early",
                        f"thesis invalidation: {inv_reason}",
                        trade.symbol,
                    )
            return self._decision(
                "hold_trade",
                "thesis protection — hold for invalidation or TP1",
                trade.symbol,
            )

        frame = self._prepare_candles(context.candles)
        best_price = (
            trade.best_price
            if trade.best_price is not None
            else context.current_price
        )
        timing = should_exit(
            side=trade.side,
            entry_price=trade.entry_price,
            current_price=context.current_price,
            stop_loss=trade.stop_loss,
            candles=frame,
            bars_since_entry=trade.bars_since_entry,
            best_price=best_price,
            partial_taken=trade.partial_taken,
            exit_phase=exit_phase,
        )

        if timing.action == "EXIT":
            return self._decision("close_early", timing.reason, trade.symbol)

        scratch = self._evaluate_scout_scratch(context, frame)
        if scratch is not None:
            return scratch

        if timing.action == "TRAIL" and timing.new_stop is not None:
            reason = f"ATR trail: {timing.reason} -> {timing.new_stop:.5f}"
            return ExitDecision(
                action="trail_stop",
                reason=reason,
                new_stop_loss=round(timing.new_stop, 5),
            )

        risk_dist = abs(trade.entry_price - trade.stop_loss) or 1e-9
        current_r = (
            (context.current_price - trade.entry_price) / risk_dist
            if trade.side == "buy"
            else (trade.entry_price - context.current_price) / risk_dist
        )
        setup_kind = context.setup_kind or "harvest"
        trend_health = context.trend_quality_score or 50

        from strategies.trade_maturity_engine import TradeMaturityEngine

        open_maturity = TradeMaturityEngine().evaluate_open(
            side=trade.side,
            current_r=current_r,
            setup_kind=setup_kind,
            trend_health=trend_health,
        )
        if open_maturity.commitment == "scratch":
            return self._decision(
                "close_early",
                f"scalp scratch — no acceptance ({current_r:.2f}R): {open_maturity.explanation}",
                trade.symbol,
            )
        if open_maturity.maturity_stage == "invalidated":
            return self._decision(
                "close_early",
                f"thesis invalidated: {open_maturity.explanation}",
                trade.symbol,
            )

        exec_result = self._execution_quality.evaluate_exit(
            symbol=trade.symbol,
            side=trade.side,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            current_price=context.current_price,
            candles=frame,
            structure=context.structure,
            momentum=context.momentum,
            invalidation_level=trade.invalidation_level,
            trend_quality_score=context.trend_quality_score,
            reversal_pressure_score=context.reversal_pressure_score,
            partial_taken=trade.partial_taken,
        )
        if exec_result.fast_failure is not None:
            ff = exec_result.fast_failure
            ff_threshold = 55
            if setup_kind == "harvest" and trend_health >= 55 and current_r > -0.6:
                ff_threshold = 72
            elif setup_kind == "micro_scalp" and current_r <= -0.25:
                ff_threshold = 42
            if ff.recommended_action == "exit_early" and ff.failure_score >= ff_threshold:
                return self._decision(
                    "close_early",
                    f"fast failure: {ff.explanation}",
                    trade.symbol,
                )
        if exec_result.repair is not None and exec_result.exit is not None:
            repair = exec_result.repair
            exit_q = exec_result.exit
            if repair.instant_close:
                return self._decision(
                    "close_early",
                    f"thesis repair exit: {repair.explanation}",
                    trade.symbol,
                )
            if exit_q.exit_style == "scale_out" and repair.repair_action in {
                "scale_down",
                "reduce_exposure",
                "tighten_and_scale",
            }:
                fraction = max(0.25, min(0.75, 1.0 - repair.size_multiplier))
                return ExitDecision(
                    action="scale_out",
                    reason=f"opportunity repair: {repair.explanation}",
                    scale_fraction=fraction,
                )

        reason = f"Hold {trade.side} trade: {timing.reason}"
        return self._decision("hold_trade", reason, trade.symbol)

    def _evaluate_scout_scratch(
        self, context: ExitContext, frame: pd.DataFrame
    ) -> ExitDecision | None:
        trade = context.trade
        eligible = (
            context.scratch_eligible
            or context.scout_or_commit in {"scout", "probe", "micro_probe"}
            or context.momentum_clarity_at_entry == "unclear"
        )
        if not eligible:
            return None

        from strategies.fast_failure_engine import FastFailureEngine
        from strategies.market_acceptance_engine import MarketAcceptanceEngine

        accept = MarketAcceptanceEngine().evaluate(
            side=trade.side,
            candles=frame,
            invalidation_level=trade.invalidation_level,
            structure=context.structure,
            spread_pips=context.spread_pips,
        )
        scratch = FastFailureEngine().evaluate_scout_scratch(
            symbol=trade.symbol,
            side=trade.side,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            current_price=context.current_price,
            bars_since_entry=trade.bars_since_entry,
            setup_kind=context.setup_kind,
            scout_or_commit=context.scout_or_commit or "scout",
            momentum_clarity=context.momentum_clarity_at_entry or "unclear",
            entry_acceptance_score=context.acceptance_score_at_entry,
            current_acceptance_score=accept.acceptance_score,
            entry_rejection_score=context.rejection_score_at_entry,
            current_rejection_score=accept.rejection_score,
            spread_pips=context.spread_pips,
            spread_limit=context.spread_limit,
            candles=frame,
            partial_taken=trade.partial_taken,
        )
        if not scratch.should_scratch:
            return None
        return self._decision(
            "close_early",
            f"scout scratch ({scratch.scratch_reason}): {scratch.explanation}",
            trade.symbol,
        )

    def _validate_context(self, context: ExitContext) -> None:
        if context.current_price <= 0:
            raise ExitEngineError("current_price must be positive")
        if context.trade.volume <= 0:
            raise ExitEngineError("trade volume must be positive")

    def _prepare_candles(self, candles: pd.DataFrame) -> pd.DataFrame:
        if candles is None or candles.empty:
            raise ExitEngineError("Candle data is empty")

        missing = [column for column in REQUIRED_COLUMNS if column not in candles.columns]
        if missing:
            raise ExitEngineError(f"Missing columns: {', '.join(missing)}")

        frame = candles.copy()
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frame = frame.dropna(subset=["open", "high", "low", "close"])
        frame = frame.sort_values("time").reset_index(drop=True)

        if len(frame) < self.config.min_candles:
            raise ExitEngineError(
                f"At least {self.config.min_candles} candles required, got {len(frame)}"
            )
        return frame

    def _stop_hit(self, trade: OpenTrade, current_price: float) -> bool:
        if trade.side == "buy":
            return current_price <= trade.stop_loss
        return current_price >= trade.stop_loss

    def _take_profit_hit(self, trade: OpenTrade, current_price: float) -> bool:
        if trade.take_profit is None:
            return False
        if trade.side == "buy":
            return current_price >= trade.take_profit
        return current_price <= trade.take_profit

    def _decision(self, action: ExitAction, reason: str, symbol: str) -> ExitDecision:
        logger.info(f"Exit {action} {symbol}: {reason}")
        return ExitDecision(action=action, reason=reason)
