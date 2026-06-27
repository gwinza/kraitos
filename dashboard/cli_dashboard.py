"""CLI command center for Kraitos runtime monitoring and controls."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from loguru import logger

from analytics.performance import PerformanceAnalyzer
from config.settings import KraitosConfig
from controls.emergency_stop import EmergencyStop
from controls.manual_override import ManualOverride
from controls.trading_gate import TradingGate
from core.signal_router import TradeSignal
from execution.paper_trader import PaperTrader
from logs.event_logger import KraitosEventLogger
from monitoring.error_reporter import ErrorReporter
from monitoring.health_monitor import HealthMonitor, HealthSnapshot
from validation.strategy_validator import ValidationResult


@dataclass(frozen=True)
class CommandCenterSnapshot:
    """Aggregated command center view."""

    mode: str
    account_balance: float
    equity: float
    drawdown_pct: float
    open_trades: int
    closed_trades: int
    latest_signal: str
    latest_reason: str
    emergency_stop_active: bool
    strategies_paused: bool
    validation_status: str
    live_trading_allowed: bool
    health: HealthSnapshot
    recent_errors: tuple[str, ...]


class CommandCenter:
    """Kraitos command center — status display, controls, and safety gates."""

    def __init__(
        self,
        *,
        project_root: Path,
        config: KraitosConfig,
        event_logger: KraitosEventLogger | None = None,
        paper_trader: PaperTrader | None = None,
        trading_gate: TradingGate | None = None,
        error_reporter: ErrorReporter | None = None,
    ) -> None:
        self.project_root = project_root
        self.config = config
        self.event_logger = event_logger
        self.paper_trader = paper_trader
        self.emergency_stop = EmergencyStop(project_root)
        self.manual_override = ManualOverride(project_root)
        self.error_reporter = error_reporter or ErrorReporter(
            project_root=project_root,
            event_logger=event_logger,
        )
        self.trading_gate = trading_gate or TradingGate(
            project_root=project_root,
            config=config,
            emergency_stop=self.emergency_stop,
            manual_override=self.manual_override,
            critical_errors=self.error_reporter.critical_errors,
        )
        self.health_monitor = HealthMonitor(
            project_root=project_root,
            config=config,
            trading_gate=self.trading_gate,
            error_reporter=self.error_reporter,
        )
        self._performance = PerformanceAnalyzer()
        self._latest_signals: list[TradeSignal] = []

    def launch(self) -> CommandCenterSnapshot:
        """Initialize and display the command center dashboard."""
        snapshot = self.collect_snapshot()
        rendered = self.render(snapshot)
        print(rendered)
        logger.info("Command center launched")
        if self.event_logger is not None:
            self.event_logger.system_event(
                "Command center launched",
                event_type="command_center",
                data={
                    "mode": snapshot.mode,
                    "validation_status": snapshot.validation_status,
                    "emergency_stop": snapshot.emergency_stop_active,
                    "paused": snapshot.strategies_paused,
                },
            )
        return snapshot

    def collect_snapshot(self) -> CommandCenterSnapshot:
        """Build the current command center snapshot."""
        account = self._account_state()
        validation = self.trading_gate.assess_validation()
        live_allowed, _ = self.trading_gate.live_allowed()
        latest_signal, latest_reason = self._latest_signal_info()
        recent_errors = tuple(
            str(item.get("message", ""))
            for item in self.error_reporter.recent_errors(limit=5)
            if item.get("message")
        )

        return CommandCenterSnapshot(
            mode=self._resolve_mode(validation, live_allowed),
            account_balance=account["balance"],
            equity=account["equity"],
            drawdown_pct=account["drawdown_pct"],
            open_trades=account["open_trades"],
            closed_trades=account["closed_trades"],
            latest_signal=latest_signal,
            latest_reason=latest_reason,
            emergency_stop_active=self.emergency_stop.is_active,
            strategies_paused=self.manual_override.is_paused,
            validation_status=validation.status,
            live_trading_allowed=live_allowed,
            health=self.health_monitor.evaluate(),
            recent_errors=recent_errors,
        )

    def render(self, snapshot: CommandCenterSnapshot | None = None) -> str:
        """Render a text dashboard."""
        view = snapshot or self.collect_snapshot()
        lines = [
            "=" * 72,
            "KRAITOS COMMAND CENTER",
            "=" * 72,
            f"Mode:                 {view.mode}",
            f"Validation:           {view.validation_status}",
            f"Live trading allowed: {view.live_trading_allowed}",
            f"Emergency stop:       {'ACTIVE' if view.emergency_stop_active else 'off'}",
            f"Strategies:           {'PAUSED' if view.strategies_paused else 'running'}",
            "",
            "ACCOUNT",
            "-" * 72,
            f"Balance:              ${view.account_balance:,.2f}",
            f"Equity:               ${view.equity:,.2f}",
            f"Drawdown:             {view.drawdown_pct:.2f}%",
            f"Open trades:          {view.open_trades}",
            f"Closed trades:        {view.closed_trades}",
            "",
            "LATEST SIGNAL",
            "-" * 72,
            f"Signal:               {view.latest_signal}",
            f"Reason:               {view.latest_reason}",
            "",
            "HEALTH",
            "-" * 72,
        ]
        for check in view.health.checks:
            mark = "OK" if check.healthy else "WARN"
            lines.append(f"  [{mark}] {check.name}: {check.detail}")

        if view.recent_errors:
            lines.extend(["", "RECENT ERRORS", "-" * 72])
            for error in view.recent_errors:
                lines.append(f"  - {error}")

        lines.append("=" * 72)
        return "\n".join(lines)

    def update_signals(self, signals: Sequence[TradeSignal]) -> None:
        """Store the latest pipeline signals for dashboard display."""
        self._latest_signals = list(signals)
        path = self.project_root / "logs" / "pipeline_signals.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([signal.to_dict() for signal in signals], indent=2),
            encoding="utf-8",
        )

    def trading_permitted(self) -> tuple[bool, str]:
        """Return whether the pipeline may execute trades."""
        return self.trading_gate.can_execute(
            live=self.trading_gate._live_execution_requested()
        )

    def activate_emergency_stop(self, reason: str = "Operator emergency stop") -> None:
        """Activate emergency stop and log the event."""
        self.emergency_stop.activate(reason)
        self.error_reporter.report(
            f"Emergency stop activated: {reason}",
            critical=True,
        )
        if self.event_logger is not None:
            self.event_logger.system_event(
                "Emergency stop activated",
                event_type="emergency_stop",
                data={"reason": reason},
            )

    def clear_emergency_stop(self) -> None:
        self.emergency_stop.clear()
        if self.event_logger is not None:
            self.event_logger.system_event(
                "Emergency stop cleared",
                event_type="emergency_stop",
            )

    def pause_strategies(self, reason: str = "Operator paused strategies") -> None:
        self.manual_override.pause(reason)
        if self.event_logger is not None:
            self.event_logger.system_event(
                "Strategies paused",
                event_type="manual_override",
                data={"reason": reason},
            )

    def resume_strategies(self) -> None:
        self.manual_override.resume()
        if self.event_logger is not None:
            self.event_logger.system_event(
                "Strategies resumed",
                event_type="manual_override",
            )

    def _resolve_mode(self, validation: ValidationResult, live_allowed: bool) -> str:
        command_mode = str(
            self.config.raw.get("command_center", {}).get("mode", "")
        ).strip().lower()
        if command_mode == "backtest":
            return "backtest"
        if live_allowed and validation.status == "LIVE_READY":
            return "live"
        if self.config.trading.paper_enabled or self.config.simulation_only:
            return "paper"
        return "live-disabled"

    def _account_state(self) -> dict[str, float | int]:
        if self.paper_trader is not None:
            snapshot = self.paper_trader.snapshot()
            balance = _as_float(getattr(snapshot, "balance", 0.0), self.config.account.balance)
            equity = _as_float(getattr(snapshot, "equity", balance), balance)
            initial = _as_float(
                getattr(snapshot, "initial_balance", self.config.account.balance),
                self.config.account.balance,
            )
            open_trades = getattr(snapshot, "open_trades", ()) or ()
            trade_history = getattr(snapshot, "trade_history", ()) or ()
            peak = max(initial, equity)
            drawdown = (
                max(0.0, (peak - equity) / peak * 100.0) if peak > 0 else 0.0
            )
            closed = max(0, len(trade_history) - len(open_trades))
            return {
                "balance": balance,
                "equity": equity,
                "drawdown_pct": drawdown,
                "open_trades": len(open_trades),
                "closed_trades": closed,
            }

        return self._account_state_from_logs()

    def _account_state_from_logs(self) -> dict[str, float | int]:
        initial = self.config.account.balance
        paper_path = self.project_root / "logs" / "paper_trades.csv"
        if not paper_path.exists():
            return {
                "balance": initial,
                "equity": initial,
                "drawdown_pct": 0.0,
                "open_trades": 0,
                "closed_trades": 0,
            }

        try:
            trades = self._performance.load_trades(paper_path)
            metrics = self._performance.analyze(trades, initial_balance=initial)
            balance = initial + metrics.net_profit
            equity = balance
            drawdown = metrics.max_drawdown * 100.0
            open_trades = 0
            import pandas as pd

            frame = pd.read_csv(paper_path)
            if not frame.empty and {"trade_id", "status"}.issubset(frame.columns):
                latest = frame.sort_values("event_time").groupby("trade_id").tail(1)
                open_trades = int(
                    (latest["status"].astype(str).str.lower() == "open").sum()
                )
            return {
                "balance": balance,
                "equity": equity,
                "drawdown_pct": drawdown,
                "open_trades": open_trades,
                "closed_trades": metrics.total_trades,
            }
        except Exception:
            return {
                "balance": initial,
                "equity": initial,
                "drawdown_pct": 0.0,
                "open_trades": 0,
                "closed_trades": 0,
            }

    def _latest_signal_info(self) -> tuple[str, str]:
        if self._latest_signals:
            signal = self._latest_signals[-1]
            return (
                f"{signal.symbol} {signal.decision} {signal.direction}",
                signal.reason,
            )

        path = self.project_root / "logs" / "pipeline_signals.json"
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload:
                    last = payload[-1]
                    return (
                        (
                            f"{last.get('symbol', '?')} "
                            f"{last.get('decision', '?')} "
                            f"{last.get('direction', 'none')}"
                        ),
                        str(last.get("reason", "")),
                    )
            except (json.JSONDecodeError, OSError):
                pass
        return "No signal yet", "Pipeline has not produced a signal"


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
