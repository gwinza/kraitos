"""Simulated trade execution for the integrated pipeline."""

from __future__ import annotations

from loguru import logger

from config.settings import KraitosConfig
from controls.trading_gate import TradingGate
from core.signal_router import TradeSignal
from execution.paper_trader import PaperTrader


class TradeExecutor:
    """Execute approved signals in simulation mode only."""

    def __init__(
        self,
        *,
        config: KraitosConfig,
        paper_trader: PaperTrader,
        trading_gate: TradingGate | None = None,
    ) -> None:
        self._config = config
        self._paper_trader = paper_trader
        self._trading_gate = trading_gate

    @property
    def simulation_only(self) -> bool:
        """Whether live broker orders are blocked."""
        return self._config.simulation_only

    def execute(self, signal: TradeSignal) -> TradeSignal:
        """
        Open a paper trade when the signal is TRADE.

        Live order placement is never attempted by this executor.
        """
        if signal.decision != "TRADE":
            return signal
        if signal.direction not in {"buy", "sell"}:
            return signal

        if self._trading_gate is not None:
            allowed, reason = self._trading_gate.can_execute(
                live=(
                    self._config.trading.live_enabled
                    and self._config.pipeline.execution_mode == "live"
                )
            )
            if not allowed:
                logger.warning(f"Execution blocked for {signal.symbol}: {reason}")
                return TradeSignal(
                    **{
                        **signal.to_dict(),
                        "decision": "NO_TRADE",
                        "reason": reason,
                        "executed": False,
                    }
                )

        if self._config.trading.live_enabled and not self._config.simulation_only:
            logger.warning(
                f"Live execution blocked for {signal.symbol}; "
                "pipeline is configured for simulation only"
            )
            return TradeSignal(
                **{
                    **signal.to_dict(),
                    "decision": "NO_TRADE",
                    "reason": "Live execution disabled; simulation-only mode",
                    "executed": False,
                }
            )
        if signal.entry is None or signal.stop_loss is None:
            return TradeSignal(
                **{
                    **signal.to_dict(),
                    "decision": "NO_TRADE",
                    "reason": "Missing entry or stop loss for execution",
                    "executed": False,
                }
            )

        trade = self._paper_trader.open_trade(
            symbol=signal.symbol,
            side=signal.direction,  # type: ignore[arg-type]
            entry_price=signal.entry,
            lot_size=signal.lot_size,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            reason=signal.reason,
            trace_id=signal.trace_id,
            invalidation_level=(
                signal.invalidation_level if signal.invalidation_level else None
            ),
            entry_type=getattr(signal, "entry_type", None) or None,
            story_direction=getattr(signal, "story_direction", None) or None,
            story_confidence=getattr(signal, "story_confidence", None) or None,
            story_narrative=getattr(signal, "story_narrative", None) or None,
        )
        logger.info(
            f"Simulated {signal.direction} {signal.symbol} "
            f"{signal.lot_size:.2f} lots (trade_id={trade.trade_id})"
        )
        return TradeSignal(
            symbol=signal.symbol,
            decision=signal.decision,
            direction=signal.direction,
            confidence=signal.confidence,
            entry=signal.entry,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            risk_pct=signal.risk_pct,
            lot_size=signal.lot_size,
            reason=signal.reason,
            mode=signal.mode,
            trace_id=signal.trace_id,
            executed=True,
            execution_id=trade.trade_id,
            partial_tp=signal.partial_tp,
            runner_tp=signal.runner_tp,
            partial_fraction=signal.partial_fraction,
            move_stop_to_breakeven=signal.move_stop_to_breakeven,
            enable_early_exit=signal.enable_early_exit,
            stagnation_bars_limit=signal.stagnation_bars_limit,
            min_progress_r=signal.min_progress_r,
            spread_limit_pips=signal.spread_limit_pips,
            runner_allowed=signal.runner_allowed,
            conviction_score=signal.conviction_score,
            invalidation_level=signal.invalidation_level,
            trade_theme=signal.trade_theme,
            theme_confidence=signal.theme_confidence,
            thesis_snapshot=signal.thesis_snapshot,
        )
