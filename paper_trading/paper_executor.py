"""Simulated trade execution using current candle prices (no live orders)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
from loguru import logger

from backtesting.execution_model import resolve_exit_price
from core.helpers import pip_size_for_symbol, pip_value_per_lot
from core.signal_router import TradeSignal
from paper_trading.virtual_account import OpenVirtualPosition, VirtualAccount
from risk.risk_manager import RiskManager


@dataclass(frozen=True)
class PaperExecutorConfig:
    """Execution settings for the validation layer."""

    driver_timeframe: str = "H1"
    spread_pips: float = 1.0


class PaperExecutor:
    """Open, monitor, and close simulated positions from pipeline signals."""

    def __init__(
        self,
        account: VirtualAccount,
        *,
        config: PaperExecutorConfig | None = None,
    ) -> None:
        self.account = account
        self.config = config or PaperExecutorConfig()

    def try_open(
        self,
        signal: TradeSignal,
        *,
        candles: dict[str, pd.DataFrame],
        moment: datetime | None = None,
    ) -> OpenVirtualPosition | None:
        """Attempt to open a simulated trade from a TRADE signal."""
        now = moment or datetime.now(timezone.utc)
        allowed, reason = self.account.can_trade(now)
        if not allowed:
            self.account.record_skipped(
                symbol=signal.symbol,
                timeframe=self.config.driver_timeframe,
                direction=signal.direction,  # type: ignore[arg-type]
                entry=signal.entry,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                confidence=signal.confidence,
                mode=signal.mode,
                reason=reason,
                moment=now,
            )
            return None

        if signal.decision != "TRADE" or signal.direction not in {"buy", "sell"}:
            return None
        if signal.entry is None or signal.stop_loss is None or signal.lot_size <= 0:
            self.account.record_skipped(
                symbol=signal.symbol,
                timeframe=self.config.driver_timeframe,
                direction=signal.direction,  # type: ignore[arg-type]
                entry=signal.entry,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                confidence=signal.confidence,
                mode=signal.mode,
                reason="Incomplete trade parameters",
                moment=now,
            )
            return None

        fill_price = self._fill_price(signal, candles)
        risk_amount = self._risk_amount(signal)

        position = OpenVirtualPosition(
            trade_id=VirtualAccount._new_trade_id(),
            symbol=signal.symbol,
            timeframe=self.config.driver_timeframe,
            direction=signal.direction,  # type: ignore[arg-type]
            entry=fill_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            lot_size=signal.lot_size,
            confidence=signal.confidence,
            mode=signal.mode,
            reason=signal.reason,
            risk_amount=risk_amount,
            entry_time=now,
        )
        self.account.open_position(position)
        logger.info(
            f"Paper open {signal.direction} {signal.symbol} "
            f"{signal.lot_size:.2f} lots @ {fill_price:.5f}"
        )
        return position

    def monitor_symbol(
        self,
        symbol: str,
        bar: pd.Series,
    ) -> list[str]:
        """Check open positions for stop loss or take profit on the current bar."""
        closed_ids: list[str] = []
        bar_time = pd.Timestamp(bar["time"]).to_pydatetime()
        if bar_time.tzinfo is None:
            bar_time = bar_time.replace(tzinfo=timezone.utc)

        high = float(bar["high"])
        low = float(bar["low"])

        for trade_id, position in list(self.account.open_positions.items()):
            if position.symbol != symbol:
                continue
            exit_price, reason = self._check_exit(position, high=high, low=low)
            if exit_price is None:
                continue
            self.account.close_position(
                trade_id,
                exit_price=exit_price,
                exit_time=bar_time,
                reason=reason,
            )
            closed_ids.append(trade_id)
        return closed_ids

    def _fill_price(self, signal: TradeSignal, candles: dict[str, pd.DataFrame]) -> float:
        frame = candles.get(self.config.driver_timeframe)
        if frame is not None and not frame.empty:
            close = float(frame.iloc[-1]["close"])
        elif signal.entry is not None:
            close = signal.entry
        else:
            close = 0.0

        pip_size = pip_size_for_symbol(signal.symbol)
        spread_price = self.config.spread_pips * pip_size
        if signal.direction == "buy":
            return close + spread_price / 2.0
        return close - spread_price / 2.0

    def _risk_amount(self, signal: TradeSignal) -> float:
        if signal.entry is None or signal.stop_loss is None:
            return 0.0
        pip_size = pip_size_for_symbol(signal.symbol)
        pip_value = pip_value_per_lot(signal.symbol, signal.entry)
        return RiskManager.position_risk_amount(
            volume=signal.lot_size,
            entry_price=signal.entry,
            stop_loss=signal.stop_loss,
            pip_size=pip_size,
            pip_value_per_lot=pip_value,
        )

    @staticmethod
    def _check_exit(
        position: OpenVirtualPosition,
        *,
        high: float,
        low: float,
    ) -> tuple[float | None, str]:
        return resolve_exit_price(position, high=high, low=low, sl_first=True)
