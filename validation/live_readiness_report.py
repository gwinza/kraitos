"""Human-readable live readiness report for Kraitos strategy validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from config.broker_settings import BrokerSettings
from validation.forward_test_tracker import ForwardTestTracker
from validation.strategy_validator import (
    StrategyValidationInput,
    StrategyValidator,
    ValidationCriterion,
    ValidationResult,
    ValidationStatus,
)


@dataclass
class LiveReadinessReport:
    """Generate and render a detailed live-readiness assessment."""

    validator: StrategyValidator | None = None

    def assess(
        self,
        tracker: ForwardTestTracker,
        *,
        live_trading_enabled: bool | None = None,
        broker_settings: BrokerSettings | None = None,
    ) -> ValidationResult:
        """Validate tracker state and return the structured result."""
        snapshot = tracker.snapshot()
        enabled = live_trading_enabled
        if enabled is None:
            enabled = _live_trading_enabled(broker_settings)

        payload = StrategyValidationInput(
            strategy_name=tracker.strategy_name,
            backtest=snapshot.backtest,
            paper=snapshot.paper,
            critical_errors=tuple(snapshot.critical_errors),
            live_trading_enabled=enabled,
            trust_verdict=getattr(tracker, "_trust_verdict", "QUESTIONABLE"),
            data_quality_score=getattr(tracker, "_data_quality_score", 0.0),
        )
        validator = self.validator or StrategyValidator()
        return validator.validate(payload)

    def render(
        self,
        result: ValidationResult,
        *,
        generated_at: datetime | None = None,
    ) -> str:
        """Return a detailed text report explaining readiness."""
        moment = generated_at or datetime.now(timezone.utc)
        lines = [
            "=" * 60,
            "KRAITOS LIVE READINESS REPORT",
            "=" * 60,
            f"Strategy:          {result.strategy_name}",
            f"Generated:         {moment.isoformat()}",
            f"Status:            {result.status}",
            f"Backtest trades:   {result.backtest_trades}",
            f"Paper trades:      {result.paper_trades}",
            "",
            "SUMMARY",
            "-" * 60,
        ]

        if result.summary_reasons:
            lines.extend(f"- {reason}" for reason in result.summary_reasons)
        else:
            lines.append("- No summary reasons recorded.")

        lines.extend(["", "CRITERIA", "-" * 60])
        for phase in ("backtest", "paper", "system"):
            phase_checks = [c for c in result.criteria if c.phase == phase]
            if not phase_checks:
                continue
            lines.append(f"[{phase.upper()}]")
            for criterion in phase_checks:
                lines.append(self._format_criterion(criterion))
            lines.append("")

        if result.critical_errors:
            lines.extend(["CRITICAL ERRORS", "-" * 60])
            lines.extend(f"- {error}" for error in result.critical_errors)
            lines.append("")

        lines.extend(["LIVE TRADING GATE", "-" * 60])
        if result.status == "LIVE_READY":
            lines.append(
                "Strategy validation: PASSED — strategy meets LIVE_READY criteria."
            )
        else:
            lines.append(
                f"Strategy validation: NOT READY — current status is {result.status}."
            )

        if result.live_trading_enabled:
            lines.append(
                "System live trading flag: ENABLED (operator switches are on)."
            )
            if result.status == "LIVE_READY":
                lines.append(
                    "Strategy is validated, but broker confirmation guards "
                    "still apply before any real order is sent."
                )
            else:
                lines.append(
                    "WARNING: Strategy is not fully validated. "
                    "Live orders must remain blocked."
                )
        else:
            lines.append(
                "System live trading flag: DISABLED (default safe mode)."
            )
            lines.append(
                "No real orders will be placed regardless of validation status."
            )

        lines.extend(["", "NEXT STEPS", "-" * 60])
        lines.extend(self._next_steps(result))
        lines.append("=" * 60)
        return "\n".join(lines)

    def generate(
        self,
        tracker: ForwardTestTracker,
        *,
        live_trading_enabled: bool | None = None,
        broker_settings: BrokerSettings | None = None,
    ) -> tuple[ValidationResult, str]:
        """Validate and return both the structured result and rendered report."""
        result = self.assess(
            tracker,
            live_trading_enabled=live_trading_enabled,
            broker_settings=broker_settings,
        )
        return result, self.render(result)

    @staticmethod
    def _format_criterion(criterion: ValidationCriterion) -> str:
        mark = "PASS" if criterion.passed else "FAIL"
        detail = f" ({criterion.message})" if criterion.message else ""
        return (
            f"  [{mark}] {criterion.name}: "
            f"required {criterion.required}, actual {criterion.actual}{detail}"
        )

    @staticmethod
    def _next_steps(result: ValidationResult) -> list[str]:
        if result.status == "LIVE_READY":
            return [
                "Review broker confirmation guard settings before enabling live trading.",
                "Keep LIVE_TRADING and ENABLE_LIVE_TRADING false until operator sign-off.",
                "Run a final paper session to confirm live-market conditions.",
            ]
        if result.status == "APPROVED_FOR_PAPER_ONLY":
            return [
                "Continue paper/forward testing until at least 30 closed paper trades.",
                "Monitor daily drawdown and halt rules during forward testing.",
                "Re-run validation after paper sample size is sufficient.",
            ]
        if result.status == "NEEDS_MORE_DATA":
            return [
                "Collect more conservative backtest trades (minimum 500 closed trades required).",
                "Ensure journal and performance metrics are being recorded.",
                "Re-run validation once trade history thresholds are met.",
            ]
        return [
            "Do not enable live trading.",
            "Review failed criteria and critical errors in the report above.",
            "Adjust strategy parameters or risk limits, then re-validate.",
        ]


def _live_trading_enabled(broker_settings: BrokerSettings | None) -> bool:
    if broker_settings is None:
        return False
    return broker_settings.live_allowed
