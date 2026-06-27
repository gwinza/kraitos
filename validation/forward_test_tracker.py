"""Track forward/paper test progress for strategy validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backtesting.performance_report import PerformanceMetrics, PerformanceReport
from paper_trading.virtual_account import VirtualAccount


@dataclass
class ForwardTestSnapshot:
    """Point-in-time view of validation progress."""

    strategy_name: str
    captured_at: datetime
    backtest: PerformanceMetrics
    paper: PerformanceMetrics
    critical_errors: list[str] = field(default_factory=list)
    backtest_trades: int = 0
    paper_trades: int = 0

    @property
    def total_trades(self) -> int:
        return self.backtest_trades + self.paper_trades


class ForwardTestTracker:
    """
    Maintain separate backtest and paper metric streams for validation.

    Backtest metrics typically come from historical replay.
    Paper metrics come from ongoing forward testing on a virtual account.
    """

    def __init__(self, strategy_name: str = "default") -> None:
        self.strategy_name = strategy_name
        self._backtest_account: VirtualAccount | None = None
        self._paper_account: VirtualAccount | None = None
        self._backtest_metrics: PerformanceMetrics | None = None
        self._paper_metrics: PerformanceMetrics | None = None
        self._critical_errors: list[str] = []
        self._trust_verdict: str = "QUESTIONABLE"
        self._data_quality_score: float = 0.0

    def set_backtest_account(self, account: VirtualAccount) -> None:
        """Attach the virtual account used during backtest replay."""
        self._backtest_account = account
        self._backtest_metrics = None

    def set_paper_account(self, account: VirtualAccount) -> None:
        """Attach the virtual account used during forward/paper testing."""
        self._paper_account = account
        self._paper_metrics = None

    def set_backtest_metrics(self, metrics: PerformanceMetrics) -> None:
        """Attach pre-computed backtest metrics."""
        self._backtest_metrics = metrics

    def set_paper_metrics(self, metrics: PerformanceMetrics) -> None:
        """Attach pre-computed paper metrics."""
        self._paper_metrics = metrics

    def set_trust_verdict(self, verdict: str) -> None:
        """Attach conservative backtest trust rating."""
        self._trust_verdict = verdict.strip().upper() or "QUESTIONABLE"

    def set_data_quality_score(self, score: float) -> None:
        """Attach data quality score from validation."""
        self._data_quality_score = float(score)

    def record_critical_error(self, message: str) -> None:
        """Record a critical system error that blocks live readiness."""
        cleaned = message.strip()
        if cleaned and cleaned not in self._critical_errors:
            self._critical_errors.append(cleaned)

    def clear_critical_errors(self) -> None:
        """Clear recorded critical errors."""
        self._critical_errors.clear()

    def backtest_metrics(self) -> PerformanceMetrics:
        """Return metrics for the backtest phase."""
        if self._backtest_metrics is not None:
            return self._backtest_metrics
        if self._backtest_account is not None:
            return PerformanceReport(self._backtest_account).metrics()
        return _empty_metrics()

    def paper_metrics(self) -> PerformanceMetrics:
        """Return metrics for the paper/forward-test phase."""
        if self._paper_metrics is not None:
            return self._paper_metrics
        if self._paper_account is not None:
            return PerformanceReport(self._paper_account).metrics()
        return _empty_metrics()

    def snapshot(self) -> ForwardTestSnapshot:
        """Capture current validation progress."""
        backtest = self.backtest_metrics()
        paper = self.paper_metrics()
        return ForwardTestSnapshot(
            strategy_name=self.strategy_name,
            captured_at=datetime.now(timezone.utc),
            backtest=backtest,
            paper=paper,
            critical_errors=list(self._critical_errors),
            backtest_trades=backtest.total_trades,
            paper_trades=paper.total_trades,
        )

    @property
    def critical_errors(self) -> tuple[str, ...]:
        return tuple(self._critical_errors)


def _empty_metrics() -> PerformanceMetrics:
    return PerformanceMetrics(
        initial_balance=0.0,
        final_balance=0.0,
        equity=0.0,
        total_return_pct=0.0,
        max_drawdown_pct=0.0,
        daily_drawdown_pct=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        average_r=0.0,
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        gross_profit=0.0,
        gross_loss=0.0,
        daily_pnl={},
        trading_disabled=False,
        trading_halted_daily=False,
    )
