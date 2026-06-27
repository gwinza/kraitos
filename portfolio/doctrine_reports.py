"""Portfolio Capital Allocation Doctrine — validation and runtime reports."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from portfolio import PORTFOLIO_DNA_STATEMENT


def write_portfolio_allocation_doctrine_report(
    project_root: Path,
    *,
    classifier_counts: dict[str, int] | None = None,
) -> Path:
    """Write doctrine summary and DNA."""
    project_root = project_root.resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Portfolio Allocation Doctrine Report",
        "",
        f"**Generated:** {now}",
        "",
        "## DNA",
        "",
        PORTFOLIO_DNA_STATEMENT,
        "",
        "## Doctrine principles",
        "",
        "- Portfolio classifies and allocates — default response is **How much?** not **No.**",
        "- HARVEST (0.10–0.30%), PROPER (0.50–1.00%), ELITE (1.00–1.50%)",
        "- Correlation, heat, daily loss, and open-position pressure **scale** sizing",
        "- NO_TRADE only for catastrophic safety or absent valid TraderBrain story",
        "",
    ]
    if classifier_counts:
        lines.extend([
            "## Classification summary",
            "",
            "| Class | Count |",
            "|-------|-------|",
        ])
        for tier in ("MICRO_HARVEST", "HARVEST", "PROPER", "ELITE", "SCOUT", "NO_TRADE"):
            lines.append(f"| {tier} | {classifier_counts.get(tier, 0)} |")
    path = logs / "portfolio_allocation_doctrine_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_allocation_vs_rejection_report(
    project_root: Path,
    *,
    scaled_not_rejected: int = 0,
    classifier_counts: dict[str, int] | None = None,
    correlation_scaled: int = 0,
    heat_scaled: int = 0,
    daily_loss_scaled: int = 0,
    total_allocated_risk_pct: float = 0.0,
) -> Path:
    """Compare previously-rejected opportunities now allocated."""
    project_root = project_root.resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    harvest = classifier_counts.get("HARVEST", 0) if classifier_counts else 0
    proper = classifier_counts.get("PROPER", 0) if classifier_counts else 0
    elite = classifier_counts.get("ELITE", 0) if classifier_counts else 0
    allocated = harvest + proper + elite
    lines = [
        "# Allocation vs Rejection Report",
        "",
        f"**Generated:** {now}",
        "",
        "## Previously rejected → now allocated",
        "",
        f"- **Scaled-not-rejected:** {scaled_not_rejected} opportunities sized instead of denied",
        f"- **Total tier allocations:** {allocated} (HARVEST {harvest}, PROPER {proper}, ELITE {elite})",
        "",
        "## Scaling usage (not rejection)",
        "",
        f"- Correlation scaling applied: **{correlation_scaled}**",
        f"- Heat scaling applied: **{heat_scaled}**",
        f"- Daily loss scaling applied: **{daily_loss_scaled}**",
        "",
        "## Capital utilisation",
        "",
        f"- **Cumulative allocated risk %:** {total_allocated_risk_pct:.2f}%",
        "",
        "## Impact vs Snapshot H",
        "",
        "Portfolio caps previously killed ~15–26% of valid opportunities.",
        "Doctrine shifts those to scaled micro-risk allocations.",
    ]
    path = logs / "allocation_vs_rejection_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_risk_manager_allocation_only_report(project_root: Path) -> Path:
    """Write Risk Manager Allocation-Only Doctrine summary."""
    project_root = project_root.resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Risk Manager Allocation-Only Report",
        "",
        f"**Generated:** {now}",
        "",
        "## Core law",
        "",
        "RiskManager scales size — NEVER blocks except catastrophic conditions.",
        "",
        "### Block only if",
        "",
        "1. Emergency stop active",
        "2. Live trading safety violation",
        "3. Broker/execution unavailable",
        "4. No valid TraderBrain story",
        "5. DD ≥ 50%: stop new trades",
        "6. DD ≥ 40%: extreme defensive micro-allocation (scale to floor)",
        "",
        "### Scale (never reject)",
        "",
        "| Factor | Scale bands |",
        "|--------|-------------|",
        "| Max open trades | 75% / 50% / 25% / 10% slot crowding |",
        "| Daily loss budget | 100% / 75% / 50% / 25% |",
        "| Correlation cluster | 100% / 80% / 60% / 40% / 20% |",
        "| Portfolio heat | 100% / 75% / 50% / 25% / 10% |",
        "| Symbol exposure | soft scale 75% / 50% / 25% |",
        "| USD stacking | soft scale via exposure netting |",
        "| Loss streaks | 75% (3+) / 50% (5+) — report only |",
        "| OAS score | size tier only (defer 15%, watchlist 25%) |",
        "| Normal drawdown | 75% (15%+) / 50% (25%+) / 10% (40%+) |",
        "",
        "## Opportunity tiers (base risk)",
        "",
        "| Tier | Risk range |",
        "|------|------------|",
        "| HARVEST | 0.10–0.30% |",
        "| PROPER | 0.50–1.00% |",
        "| ELITE | 1.00–1.50% |",
        "",
        "## Floor",
        "",
        "Minimum allocated risk: **0.01%** or **0.01 lot** — never zero unless catastrophic.",
    ]
    path = logs / "risk_manager_allocation_only_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_risk_blocker_removal_report(project_root: Path) -> Path:
    """Document blockers removed under allocation-only doctrine."""
    project_root = project_root.resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Risk Blocker Removal Report",
        "",
        f"**Generated:** {now}",
        "",
        "## Before (binary reject)",
        "",
        "| Blocker | Old behavior |",
        "|---------|--------------|",
        "| Max open trades | Hard reject at cap |",
        "| Daily loss budget | Hard reject at limit |",
        "| Symbol exposure | Hard reject over limit |",
        "| Correlated exposure | Hard reject over limit |",
        "| Portfolio heat | Suppress at catastrophic |",
        "| Daily loss 100% | Catastrophic suppress |",
        "| Drawdown 25% | Hard block new entries |",
        "| MIN combined score | Hard floor reject |",
        "",
        "## After (scale only)",
        "",
        "| Blocker | New behavior |",
        "|---------|--------------|",
        "| Max open trades | Slot crowding scale 75→10% |",
        "| Daily loss budget | Scale 100→25% |",
        "| Symbol exposure | Soft scale 75→25% |",
        "| Correlated exposure | Position cluster scale 100→20% |",
        "| Portfolio heat | Scale to 10% floor |",
        "| Daily loss 100% | Scale to 25% |",
        "| Drawdown 40% | Micro-allocation 10% |",
        "| Drawdown 50% | Only hard block |",
        "| OAS / combined | Micro-allocation floor 0.01% |",
        "",
        "## Unchanged (catastrophic only)",
        "",
        "- Emergency stop",
        "- Live trading safety",
        "- Broker unavailable",
        "- No valid TraderBrain story",
        "- DD ≥ 50%",
    ]
    path = logs / "risk_blocker_removal_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


SNAPSHOT_I = {
    "label": "Snapshot I",
    "trades": 398,
    "win_rate": 0.942,
    "profit_factor": 2.90,
    "max_drawdown_pct": 4.59,
    "average_r": 0.15,
    "validation_days": 504,
}


def write_risk_manager_allocation_only_validation_report(
    project_root: Path,
    *,
    current_metrics: dict,
) -> Path:
    """Compare Snapshot I baseline vs Snapshot K after allocation-only doctrine."""
    project_root = project_root.resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    trades = int(current_metrics.get("total_trades", 0))
    win_rate = float(current_metrics.get("win_rate", 0.0))
    pf = float(current_metrics.get("profit_factor", 0.0))
    dd = float(current_metrics.get("max_drawdown_pct", 0.0))
    avg_r = float(current_metrics.get("average_r", 0.0))
    days = int(current_metrics.get("validation_days", SNAPSHOT_I["validation_days"]))
    trades_per_day = trades / days if days else 0.0
    baseline_tpd = SNAPSHOT_I["trades"] / SNAPSHOT_I["validation_days"]

    def _delta(current: float, baseline: float, *, pct: bool = False) -> str:
        diff = current - baseline
        if pct:
            return f"{diff:+.1%}"
        return f"{diff:+.2f}"

    gates = {
        "trades_increased": trades > SNAPSHOT_I["trades"],
        "pf_above_1_5": pf >= 1.5,
        "wr_above_65": win_rate >= 0.65,
        "dd_acceptable": dd < 50.0,
    }
    overall = all(gates.values())

    lines = [
        "# Risk Manager Allocation-Only Validation Report",
        "",
        f"**Generated:** {now}",
        "",
        "## Snapshot comparison",
        "",
        "| Metric | Snapshot I | Snapshot K | Delta |",
        "|--------|------------|------------|-------|",
        f"| Trades | {SNAPSHOT_I['trades']} | {trades} | {_delta(trades, SNAPSHOT_I['trades'])} |",
        f"| Win rate | {SNAPSHOT_I['win_rate']:.1%} | {win_rate:.1%} | {_delta(win_rate, SNAPSHOT_I['win_rate'], pct=True)} |",
        f"| Profit factor | {SNAPSHOT_I['profit_factor']:.2f} | {pf:.2f} | {_delta(pf, SNAPSHOT_I['profit_factor'])} |",
        f"| Max DD | {SNAPSHOT_I['max_drawdown_pct']:.2f}% | {dd:.2f}% | {_delta(dd, SNAPSHOT_I['max_drawdown_pct'])}% |",
        f"| Avg R | {SNAPSHOT_I['average_r']:+.2f} | {avg_r:+.2f} | {_delta(avg_r, SNAPSHOT_I['average_r'])} |",
        f"| Trades/day | {baseline_tpd:.2f} | {trades_per_day:.2f} | {_delta(trades_per_day, baseline_tpd)} |",
        "",
        f"**Trades/day method:** total trades / {days} validation days (baseline I: 398/504).",
        "",
        "## Gate checklist",
        "",
        f"- Trade count increased vs I: **{'PASS' if gates['trades_increased'] else 'MISS'}**",
        f"- PF ≥ 1.5: **{'PASS' if gates['pf_above_1_5'] else 'MISS'}**",
        f"- WR ≥ 65%: **{'PASS' if gates['wr_above_65'] else 'MISS'}**",
        f"- DD acceptable (<50%): **{'PASS' if gates['dd_acceptable'] else 'MISS'}**",
        "",
        f"**Overall:** {'PASS' if overall else 'MISS'}",
    ]
    path = logs / "risk_manager_allocation_only_validation_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


SNAPSHOT_K = {
    "label": "Snapshot K",
    "trades": 709,
    "win_rate": 0.841,
    "profit_factor": 7.83,
    "max_drawdown_pct": 1.31,
    "average_r": 0.94,
    "validation_days": 504,
}


def write_unlimited_opportunity_execution_report(project_root: Path) -> Path:
    """Summarize unlimited opportunity execution metrics."""
    from portfolio.unlimited_opportunity_tracker import get_unlimited_opportunity_tracker

    project_root = project_root.resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    tracker = get_unlimited_opportunity_tracker()
    summary = tracker.summary()
    lines = [
        "# Unlimited Opportunity Execution Report",
        "",
        f"**Generated:** {now}",
        "",
        "## Opportunities",
        "",
        f"- **Seen:** {summary['opportunities_seen']}",
        f"- **Taken (trade intent):** {summary['opportunities_taken']}",
        f"- **Rejected:** {summary['opportunities_rejected']}",
        "",
        "## Simultaneous capacity",
        "",
        f"- **Max open:** {summary['max_simultaneous_open']}",
        f"- **Avg open:** {summary['avg_simultaneous_open']}",
        "",
        "## Top rejection reasons",
        "",
    ]
    for reason, count in tracker.rejection_reasons.most_common(10):
        lines.append(f"- {reason}: {count}")
    lines.extend([
        "",
        "## Remaining caps discovered",
        "",
    ])
    caps = summary["remaining_caps"] or [
        "VirtualAccount catastrophic gate only (50% DD)",
        "RiskManager catastrophic_gate (50% DD)",
        "Story unclear / no valid opportunity (TraderBrain)",
        "Emergency stop / live safety / broker unavailable",
    ]
    for cap in caps:
        lines.append(f"- {cap}")
    path = logs / "unlimited_opportunity_execution_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_all_opportunities_taken_report(project_root: Path) -> Path:
    """Per-symbol and per-class opportunity uptake."""
    from portfolio.unlimited_opportunity_tracker import get_unlimited_opportunity_tracker

    project_root = project_root.resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    tracker = get_unlimited_opportunity_tracker()
    lines = [
        "# All Opportunities Taken Report",
        "",
        f"**Generated:** {now}",
        "",
        "## By symbol",
        "",
        "| Symbol | Taken |",
        "|--------|-------|",
    ]
    for symbol, count in sorted(tracker.trades_per_symbol.items()):
        lines.append(f"| {symbol} | {count} |")
    lines.extend([
        "",
        "## By opportunity class (setup_kind)",
        "",
        "| Class | Taken |",
        "|-------|-------|",
    ])
    for cls, count in sorted(tracker.trades_per_class.items()):
        lines.append(f"| {cls} | {count} |")
    lines.extend([
        "",
        "## Multi-trade timestamps (same candle)",
        "",
        f"- Timestamps with >1 trade: "
        f"{sum(1 for c in tracker.trades_per_timestamp.values() if c > 1)}",
    ])
    path = logs / "all_opportunities_taken_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_simultaneous_trade_capacity_report(project_root: Path) -> Path:
    """Document simultaneous open trade capacity during validation."""
    from portfolio.unlimited_opportunity_tracker import get_unlimited_opportunity_tracker

    project_root = project_root.resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    tracker = get_unlimited_opportunity_tracker()
    lines = [
        "# Simultaneous Trade Capacity Report",
        "",
        f"**Generated:** {now}",
        "",
        f"- **Max simultaneous open:** {tracker.max_simultaneous_open}",
        f"- **Avg simultaneous open:** {tracker.avg_simultaneous_open:.2f}",
        f"- **Samples:** {len(tracker.simultaneous_samples)}",
        "",
        "Doctrine: no max-open hard cap — slot crowding scales allocation only.",
    ]
    path = logs / "simultaneous_trade_capacity_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_unlimited_opportunity_validation_report(
    project_root: Path,
    *,
    current_metrics: dict,
) -> Path:
    """Snapshot L vs K comparison after unlimited opportunity execution."""
    project_root = project_root.resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    trades = int(current_metrics.get("total_trades", 0))
    win_rate = float(current_metrics.get("win_rate", 0.0))
    pf = float(current_metrics.get("profit_factor", 0.0))
    dd = float(current_metrics.get("max_drawdown_pct", 0.0))
    avg_r = float(current_metrics.get("average_r", 0.0))
    days = int(current_metrics.get("validation_days", SNAPSHOT_K["validation_days"]))
    tpd = trades / days if days else 0.0
    k_tpd = SNAPSHOT_K["trades"] / SNAPSHOT_K["validation_days"]

    def _delta(current: float, baseline: float, *, pct: bool = False) -> str:
        diff = current - baseline
        if pct:
            return f"{diff:+.1%}"
        return f"{diff:+.2f}"

    lines = [
        "# Unlimited Opportunity Validation Report (Snapshot L vs K)",
        "",
        f"**Generated:** {now}",
        "",
        "| Metric | Snapshot K | Snapshot L | Delta |",
        "|--------|------------|------------|-------|",
        f"| Trades | {SNAPSHOT_K['trades']} | {trades} | {_delta(trades, SNAPSHOT_K['trades'])} |",
        f"| Win rate | {SNAPSHOT_K['win_rate']:.1%} | {win_rate:.1%} | "
        f"{_delta(win_rate, SNAPSHOT_K['win_rate'], pct=True)} |",
        f"| Profit factor | {SNAPSHOT_K['profit_factor']:.2f} | {pf:.2f} | "
        f"{_delta(pf, SNAPSHOT_K['profit_factor'])} |",
        f"| Max DD | {SNAPSHOT_K['max_drawdown_pct']:.2f}% | {dd:.2f}% | "
        f"{_delta(dd, SNAPSHOT_K['max_drawdown_pct'])}% |",
        f"| Avg R | {SNAPSHOT_K['average_r']:+.2f} | {avg_r:+.2f} | "
        f"{_delta(avg_r, SNAPSHOT_K['average_r'])} |",
        f"| Trades/day | {k_tpd:.2f} | {tpd:.2f} | {_delta(tpd, k_tpd)} |",
        "",
        f"**Trades/day:** total trades ÷ {days} validation days.",
    ]
    path = logs / "unlimited_opportunity_validation_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
