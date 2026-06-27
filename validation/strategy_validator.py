"""Strategy validation gate — determines paper/live readiness from backtest and forward tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from backtesting.performance_report import PerformanceMetrics

ValidationStatus = Literal[
    "APPROVED_FOR_PAPER_ONLY",
    "NEEDS_MORE_DATA",
    "FAILED_VALIDATION",
    "LIVE_READY",
]


@dataclass(frozen=True)
class ValidationThresholds:
    """Minimum requirements for marking a strategy LIVE_READY."""

    min_backtest_trades: int = 500
    min_paper_trades: int = 30
    min_win_rate: float = 0.52
    min_profit_factor: float = 1.3
    max_drawdown_pct: float = 15.0
    min_average_r: float = 0.0  # must be strictly greater than zero


@dataclass(frozen=True)
class ValidationCriterion:
    """One evaluated readiness check."""

    name: str
    phase: str
    required: str
    actual: str
    passed: bool
    message: str = ""


@dataclass
class StrategyValidationInput:
    """Metrics and system state used by the validator."""

    strategy_name: str = "default"
    backtest: PerformanceMetrics | None = None
    paper: PerformanceMetrics | None = None
    critical_errors: tuple[str, ...] = ()
    live_trading_enabled: bool = False
    trust_verdict: str = "QUESTIONABLE"
    data_quality_score: float = 0.0


@dataclass
class ValidationResult:
    """Outcome of strategy validation with per-criterion detail."""

    status: ValidationStatus
    strategy_name: str
    criteria: list[ValidationCriterion] = field(default_factory=list)
    critical_errors: list[str] = field(default_factory=list)
    live_trading_enabled: bool = False
    summary_reasons: list[str] = field(default_factory=list)
    backtest_trades: int = 0
    paper_trades: int = 0

    @property
    def live_ready(self) -> bool:
        return self.status == "LIVE_READY"

    @property
    def all_criteria_passed(self) -> bool:
        return all(criterion.passed for criterion in self.criteria)


class StrategyValidator:
    """Evaluate whether a strategy meets Kraitos live-readiness requirements."""

    def __init__(self, thresholds: ValidationThresholds | None = None) -> None:
        self.thresholds = thresholds or ValidationThresholds()

    def validate(self, data: StrategyValidationInput) -> ValidationResult:
        """Run all validation checks and return a structured result."""
        backtest = data.backtest or _empty_metrics()
        paper = data.paper or _empty_metrics()
        criteria: list[ValidationCriterion] = []

        criteria.extend(self._trade_count_checks(backtest, paper))
        criteria.extend(self._phase_quality_checks("backtest", backtest))
        criteria.extend(self._phase_quality_checks("paper", paper))
        criteria.extend(self._system_checks(backtest, paper, data.critical_errors))
        criteria.append(self._trust_verdict_check(data.trust_verdict))

        result = ValidationResult(
            status="NEEDS_MORE_DATA",
            strategy_name=data.strategy_name,
            criteria=criteria,
            critical_errors=list(data.critical_errors),
            live_trading_enabled=data.live_trading_enabled,
            backtest_trades=backtest.total_trades,
            paper_trades=paper.total_trades,
        )
        result.status = self._resolve_status(result, backtest, paper)
        result.summary_reasons = self._build_summary_reasons(result)
        return result

    def _trade_count_checks(
        self,
        backtest: PerformanceMetrics,
        paper: PerformanceMetrics,
    ) -> list[ValidationCriterion]:
        thresholds = self.thresholds
        return [
            ValidationCriterion(
                name="backtest_trade_count",
                phase="backtest",
                required=f">= {thresholds.min_backtest_trades}",
                actual=str(backtest.total_trades),
                passed=backtest.total_trades >= thresholds.min_backtest_trades,
                message="Minimum conservative backtest trades collected",
            ),
            ValidationCriterion(
                name="paper_trade_count",
                phase="paper",
                required=f">= {thresholds.min_paper_trades}",
                actual=str(paper.total_trades),
                passed=paper.total_trades >= thresholds.min_paper_trades,
                message="Minimum forward/paper trades collected",
            ),
        ]

    def _phase_quality_checks(
        self,
        phase: str,
        metrics: PerformanceMetrics,
    ) -> list[ValidationCriterion]:
        thresholds = self.thresholds
        pf_actual = _format_profit_factor(metrics.profit_factor)
        pf_passed = _profit_factor_passes(metrics.profit_factor, thresholds.min_profit_factor)

        return [
            ValidationCriterion(
                name="win_rate",
                phase=phase,
                required=f">= {thresholds.min_win_rate:.0%}",
                actual=f"{metrics.win_rate:.1%}",
                passed=metrics.win_rate >= thresholds.min_win_rate,
                message="Win rate meets minimum edge threshold",
            ),
            ValidationCriterion(
                name="profit_factor",
                phase=phase,
                required=f">= {thresholds.min_profit_factor:.1f}",
                actual=pf_actual,
                passed=pf_passed,
                message="Profit factor meets minimum threshold",
            ),
            ValidationCriterion(
                name="max_drawdown",
                phase=phase,
                required=f"<= {thresholds.max_drawdown_pct:.0f}%",
                actual=f"{metrics.max_drawdown_pct:.2f}%",
                passed=metrics.max_drawdown_pct <= thresholds.max_drawdown_pct,
                message="Maximum drawdown within safety limit",
            ),
            ValidationCriterion(
                name="average_r",
                phase=phase,
                required=f"> {thresholds.min_average_r:.1f}R",
                actual=f"{metrics.average_r:+.2f}R",
                passed=metrics.average_r > thresholds.min_average_r,
                message="Average R-multiple is positive",
            ),
            ValidationCriterion(
                name="daily_drawdown_breach",
                phase=phase,
                required="no breach",
                actual="breach" if metrics.trading_halted_daily else "ok",
                passed=not metrics.trading_halted_daily,
                message="No daily drawdown safety breach during phase",
            ),
        ]

    def _trust_verdict_check(self, trust_verdict: str) -> ValidationCriterion:
        normalized = (trust_verdict or "QUESTIONABLE").upper()
        return ValidationCriterion(
            name="trust_verdict",
            phase="backtest",
            required="TRUSTWORTHY",
            actual=normalized,
            passed=normalized == "TRUSTWORTHY",
            message="Conservative backtest trust rating from red-team audit",
        )

    def _system_checks(
        self,
        backtest: PerformanceMetrics,
        paper: PerformanceMetrics,
        critical_errors: tuple[str, ...],
    ) -> list[ValidationCriterion]:
        has_errors = bool(critical_errors)
        return [
            ValidationCriterion(
                name="critical_system_errors",
                phase="system",
                required="none",
                actual=str(len(critical_errors)),
                passed=not has_errors,
                message="No critical system errors recorded",
            ),
            ValidationCriterion(
                name="total_drawdown_halt",
                phase="system",
                required="no halt",
                actual=(
                    "halted"
                    if backtest.trading_disabled or paper.trading_disabled
                    else "ok"
                ),
                passed=not backtest.trading_disabled and not paper.trading_disabled,
                message="No total drawdown safety halt triggered",
            ),
        ]

    def _resolve_status(
        self,
        result: ValidationResult,
        backtest: PerformanceMetrics,
        paper: PerformanceMetrics,
    ) -> ValidationStatus:
        thresholds = self.thresholds

        if result.critical_errors:
            return "FAILED_VALIDATION"

        backtest_count_ok = backtest.total_trades >= thresholds.min_backtest_trades
        paper_count_ok = paper.total_trades >= thresholds.min_paper_trades

        if not backtest_count_ok:
            return "NEEDS_MORE_DATA"

        trust_check = next(
            (criterion for criterion in result.criteria if criterion.name == "trust_verdict"),
            None,
        )
        if trust_check is not None and not trust_check.passed:
            return "FAILED_VALIDATION"

        system_failed = any(
            not criterion.passed
            for criterion in result.criteria
            if criterion.phase == "system"
        )
        if system_failed:
            return "FAILED_VALIDATION"

        backtest_quality_ok = backtest_count_ok and _phase_passes(
            result.criteria,
            phase="backtest",
            exclude={"backtest_trade_count"},
        )
        paper_quality_ok = paper_count_ok and _phase_passes(
            result.criteria,
            phase="paper",
            exclude={"paper_trade_count"},
        )

        if not backtest_quality_ok:
            return "FAILED_VALIDATION"

        if not paper_count_ok:
            return "APPROVED_FOR_PAPER_ONLY"

        if not paper_quality_ok:
            return "FAILED_VALIDATION"

        return "LIVE_READY"

    def _build_summary_reasons(self, result: ValidationResult) -> list[str]:
        reasons: list[str] = []

        if result.status == "LIVE_READY":
            reasons.append(
                "All backtest and paper validation criteria passed. "
                "Strategy is marked LIVE_READY."
            )
            if not result.live_trading_enabled:
                reasons.append(
                    "System live trading remains DISABLED by configuration. "
                    "Explicit operator approval is still required."
                )
            return reasons

        if result.status == "APPROVED_FOR_PAPER_ONLY":
            reasons.append(
                "Backtest validation passed. Continue forward/paper testing "
                "until minimum paper trade count and metrics are met."
            )
            failed = [c for c in result.criteria if not c.passed]
            for criterion in failed:
                reasons.append(
                    f"{criterion.phase}.{criterion.name}: "
                    f"required {criterion.required}, got {criterion.actual}"
                )
            return reasons

        if result.status == "NEEDS_MORE_DATA":
            reasons.append("Insufficient trade history to complete validation.")
            for criterion in result.criteria:
                if not criterion.passed and criterion.name.endswith("_trade_count"):
                    reasons.append(
                        f"{criterion.phase}: required {criterion.required}, "
                        f"got {criterion.actual}"
                    )
            return reasons

        reasons.append("Validation failed one or more quality or safety checks.")
        if result.critical_errors:
            reasons.append(f"Critical errors: {', '.join(result.critical_errors)}")
        for criterion in result.criteria:
            if not criterion.passed:
                reasons.append(
                    f"{criterion.phase}.{criterion.name}: "
                    f"required {criterion.required}, got {criterion.actual}"
                )
        return reasons


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


def _phase_passes(
    criteria: list[ValidationCriterion],
    *,
    phase: str,
    exclude: set[str],
) -> bool:
    return all(
        criterion.passed
        for criterion in criteria
        if criterion.phase == phase and criterion.name not in exclude
    )


def _profit_factor_passes(value: float, minimum: float) -> bool:
    if value == float("inf"):
        return True
    return value >= minimum


def _format_profit_factor(value: float) -> str:
    if value == float("inf"):
        return "inf"
    return f"{value:.2f}"
