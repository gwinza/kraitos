"""Portfolio construction validation report writers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backtesting.performance_report import PerformanceMetrics


BASELINE_A = {
    "label": "Opportunity Allocation (A)",
    "trades": 430,
    "win_rate": 0.865,
    "profit_factor": 2.03,
    "max_drawdown_pct": 21.8,
    "average_r": 0.13,
}
BASELINE_B = {
    "label": "Drawdown Controls (B)",
    "trades": 274,
    "win_rate": 0.858,
    "profit_factor": 1.83,
    "max_drawdown_pct": 11.6,
    "average_r": 0.11,
}
TARGETS = {
    "trades_min": 430,
    "trades_ideal": 500,
    "win_rate_min": 0.65,
    "profit_factor_min": 1.5,
    "max_drawdown_pct": 15.0,
    "max_drawdown_ideal": 14.0,
    "average_r_min": 0.15,
}


def _status(pass_: bool) -> str:
    return "PASS" if pass_ else "MISS"


def write_portfolio_construction_validation_report(
    project_root: Path,
    *,
    current_metrics: dict | PerformanceMetrics,
) -> Path:
    """Write portfolio construction validation report."""
    project_root = project_root.resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    if isinstance(current_metrics, PerformanceMetrics):
        trades = current_metrics.total_trades
        win_rate = current_metrics.win_rate
        pf = current_metrics.profit_factor
        dd = current_metrics.max_drawdown_pct
        avg_r = current_metrics.average_r
    else:
        trades = int(current_metrics.get("total_trades", 0))
        win_rate = float(current_metrics.get("win_rate", 0.0))
        pf = float(current_metrics.get("profit_factor", 0.0))
        dd = float(current_metrics.get("max_drawdown_pct", 0.0))
        avg_r = float(current_metrics.get("average_r", 0.0))

    lines = [
        "# Portfolio Construction Validation Report",
        "",
        f"**Generated:** {now}",
        "",
        "Institutional Portfolio Construction and Allocation Engine validation.",
        "",
        "**Safety:** Live trading remains disabled. Portfolio scales risk; does not starve opportunities.",
        "",
        "## Metrics comparison",
        "",
        "| Snapshot | Trades | Win rate | PF | Max DD | Avg R |",
        "|----------|--------|----------|-----|--------|-------|",
        f"| {BASELINE_A['label']} | {BASELINE_A['trades']} | {BASELINE_A['win_rate']:.1%} | "
        f"{BASELINE_A['profit_factor']:.2f} | {BASELINE_A['max_drawdown_pct']:.1f}% | "
        f"+{BASELINE_A['average_r']:.2f}R |",
        f"| {BASELINE_B['label']} | {BASELINE_B['trades']} | {BASELINE_B['win_rate']:.1%} | "
        f"{BASELINE_B['profit_factor']:.2f} | {BASELINE_B['max_drawdown_pct']:.1f}% | "
        f"+{BASELINE_B['average_r']:.2f}R |",
        f"| Portfolio Construction (C) | {trades} | {win_rate:.1%} | {pf:.2f} | {dd:.2f}% | {avg_r:+.2f}R |",
        "",
        "## Target gates (C)",
        "",
        "| Metric | Target | Current | Status |",
        "|--------|--------|---------|--------|",
        f"| Trades | ≥ {TARGETS['trades_min']} ({TARGETS['trades_ideal']}+ ideal) | {trades} | "
        f"{_status(trades >= TARGETS['trades_min'])} |",
        f"| Win rate | ≥ {TARGETS['win_rate_min']:.0%} | {win_rate:.1%} | "
        f"{_status(win_rate >= TARGETS['win_rate_min'])} |",
        f"| Profit factor | ≥ {TARGETS['profit_factor_min']} | {pf:.2f} | "
        f"{_status(pf >= TARGETS['profit_factor_min'])} |",
        f"| Max drawdown | ≤ {TARGETS['max_drawdown_pct']:.0f}% ({TARGETS['max_drawdown_ideal']:.0f}% ideal) | {dd:.2f}% | "
        f"{_status(dd <= TARGETS['max_drawdown_pct'])} |",
        f"| Average R | ≥ +{TARGETS['average_r_min']:.2f} | {avg_r:+.2f}R | "
        f"{_status(avg_r >= TARGETS['average_r_min'])} |",
        "",
        "## Delta vs drawdown controls (B)",
        "",
        f"- Trades: {trades - BASELINE_B['trades']:+d}",
        f"- Win rate: {(win_rate - BASELINE_B['win_rate']) * 100:+.1f}%",
        f"- PF: {pf - BASELINE_B['profit_factor']:+.2f}",
        f"- Max DD: {dd - BASELINE_B['max_drawdown_pct']:+.2f}pp",
        f"- Avg R: {avg_r - BASELINE_B['average_r']:+.2f}R",
    ]
    path = logs / "portfolio_construction_validation_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_portfolio_vs_drawdown_controls_comparison(
    project_root: Path,
    *,
    current_metrics: dict | PerformanceMetrics,
) -> Path:
    """Write A/B/C comparison report."""
    project_root = project_root.resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    if isinstance(current_metrics, PerformanceMetrics):
        c_trades = current_metrics.total_trades
        c_wr = current_metrics.win_rate
        c_pf = current_metrics.profit_factor
        c_dd = current_metrics.max_drawdown_pct
        c_r = current_metrics.average_r
    else:
        c_trades = int(current_metrics.get("total_trades", 0))
        c_wr = float(current_metrics.get("win_rate", 0.0))
        c_pf = float(current_metrics.get("profit_factor", 0.0))
        c_dd = float(current_metrics.get("max_drawdown_pct", 0.0))
        c_r = float(current_metrics.get("average_r", 0.0))

    lines = [
        "# Portfolio vs Drawdown Controls Comparison",
        "",
        f"**Generated:** {now}",
        "",
        "## A / B / C comparison",
        "",
        "| Variant | Trades | WR | PF | DD | Avg R | Trade preservation | DD control |",
        "|---------|--------|-----|-----|-----|-------|-------------------|------------|",
        f"| A — Opportunity Allocation | {BASELINE_A['trades']} | {BASELINE_A['win_rate']:.1%} | "
        f"{BASELINE_A['profit_factor']:.2f} | {BASELINE_A['max_drawdown_pct']:.1f}% | "
        f"+{BASELINE_A['average_r']:.2f}R | High | Low |",
        f"| B — Drawdown Controls | {BASELINE_B['trades']} | {BASELINE_B['win_rate']:.1%} | "
        f"{BASELINE_B['profit_factor']:.2f} | {BASELINE_B['max_drawdown_pct']:.1f}% | "
        f"+{BASELINE_B['average_r']:.2f}R | Low (-156) | High |",
        f"| C — Portfolio Construction | {c_trades} | {c_wr:.1%} | {c_pf:.2f} | {c_dd:.2f}% | "
        f"{c_r:+.2f}R | {'High' if c_trades >= 400 else 'Medium'} | "
        f"{'High' if c_dd <= 15 else 'Medium'} |",
        "",
        "## Design intent",
        "",
        "- **A** maximizes opportunity capture but accepts high drawdown.",
        "- **B** cuts drawdown via trade starvation (430→274).",
        "- **C** ranks and scales capital via OAS, risk budget, correlation, heat — preserving scan volume.",
        "",
        "## C vs B deltas",
        "",
        f"- Trades recovered: {c_trades - BASELINE_B['trades']:+d} (target: recover ≥156)",
        f"- DD change: {c_dd - BASELINE_B['max_drawdown_pct']:+.2f}pp",
        f"- PF change: {c_pf - BASELINE_B['profit_factor']:+.2f}",
        f"- Avg R change: {c_r - BASELINE_B['average_r']:+.2f}R",
    ]
    path = logs / "portfolio_vs_drawdown_controls_comparison.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
