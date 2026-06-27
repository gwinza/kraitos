"""Health checks for the Kraitos command center."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from config.settings import KraitosConfig
from controls.emergency_stop import EmergencyStop
from controls.manual_override import ManualOverride
from controls.trading_gate import TradingGate
from monitoring.error_reporter import ErrorReporter


@dataclass(frozen=True)
class HealthCheck:
    """One health monitor result."""

    name: str
    healthy: bool
    detail: str


@dataclass
class HealthSnapshot:
    """Aggregated health status."""

    healthy: bool
    checks: list[HealthCheck] = field(default_factory=list)


class HealthMonitor:
    """Evaluate runtime health for dashboard display."""

    def __init__(
        self,
        *,
        project_root: Path,
        config: KraitosConfig,
        trading_gate: TradingGate,
        error_reporter: ErrorReporter,
    ) -> None:
        self.project_root = project_root
        self.config = config
        self.trading_gate = trading_gate
        self.error_reporter = error_reporter
        self.emergency_stop = trading_gate.emergency_stop
        self.manual_override = trading_gate.manual_override

    def evaluate(self) -> HealthSnapshot:
        checks = [
            self._config_check(),
            self._emergency_stop_check(),
            self._override_check(),
            self._validation_check(),
            self._error_check(),
            self._logs_check(),
        ]
        return HealthSnapshot(
            healthy=all(check.healthy for check in checks),
            checks=checks,
        )

    def _config_check(self) -> HealthCheck:
        config_path = self.project_root / "config" / "config.yaml"
        healthy = config_path.exists()
        return HealthCheck(
            name="configuration",
            healthy=healthy,
            detail="config/config.yaml present" if healthy else "config missing",
        )

    def _emergency_stop_check(self) -> HealthCheck:
        if self.emergency_stop.is_active:
            return HealthCheck(
                name="emergency_stop",
                healthy=False,
                detail=f"ACTIVE: {self.emergency_stop.reason}",
            )
        return HealthCheck(
            name="emergency_stop",
            healthy=True,
            detail="inactive",
        )

    def _override_check(self) -> HealthCheck:
        if self.manual_override.is_paused:
            return HealthCheck(
                name="manual_override",
                healthy=True,
                detail=f"paused: {self.manual_override.reason}",
            )
        return HealthCheck(
            name="manual_override",
            healthy=True,
            detail="running",
        )

    def _validation_check(self) -> HealthCheck:
        validation = self.trading_gate.assess_validation()
        healthy = validation.status in {"LIVE_READY", "APPROVED_FOR_PAPER_ONLY"}
        return HealthCheck(
            name="validation",
            healthy=healthy,
            detail=f"status={validation.status}",
        )

    def _error_check(self) -> HealthCheck:
        recent = self.error_reporter.recent_errors(limit=1)
        critical = bool(self.error_reporter.critical_errors)
        healthy = not critical
        detail = "no critical errors"
        if critical:
            detail = self.error_reporter.critical_errors[-1]
        elif recent:
            detail = str(recent[0].get("message", "recent error logged"))
        return HealthCheck(
            name="errors",
            healthy=healthy,
            detail=detail,
        )

    def _logs_check(self) -> HealthCheck:
        logs_dir = self.project_root / "logs"
        healthy = logs_dir.exists()
        return HealthCheck(
            name="logs",
            healthy=healthy,
            detail="logs directory available" if healthy else "logs directory missing",
        )
