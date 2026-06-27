"""Readable performance summaries for validation and backtest runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from paper_trading.virtual_account import TradeJournalEntry, VirtualAccount


@dataclass(frozen=True)
class PerformanceMetrics:
    """Aggregated performance statistics."""

    initial_balance: float
    final_balance: float
    equity: float
    total_return_pct: float
    max_drawdown_pct: float
    daily_drawdown_pct: float
    win_rate: float
    profit_factor: float
    average_r: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    gross_profit: float
    gross_loss: float
    daily_pnl: dict[str, float]
    trading_disabled: bool
    trading_halted_daily: bool


class PerformanceReport:
    """Build metrics and human-readable summaries from journal data."""

    def __init__(self, account: VirtualAccount) -> None:
        self.account = account

    def metrics(self) -> PerformanceMetrics:
        closed = self._closed_trades()
        winners = [trade for trade in closed if trade.profit_loss > 0]
        losers = [trade for trade in closed if trade.profit_loss < 0]
        gross_profit = sum(trade.profit_loss for trade in winners)
        gross_loss = abs(sum(trade.profit_loss for trade in losers))

        total = len(closed)
        win_rate = len(winners) / total if total else 0.0
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        from validation.r_metrics import trade_r_multiple

        r_values = [trade_r_multiple(trade.to_row()) for trade in closed]
        average_r = sum(r_values) / len(r_values) if r_values else 0.0

        initial = self.account.config.initial_balance
        final = self.account.balance
        total_return = ((final - initial) / initial * 100.0) if initial else 0.0

        return PerformanceMetrics(
            initial_balance=initial,
            final_balance=final,
            equity=self.account.equity,
            total_return_pct=total_return,
            max_drawdown_pct=self.account.total_drawdown_pct,
            daily_drawdown_pct=self.account.daily_drawdown_pct,
            win_rate=win_rate,
            profit_factor=profit_factor,
            average_r=average_r,
            total_trades=total,
            winning_trades=len(winners),
            losing_trades=len(losers),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            daily_pnl=dict(self.account.daily_pnl),
            trading_disabled=self.account.trading_disabled,
            trading_halted_daily=self.account.trading_halted_daily,
        )

    def render(self) -> str:
        """Return a readable text summary."""
        metrics = self.metrics()
        lines = [
            "=== Kraitos Validation Performance ===",
            f"Initial balance:     ${metrics.initial_balance:,.2f}",
            f"Final balance:       ${metrics.final_balance:,.2f}",
            f"Equity:              ${metrics.equity:,.2f}",
            f"Total return:        {metrics.total_return_pct:+.2f}%",
            f"Max drawdown:        {metrics.max_drawdown_pct:.2f}%",
            f"Daily drawdown:      {metrics.daily_drawdown_pct:.2f}%",
            f"Total trades:        {metrics.total_trades}",
            f"Win rate:            {metrics.win_rate:.1%}",
            f"Profit factor:       {self._format_profit_factor(metrics.profit_factor)}",
            f"Average R:           {metrics.average_r:+.2f}R",
            f"Gross profit:        ${metrics.gross_profit:,.2f}",
            f"Gross loss:          ${metrics.gross_loss:,.2f}",
        ]

        if metrics.daily_pnl:
            lines.append("Daily P/L:")
            for day, pnl in sorted(metrics.daily_pnl.items()):
                lines.append(f"  {day}: ${pnl:+,.2f}")

        if metrics.trading_disabled:
            lines.append("Safety: TRADING DISABLED (total drawdown > 15%)")
        elif metrics.trading_halted_daily:
            lines.append("Safety: HALTED FOR TODAY (daily drawdown > 5%)")
        else:
            lines.append("Safety: ACTIVE")

        return "\n".join(lines)

    def print_summary(self) -> str:
        """Print and return the performance summary."""
        summary = self.render()
        print(summary)
        return summary

    def _closed_trades(self) -> Iterable[TradeJournalEntry]:
        return [
            entry
            for entry in self.account.closed_entries
            if entry.result in {"win", "loss", "breakeven"}
        ]

    @staticmethod
    def _format_profit_factor(value: float) -> str:
        if value == float("inf"):
            return "inf"
        return f"{value:.2f}"
