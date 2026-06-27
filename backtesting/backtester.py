"""
Basic backtesting engine for Kraitos.

Loads historical candle data, simulates trades with spread and stop/take-profit
levels, and produces performance metrics.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
from loguru import logger

from backtesting.models import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    Trade,
    TradeSignal,
    TradeSide,
)
from data.market_data import CANDLE_COLUMNS, prepare_candles

REQUIRED_COLUMNS = CANDLE_COLUMNS


class BacktestError(Exception):
    """Raised when backtest input or execution is invalid."""


class Backtester:
    """Simple candle-based backtester with spread and stop/take-profit support."""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run(
        self,
        candles: pd.DataFrame,
        signals: list[TradeSignal],
        *,
        symbol: str = "EURUSD",
    ) -> BacktestResult:
        """
        Run a backtest on historical candles and trade signals.

        Args:
            candles: OHLCV DataFrame (time, open, high, low, close, tick_volume, spread).
            signals: Entry instructions keyed by candle bar index.
            symbol: Symbol label attached to generated trades.

        Returns:
            BacktestResult with trades, equity curve, and metrics.
        """
        frame = self._prepare_candles(candles)
        ordered_signals = sorted(signals, key=lambda signal: signal.bar_index)
        self._validate_signals(ordered_signals, len(frame))

        balance = self.config.initial_balance
        open_trade: Trade | None = None
        closed_trades: list[Trade] = []
        equity_rows: list[dict[str, float | pd.Timestamp]] = []

        signals_by_bar: dict[int, list[TradeSignal]] = {}
        for signal in ordered_signals:
            signals_by_bar.setdefault(signal.bar_index, []).append(signal)

        for bar_index, row in frame.iterrows():
            bar_time = row["time"]
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])

            if open_trade is not None:
                open_trade, exit_trade = self._check_exit(open_trade, bar_time, high, low, close)
                if exit_trade is not None:
                    balance += exit_trade.pnl
                    closed_trades.append(exit_trade)
                    open_trade = None

            if open_trade is None and bar_index in signals_by_bar:
                for signal in signals_by_bar[bar_index]:
                    if open_trade is not None and not self.config.allow_multiple_positions:
                        break
                    open_trade = self._open_trade(signal, row, symbol)

            equity = balance
            if open_trade is not None:
                equity += self._unrealized_pnl(open_trade, close)

            equity_rows.append(
                {
                    "time": bar_time,
                    "balance": balance,
                    "equity": equity,
                }
            )

        if open_trade is not None:
            final_row = frame.iloc[-1]
            closed = self._close_trade(
                open_trade,
                final_row["time"],
                float(final_row["close"]),
                "close",
            )
            balance += closed.pnl
            closed_trades.append(closed)
            equity_rows[-1]["balance"] = balance
            equity_rows[-1]["equity"] = balance

        equity_curve = pd.DataFrame(equity_rows)
        metrics = self._calculate_metrics(
            initial_balance=self.config.initial_balance,
            final_balance=balance,
            trades=closed_trades,
            equity_curve=equity_curve,
        )

        logger.info(
            f"Backtest complete: {metrics.total_trades} trade(s), "
            f"return={metrics.total_return:.2%}, "
            f"max_drawdown={metrics.max_drawdown:.2%}"
        )

        return BacktestResult(
            trades=closed_trades,
            equity_curve=equity_curve,
            metrics=metrics,
        )

    def _prepare_candles(self, candles: pd.DataFrame) -> pd.DataFrame:
        if candles is None or candles.empty:
            raise BacktestError("Candle data is empty")

        frame = prepare_candles(candles)
        if frame.empty:
            raise BacktestError("No valid candles after cleaning")

        missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
        if missing:
            raise BacktestError(f"Candle data missing columns: {', '.join(missing)}")

        return frame.reset_index(drop=True)

    def _validate_signals(self, signals: list[TradeSignal], bar_count: int) -> None:
        for index, signal in enumerate(signals):
            if signal.bar_index < 0 or signal.bar_index >= bar_count:
                raise BacktestError(
                    f"Signal {index} bar_index {signal.bar_index} is out of range (0-{bar_count - 1})"
                )
            if signal.volume <= 0:
                raise BacktestError(f"Signal {index} volume must be positive")
            if signal.stop_loss is None and signal.take_profit is None:
                raise BacktestError(
                    f"Signal {index} must define stop_loss and/or take_profit"
                )

    def _spread_price(self, candle_spread: float) -> float:
        if candle_spread > 0:
            return float(candle_spread) * self.config.pip_size
        return self.config.spread_pips * self.config.pip_size

    def _entry_price(self, side: TradeSide, close: float, spread_price: float) -> float:
        half_spread = spread_price / 2.0
        if side == "buy":
            return close + half_spread
        return close - half_spread

    def _exit_price(self, side: TradeSide, price: float, spread_price: float) -> float:
        half_spread = spread_price / 2.0
        if side == "buy":
            return price - half_spread
        return price + half_spread

    def _open_trade(self, signal: TradeSignal, row: pd.Series, symbol: str) -> Trade:
        spread_price = self._spread_price(float(row["spread"]))
        entry_price = self._entry_price(signal.side, float(row["close"]), spread_price)
        return Trade(
            symbol=symbol,
            side=signal.side,
            volume=signal.volume,
            entry_time=row["time"],
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )

    def _check_exit(
        self,
        trade: Trade,
        bar_time: pd.Timestamp,
        high: float,
        low: float,
        close: float,
    ) -> tuple[Trade | None, Trade | None]:
        if trade.side == "buy":
            if trade.stop_loss is not None and low <= trade.stop_loss:
                return None, self._close_trade(trade, bar_time, trade.stop_loss, "stop_loss")
            if trade.take_profit is not None and high >= trade.take_profit:
                return None, self._close_trade(trade, bar_time, trade.take_profit, "take_profit")
        else:
            if trade.stop_loss is not None and high >= trade.stop_loss:
                return None, self._close_trade(trade, bar_time, trade.stop_loss, "stop_loss")
            if trade.take_profit is not None and low <= trade.take_profit:
                return None, self._close_trade(trade, bar_time, trade.take_profit, "take_profit")

        return trade, None

    def _close_trade(
        self,
        trade: Trade,
        exit_time: pd.Timestamp,
        raw_exit_price: float,
        reason: str,
    ) -> Trade:
        spread_price = self.config.spread_pips * self.config.pip_size
        exit_price = self._exit_price(trade.side, raw_exit_price, spread_price)
        pnl = self._realized_pnl(trade.side, trade.entry_price, exit_price, trade.volume)
        return replace(
            trade,
            exit_time=exit_time,
            exit_price=exit_price,
            pnl=pnl,
            exit_reason=reason,  # type: ignore[arg-type]
        )

    def _price_delta(self, side: TradeSide, entry: float, current: float) -> float:
        if side == "buy":
            return current - entry
        return entry - current

    def _realized_pnl(self, side: TradeSide, entry: float, exit_price: float, volume: float) -> float:
        delta = self._price_delta(side, entry, exit_price)
        return delta * volume * self.config.contract_size

    def _unrealized_pnl(self, trade: Trade, close: float) -> float:
        mark_price = close
        delta = self._price_delta(trade.side, trade.entry_price, mark_price)
        return delta * trade.volume * self.config.contract_size

    def _calculate_metrics(
        self,
        *,
        initial_balance: float,
        final_balance: float,
        trades: list[Trade],
        equity_curve: pd.DataFrame,
    ) -> BacktestMetrics:
        winners = [trade for trade in trades if trade.pnl > 0]
        losers = [trade for trade in trades if trade.pnl < 0]
        gross_profit = sum(trade.pnl for trade in winners)
        gross_loss = abs(sum(trade.pnl for trade in losers))

        total_trades = len(trades)
        win_rate = len(winners) / total_trades if total_trades else 0.0
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        total_return = (final_balance - initial_balance) / initial_balance
        max_drawdown = self._max_drawdown(equity_curve["equity"])

        return BacktestMetrics(
            initial_balance=initial_balance,
            final_balance=final_balance,
            total_return=total_return,
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            total_trades=total_trades,
            winning_trades=len(winners),
            losing_trades=len(losers),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
        )

    @staticmethod
    def _max_drawdown(equity: pd.Series) -> float:
        if equity.empty:
            return 0.0

        running_peak = equity.cummax()
        drawdown = (running_peak - equity) / running_peak.replace(0, pd.NA)
        return float(drawdown.max(skipna=True) or 0.0)
