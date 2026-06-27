"""Trading safety gate — blocks execution unless all controls pass."""

from __future__ import annotations

from pathlib import Path

from backtesting.performance_report import PerformanceMetrics
from config.broker_settings import BrokerSettings
from config.settings import KraitosConfig
from controls.emergency_stop import EmergencyStop
from controls.manual_override import ManualOverride
from validation import ForwardTestTracker, LiveReadinessReport
from validation.strategy_validator import ValidationResult


class TradingGate:
    """Central gate for paper, backtest, and live execution paths."""

    def __init__(
        self,
        *,
        project_root: Path,
        config: KraitosConfig,
        emergency_stop: EmergencyStop | None = None,
        manual_override: ManualOverride | None = None,
        broker_settings: BrokerSettings | None = None,
        validation_result: ValidationResult | None = None,
        critical_errors: tuple[str, ...] = (),
    ) -> None:
        self.project_root = project_root
        self.config = config
        self.emergency_stop = emergency_stop or EmergencyStop(project_root)
        self.manual_override = manual_override or ManualOverride(project_root)
        self.broker_settings = broker_settings or BrokerSettings.from_env(
            config_raw=config.raw
        )
        self._validation_result = validation_result
        self._critical_errors = critical_errors

    def assess_validation(self) -> ValidationResult:
        """Evaluate strategy live-readiness from current tracker state."""
        if self._validation_result is not None:
            return self._validation_result

        tracker = ForwardTestTracker(strategy_name="kraitos")
        tracker.set_backtest_metrics(self._load_phase_metrics("backtest"))
        tracker.set_paper_metrics(self._load_phase_metrics("paper"))
        for error in self._critical_errors:
            tracker.record_critical_error(error)

        report = LiveReadinessReport()
        return report.assess(
            tracker,
            broker_settings=self.broker_settings,
        )

    def can_execute(self, *, live: bool = False) -> tuple[bool, str]:
        """
        Return whether trade execution is permitted.

        Paper/backtest paths still require emergency stop and pause checks.
        Live orders additionally require LIVE_READY and broker safety flags.
        """
        if self.emergency_stop.is_active:
            return False, f"Emergency stop active: {self.emergency_stop.reason}"
        if self.manual_override.is_paused:
            return False, f"Strategies paused: {self.manual_override.reason}"

        if live or self._live_execution_requested():
            allowed, reason = self.live_allowed()
            if not allowed:
                return False, reason
        return True, "ok"

    def live_allowed(self) -> tuple[bool, str]:
        """Return whether live broker orders may be placed."""
        if self.emergency_stop.is_active:
            return False, f"Emergency stop active: {self.emergency_stop.reason}"
        if self.manual_override.is_paused:
            return False, f"Strategies paused: {self.manual_override.reason}"

        if self.config.simulation_only or not self.config.trading.live_enabled:
            return False, "Live trading disabled by configuration"

        if not self.broker_settings.live_allowed:
            return (
                False,
                "Broker safety flags not approved "
                "(LIVE_TRADING and ENABLE_LIVE_TRADING required)",
            )

        if not self.broker_settings.broker_name:
            return False, "BROKER_NAME must be set for live trading"
        if not self.broker_settings.account_id:
            return False, "BROKER_ACCOUNT_ID must be set for live trading"
        if self.broker_settings.max_risk_per_trade_pct > 1.0:
            return False, "max_risk_per_trade must be <= 1%"
        if self.broker_settings.daily_drawdown_limit_pct > 5.0:
            return False, "daily_drawdown_limit must be <= 5%"

        validation = self.assess_validation()
        if validation.status != "LIVE_READY":
            return False, f"Validation status is {validation.status}, not LIVE_READY"

        return True, "Live trading approved by validation and safety flags"

    def _live_execution_requested(self) -> bool:
        return (
            self.config.trading.live_enabled
            and self.config.pipeline.execution_mode == "live"
            and not self.config.trading.paper_enabled
        )

    def _load_phase_metrics(self, phase: str) -> PerformanceMetrics:
        path = self.project_root / "logs" / "validation_metrics.json"
        if not path.exists():
            return _empty_metrics()

        import json

        try:
            with path.open(encoding="utf-8") as handle:
                raw = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return _empty_metrics()

        if phase == "backtest":
            phase_raw = raw.get("conservative_metrics") or raw.get("backtest", {})
        else:
            phase_raw = raw.get(phase, {})
        if not isinstance(phase_raw, dict):
            return _empty_metrics()
        return _metrics_from_dict(phase_raw)


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


def _metrics_from_dict(raw: dict) -> PerformanceMetrics:
    profit_factor_raw = raw.get("profit_factor", 0.0)
    if profit_factor_raw == "inf":
        profit_factor = float("inf")
    else:
        profit_factor = float(profit_factor_raw)

    return PerformanceMetrics(
        initial_balance=float(raw.get("initial_balance", 0.0)),
        final_balance=float(raw.get("final_balance", 0.0)),
        equity=float(raw.get("equity", 0.0)),
        total_return_pct=float(raw.get("total_return_pct", 0.0)),
        max_drawdown_pct=float(raw.get("max_drawdown_pct", 0.0)),
        daily_drawdown_pct=float(raw.get("daily_drawdown_pct", 0.0)),
        win_rate=float(raw.get("win_rate", 0.0)),
        profit_factor=profit_factor,
        average_r=float(raw.get("average_r", 0.0)),
        total_trades=int(raw.get("total_trades", 0)),
        winning_trades=int(raw.get("winning_trades", 0)),
        losing_trades=int(raw.get("losing_trades", 0)),
        gross_profit=float(raw.get("gross_profit", 0.0)),
        gross_loss=float(raw.get("gross_loss", 0.0)),
        daily_pnl=dict(raw.get("daily_pnl", {})),
        trading_disabled=bool(raw.get("trading_disabled", False)),
        trading_halted_daily=bool(raw.get("trading_halted_daily", False)),
    )
