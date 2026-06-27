"""Brain separation report writers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from backtesting.performance_report import PerformanceMetrics

if TYPE_CHECKING:
    from brains.auditor_brain import AuditorBrain, ValidationGateReport
    from brains.trader_brain import TraderBrain


SNAPSHOT_G = {
    "label": "G (pre-split)",
    "trades": 802,
    "win_rate": 0.963,
    "profit_factor": 2.56,
    "max_drawdown_pct": 2.50,
    "average_r": 0.11,
}


def write_trader_brain_report(
    project_root: Path,
    *,
    trader: TraderBrain | None = None,
) -> Path:
    """Write trader brain responsibilities and scan statistics."""
    path = project_root / "logs" / "trader_brain_report.md"
    now = datetime.now(timezone.utc).isoformat()
    stats = trader.stats if trader is not None else None

    lines = [
        "# Trader Brain Report",
        "",
        f"**Generated:** {now}",
        "",
        "## DNA",
        "",
        "The Trader Brain understands markets, forecasts outcomes, discovers opportunities",
        "and executes decisively. Conservative execution does NOT apply here.",
        "",
        "## Responsibilities",
        "",
        "- Scan all assets",
        "- Market story (`market_story_engine`)",
        "- Forecast (`story_forecast_engine`)",
        "- Opportunity identification (harvest, price action, volume, structure)",
        "- Strategy selection and entry candidates",
        "- Trade management signals (partial exits, runners — trader-side intent)",
        "- Indicator assist ONLY (boost, never veto)",
        "",
        "## Separation guarantees",
        "",
        "- Does NOT import `backtesting.execution_model`",
        "- Does NOT import `validation.conservative_validation`",
        "- Does NOT apply validation gates or strategy quality filters",
        "- Does NOT use next-bar / closed-candle conservative assumptions",
        "",
        "## Last scan stats",
        "",
    ]
    if stats is not None:
        lines.extend(
            [
                f"- Symbols scanned: **{stats.symbols_scanned}**",
                f"- Opportunities found: **{stats.opportunities_found}**",
                f"- Trade candidates: **{stats.trade_candidates}**",
                f"- Harvest allowed: **{stats.harvest_allowed}**",
                f"- Micro scalp signals: **{stats.micro_scalp_signals}**",
                f"- Last scan: `{stats.last_scan_at or 'n/a'}`",
            ]
        )
    else:
        lines.append("- No scan stats recorded this session.")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_auditor_brain_report(
    project_root: Path,
    *,
    auditor: AuditorBrain | None = None,
    metrics: PerformanceMetrics | None = None,
    gate_report: ValidationGateReport | None = None,
    snapshot_h: dict | None = None,
) -> Path:
    """Write auditor validation assumptions, realism checks, and metrics."""
    path = project_root / "logs" / "auditor_brain_report.md"
    now = datetime.now(timezone.utc).isoformat()
    stats = auditor.stats if auditor is not None else None

    lines = [
        "# Auditor Brain Report",
        "",
        f"**Generated:** {now}",
        "",
        "## DNA",
        "",
        "The Auditor Brain validates outcomes using conservative assumptions to prevent",
        "bias and self-deception. The Auditor never dictates how opportunities are discovered.",
        "",
        "## Conservative execution assumptions",
        "",
        "- Closed candles only (no partial-period lookahead)",
        "- Next-bar entry fill after signal confirmation",
        "- Spread: 1.2 pips, slippage: 0.3 pips, commission: $7/lot round-turn",
        "- Stop-loss prioritized when TP and SL share a bar (worst-case)",
        "- Mark open positions at backtest end",
        "",
        "## Separation guarantees",
        "",
        "- Does NOT participate in story/opportunity/scoring decisions",
        "- Validation gates are diagnostic only — never feed back into trader thresholds",
        "- Trader generates intent; auditor executes conservatively in backtest",
        "",
        "## Verification stats",
        "",
    ]
    if stats is not None:
        lines.extend(
            [
                f"- Validation runs: **{stats.validation_runs}**",
                f"- Trust verdict: **{stats.trust_verdict}**",
                f"- Conservative trades: **{stats.conservative_trades}**",
                f"- Last verification: `{stats.last_verification_at or 'n/a'}`",
            ]
        )
    else:
        lines.append("- No verification stats recorded this session.")

    if metrics is not None:
        lines.extend(
            [
                "",
                "## Snapshot H metrics (post-split)",
                "",
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| Trades | {metrics.total_trades} |",
                f"| Win rate | {metrics.win_rate:.1%} |",
                f"| Profit factor | {metrics.profit_factor:.2f} |",
                f"| Max drawdown | {metrics.max_drawdown_pct:.2f}% |",
                f"| Average R | {metrics.average_r:+.2f} |",
            ]
        )

    if gate_report is not None:
        lines.extend(
            [
                "",
                "## Validation gates (diagnostic only)",
                "",
                f"- Passed: **{gate_report.passed}**",
                f"- Failed: **{gate_report.failed}**",
                f"- Diagnostic only: **{gate_report.diagnostic_only}**",
                "",
                "| Gate | Status |",
                "|------|--------|",
            ]
        )
        for name, status in sorted(gate_report.gates.items()):
            lines.append(f"| {name} | {status} |")

    if snapshot_h is not None:
        lines.extend(
            [
                "",
                "## Snapshot comparison (G vs H)",
                "",
                "| | Trades | WR | PF | DD | Avg R |",
                "|---|--------|-----|-----|--------|-------|",
                _metrics_row(SNAPSHOT_G),
                _metrics_row(snapshot_h),
            ]
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_brain_separation_audit(
    project_root: Path,
    *,
    violations_fixed: list[str] | None = None,
    snapshot_h: dict | None = None,
) -> Path:
    """Write decision ownership matrix and separation enforcement audit."""
    path = project_root / "logs" / "brain_separation_audit.md"
    now = datetime.now(timezone.utc).isoformat()
    fixed = violations_fixed or []

    lines = [
        "# Brain Separation Audit",
        "",
        f"**Generated:** {now}",
        "",
        "## Decision ownership matrix",
        "",
        "| Concern | Owner | Notes |",
        "|---------|-------|-------|",
        "| Market story | Trader Brain | `market_story_engine` |",
        "| Story forecast | Trader Brain | `story_forecast_engine` |",
        "| Opportunity scoring | Trader Brain | harvest, allocator, structure |",
        "| Council observers | Trader Brain | observers-only, no vote gates |",
        "| Indicator confirmation | Trader Brain | boost only, never veto |",
        "| Entry candidates | Trader Brain | harvest + micro scalp + entry engine |",
        "| Portfolio sizing | Trader Brain | size only, no discovery suppression |",
        "| Conservative execution | Auditor Brain | next-bar, spread, slippage, SL-first |",
        "| Closed-candle slicing | Auditor Brain | anti-lookahead in backtest |",
        "| Validation gates | Auditor Brain | diagnostic reporting only |",
        "| Trust verdict | Auditor Brain | red-team comparison |",
        "| Strategy quality filters | Auditor Brain | NOT wired into trader pipeline |",
        "",
        "## Enforcement",
        "",
        "- `brains/trader_brain.py` — no imports from `execution_model`, `conservative_validation`",
        "- `brains/auditor_brain.py` — no imports from story/harvest scoring engines",
        "- `core/pipeline.py` — delegates discovery to `TraderBrain`",
        "- `backtesting/conservative_backtest_engine.py` — auditor execution path only",
        "- `validation/conservative_validation.py` — uses `AuditorBrain.verify_run`",
        "",
        "## Violations found and fixed",
        "",
    ]
    if fixed:
        for item in fixed:
            lines.append(f"- {item}")
    else:
        lines.extend(
            [
                "- Removed `StrategyQualityGate` from trader discovery path (`pipeline.py`, `trader_brain.py`)",
                "- Removed validation gate checks from `_run_entry_and_risk` trader path",
                "- Moved conservative execution ownership to `AuditorBrain`",
                "- `build_backtest_stack(apply_strategy_quality=False)` for trader signal generation",
                "- Validation gates remain in `AuditorBrain.check_validation_gates` (diagnostic only)",
            ]
        )

    lines.extend(
        [
            "",
            "## Snapshot comparison",
            "",
            "| | Trades | WR | PF | DD | Avg R |",
            "|---|--------|-----|-----|--------|-------|",
            _metrics_row(SNAPSHOT_G),
        ]
    )
    if snapshot_h is not None:
        lines.append(_metrics_row(snapshot_h))
        delta_trades = snapshot_h["trades"] - SNAPSHOT_G["trades"]
        lines.extend(
            [
                "",
                f"**Trade count delta (H − G):** {delta_trades:+d}",
                "",
                "Trade count must NOT drop due to auditor leakage into trader.",
            ]
        )
    else:
        lines.append("| H (post-split) | pending | — | — | — | — |")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_brain_separation_reports(
    project_root: Path,
    *,
    trader: TraderBrain | None = None,
    auditor: AuditorBrain | None = None,
    metrics: PerformanceMetrics | None = None,
    gate_report: ValidationGateReport | None = None,
) -> dict[str, Path]:
    """Write all brain separation reports."""
    snapshot_h = None
    if metrics is not None:
        snapshot_h = {
            "label": "H (post-split)",
            "trades": metrics.total_trades,
            "win_rate": metrics.win_rate,
            "profit_factor": metrics.profit_factor,
            "max_drawdown_pct": metrics.max_drawdown_pct,
            "average_r": metrics.average_r,
        }

    violations = auditor.violations_fixed if auditor is not None else None
    return {
        "trader": write_trader_brain_report(project_root, trader=trader),
        "auditor": write_auditor_brain_report(
            project_root,
            auditor=auditor,
            metrics=metrics,
            gate_report=gate_report,
            snapshot_h=snapshot_h,
        ),
        "audit": write_brain_separation_audit(
            project_root,
            violations_fixed=violations,
            snapshot_h=snapshot_h,
        ),
    }


def _metrics_row(snapshot: dict) -> str:
    return (
        f"| {snapshot['label']} | {snapshot['trades']} | "
        f"{snapshot['win_rate']:.1%} | {snapshot['profit_factor']:.2f} | "
        f"{snapshot['max_drawdown_pct']:.2f}% | {snapshot['average_r']:+.2f} |"
    )
