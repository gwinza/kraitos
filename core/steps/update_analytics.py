"""Step 14: Update analytics and dashboard state."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from loguru import logger

from analytics.performance import PerformanceError
from core.models import SymbolCycleState
from core.runtime import KraitosRuntime


def update_analytics(
    runtime: KraitosRuntime,
    *,
    trace_id: str,
    states: list[SymbolCycleState],
) -> None:
    """Refresh performance metrics, pair specialisation, and dashboard state."""
    logs_dir = runtime.project_root / "logs"
    metrics_path = logs_dir / "performance_metrics.json"
    dashboard_path = logs_dir / "dashboard_state.json"

    try:
        metrics = runtime.performance_analyzer.from_default_logs(
            initial_balance=runtime.config.account.balance,
        )
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        with metrics_path.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "total_trades": metrics.total_trades,
                    "win_rate": metrics.win_rate,
                    "profit_factor": metrics.profit_factor,
                    "net_profit": metrics.net_profit,
                    "max_drawdown": metrics.max_drawdown,
                    "best_symbol": metrics.best_symbol,
                    "worst_symbol": metrics.worst_symbol,
                },
                handle,
                indent=2,
            )
        logger.info(f"Performance metrics saved to {metrics_path}")
    except PerformanceError:
        logger.debug("No closed trades yet; skipping performance metrics update")

    try:
        trades = []
        for path in (
            logs_dir / "paper_trades.csv",
            logs_dir / "csv" / "executed_trades.csv",
            logs_dir / "json" / "executed_trades.jsonl",
        ):
            if path.exists():
                trades.extend(runtime.performance_analyzer.load_trades(path))
        runtime.pair_analyzer.analyze_and_save(
            trades,
            symbols=list(runtime.config.trading.symbols),
            output_path=logs_dir / "pair_specialisation.json",
        )
    except Exception as exc:
        runtime.event_logger.error(
            "Pair specialisation update failed",
            trace_id=trace_id,
            exc=exc,
        )

    primary = _primary_regime_state(states)
    dashboard_payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "regime": primary.get("regime", "unclear"),
        "regime_confidence": primary.get("confidence", 0.0),
        "regime_reason": primary.get("reason", "No regime data"),
        "symbols": {
            state.symbol: {
                "regime": state.regime.regime if state.regime else None,
                "bias": state.bias.bias if state.bias else None,
                "harvest_mode": state.harvest.mode if state.harvest else None,
                "entry_action": state.entry.action if state.entry else None,
            }
            for state in states
        },
    }
    dashboard_path.parent.mkdir(parents=True, exist_ok=True)
    with dashboard_path.open("w", encoding="utf-8") as handle:
        json.dump(dashboard_payload, handle, indent=2)
    logger.info(f"Dashboard state saved to {dashboard_path}")

    runtime.event_logger.system_event(
        "Analytics updated",
        event_type="analytics_updated",
        trace_id=trace_id,
        data={"dashboard_state": str(dashboard_path), "metrics_path": str(metrics_path)},
    )


def _primary_regime_state(states: list[SymbolCycleState]) -> dict[str, object]:
    """Pick the highest-confidence regime from the cycle for dashboard display."""
    candidates = [state for state in states if state.regime is not None]
    if not candidates:
        return {}
    best = max(candidates, key=lambda state: state.regime.confidence)  # type: ignore[union-attr]
    return {
        "regime": best.regime.regime,
        "confidence": best.regime.confidence,
        "reason": best.regime.reason,
    }
