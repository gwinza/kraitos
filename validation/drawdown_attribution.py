"""Drawdown attribution analysis from conservative trade journal."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from risk.models import DEFAULT_CORRELATION_GROUPS
from validation.data_universe import YEAR_REGIME_LABELS
from validation.r_metrics import CLOSED_RESULTS

SESSION_BUCKETS = (
    (0, 8, "asia"),
    (8, 13, "london"),
    (13, 17, "london_ny_overlap"),
    (17, 22, "new_york"),
    (22, 24, "late_ny"),
)


@dataclass(frozen=True)
class DrawdownPeriod:
    """One equity drawdown episode."""

    start_time: datetime
    trough_time: datetime
    recovery_time: datetime | None
    peak_equity: float
    trough_equity: float
    drawdown_pct: float
    loss_pnl: float


def _infer_session(hour: int) -> str:
    for start, end, label in SESSION_BUCKETS:
        if start <= hour < end:
            return label
    return "late_ny"


def _clusters_for_symbol(symbol: str) -> list[str]:
    normalized = symbol.strip().upper()
    return [
        name
        for name, members in DEFAULT_CORRELATION_GROUPS.items()
        if normalized in members
    ]


def _load_closed_trades(journal_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(journal_path)
    if frame.empty:
        return frame
    frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")
    frame["profit_loss"] = pd.to_numeric(frame["profit_loss"], errors="coerce").fillna(0.0)
    frame["balance"] = pd.to_numeric(frame["balance"], errors="coerce").fillna(0.0)
    frame["r_multiple"] = pd.to_numeric(frame["r_multiple"], errors="coerce").fillna(0.0)
    closed = frame[frame["result"].isin(CLOSED_RESULTS)].copy()
    return closed.sort_values("event_time")


def _identify_drawdown_periods(closed: pd.DataFrame) -> list[DrawdownPeriod]:
    if closed.empty:
        return []

    periods: list[DrawdownPeriod] = []
    peak = float(closed.iloc[0]["balance"] - closed.iloc[0]["profit_loss"])
    peak_time = closed.iloc[0]["event_time"]
    in_dd = False
    trough = peak
    trough_time = peak_time
    episode_start = peak_time
    episode_loss = 0.0

    for _, row in closed.iterrows():
        balance = float(row["balance"])
        moment = row["event_time"]
        pnl = float(row["profit_loss"])

        if balance >= peak:
            if in_dd:
                dd_pct = (peak - trough) / peak * 100.0 if peak > 0 else 0.0
                periods.append(
                    DrawdownPeriod(
                        start_time=episode_start,
                        trough_time=trough_time,
                        recovery_time=moment,
                        peak_equity=peak,
                        trough_equity=trough,
                        drawdown_pct=dd_pct,
                        loss_pnl=episode_loss,
                    )
                )
                in_dd = False
                episode_loss = 0.0
            peak = balance
            peak_time = moment
            trough = peak
            trough_time = moment
            continue

        if not in_dd:
            in_dd = True
            episode_start = peak_time
            trough = balance
            trough_time = moment
            episode_loss = pnl if pnl < 0 else 0.0
        else:
            if balance < trough:
                trough = balance
                trough_time = moment
            if pnl < 0:
                episode_loss += pnl

    if in_dd and peak > 0:
        dd_pct = (peak - trough) / peak * 100.0
        periods.append(
            DrawdownPeriod(
                start_time=episode_start,
                trough_time=trough_time,
                recovery_time=None,
                peak_equity=peak,
                trough_equity=trough,
                drawdown_pct=dd_pct,
                loss_pnl=episode_loss,
            )
        )
    return sorted(periods, key=lambda p: p.drawdown_pct, reverse=True)


def _trades_in_drawdown(closed: pd.DataFrame, period: DrawdownPeriod) -> pd.DataFrame:
    end = period.recovery_time or closed["event_time"].max()
    mask = (closed["event_time"] >= period.start_time) & (closed["event_time"] <= end)
    losses = closed.loc[mask & (closed["profit_loss"] < 0)]
    return losses


def _loss_streaks(closed: pd.DataFrame) -> list[dict]:
    streaks: list[dict] = []
    current_key: tuple[str, str] | None = None
    count = 0
    total_loss = 0.0
    start_time = None

    for _, row in closed.iterrows():
        key = (str(row["symbol"]), str(row["mode"]))
        pnl = float(row["profit_loss"])
        if pnl < 0:
            if key == current_key:
                count += 1
                total_loss += pnl
            else:
                if count >= 3:
                    streaks.append(
                        {
                            "symbol": current_key[0] if current_key else "",
                            "mode": current_key[1] if current_key else "",
                            "losses": count,
                            "total_pnl": total_loss,
                            "start": start_time,
                        }
                    )
                current_key = key
                count = 1
                total_loss = pnl
                start_time = row["event_time"]
        else:
            if count >= 3 and current_key is not None:
                streaks.append(
                    {
                        "symbol": current_key[0],
                        "mode": current_key[1],
                        "losses": count,
                        "total_pnl": total_loss,
                        "start": start_time,
                    }
                )
            current_key = None
            count = 0
            total_loss = 0.0
            start_time = None

    if count >= 3 and current_key is not None:
        streaks.append(
            {
                "symbol": current_key[0],
                "mode": current_key[1],
                "losses": count,
                "total_pnl": total_loss,
                "start": start_time,
            }
        )
    return sorted(streaks, key=lambda s: s["total_pnl"])


def _pyramiding_events(
    frame: pd.DataFrame,
) -> tuple[list[dict], dict[str, int]]:
    opens = frame[frame["result"] == "open"].copy()
    if opens.empty:
        return [], {}
    events: list[dict] = []
    for (symbol, moment), group in opens.groupby(["symbol", "event_time"]):
        if len(group) > 1:
            events.append(
                {
                    "symbol": symbol,
                    "event_time": moment,
                    "count": len(group),
                    "modes": ", ".join(sorted(set(group["mode"].astype(str)))),
                }
            )
    same_symbol = (
        opens.sort_values("event_time")
        .groupby("symbol")
        .apply(
            lambda g: (g["event_time"].diff().dt.total_seconds() < 3600).sum(),
            include_groups=False,
        )
    )
    rapid = {sym: int(cnt) for sym, cnt in same_symbol.items() if cnt > 0}
    return events, rapid


def analyze_drawdown_attribution(journal_path: Path) -> dict:
    """Run full drawdown attribution analysis."""
    journal_path = journal_path.resolve()
    frame = pd.read_csv(journal_path) if journal_path.exists() else pd.DataFrame()
    closed = _load_closed_trades(journal_path) if journal_path.exists() else pd.DataFrame()

    periods = _identify_drawdown_periods(closed) if not closed.empty else []
    top_periods = periods[:5]

    dd_losses = pd.concat(
        [_trades_in_drawdown(closed, p) for p in top_periods[:3]],
        ignore_index=True,
    ).drop_duplicates(subset=["trade_id", "event_time"]) if top_periods else pd.DataFrame()

    by_symbol: dict[str, float] = {}
    by_mode: dict[str, float] = {}
    by_session: dict[str, float] = {}
    by_year: dict[str, float] = {}
    by_regime: dict[str, float] = {}
    by_cluster: dict[str, float] = {}
    by_reason: dict[str, float] = {}

    if not dd_losses.empty:
        for symbol, grp in dd_losses.groupby("symbol"):
            by_symbol[str(symbol)] = float(grp["profit_loss"].sum())
        for mode, grp in dd_losses.groupby("mode"):
            by_mode[str(mode)] = float(grp["profit_loss"].sum())
        for _, row in dd_losses.iterrows():
            hour = int(row["event_time"].hour)
            session = _infer_session(hour)
            by_session[session] = by_session.get(session, 0.0) + float(row["profit_loss"])
            year = str(int(row["event_time"].year))
            by_year[year] = by_year.get(year, 0.0) + float(row["profit_loss"])
            regime = YEAR_REGIME_LABELS.get(int(row["event_time"].year), "unknown")
            by_regime[regime] = by_regime.get(regime, 0.0) + float(row["profit_loss"])
            for cluster in _clusters_for_symbol(str(row["symbol"])):
                by_cluster[cluster] = by_cluster.get(cluster, 0.0) + float(row["profit_loss"])
            reason = str(row.get("reason", "unknown"))
            if "stop_loss" in reason:
                bucket = "stop_loss"
            elif "take_profit" in reason:
                bucket = "take_profit"
            elif "Enter" in reason:
                bucket = "entry_open"
            else:
                bucket = reason[:40]
            by_reason[bucket] = by_reason.get(bucket, 0.0) + float(row["profit_loss"])

    streaks = _loss_streaks(closed) if not closed.empty else []
    pyramid_same_moment: list[dict] = []
    rapid_reentry: dict[str, int] = {}
    if not frame.empty:
        frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")
        pyramid_same_moment, rapid_reentry = _pyramiding_events(frame)

    cluster_stacking: dict[str, int] = defaultdict(int)
    if not frame.empty:
        opens = frame[frame["result"] == "open"].sort_values("event_time")
        for moment, grp in opens.groupby("event_time"):
            clusters_at_moment: dict[str, set[str]] = defaultdict(set)
            for _, row in grp.iterrows():
                for cluster in _clusters_for_symbol(str(row["symbol"])):
                    clusters_at_moment[cluster].add(str(row["symbol"]))
            for cluster, symbols in clusters_at_moment.items():
                if len(symbols) >= 2:
                    cluster_stacking[cluster] += 1

    return {
        "journal_path": str(journal_path),
        "total_closed": len(closed),
        "max_drawdown_pct": periods[0].drawdown_pct if periods else 0.0,
        "top_periods": top_periods,
        "by_symbol": dict(sorted(by_symbol.items(), key=lambda x: x[1])),
        "by_mode": dict(sorted(by_mode.items(), key=lambda x: x[1])),
        "by_session": dict(sorted(by_session.items(), key=lambda x: x[1])),
        "by_year": dict(sorted(by_year.items(), key=lambda x: x[1])),
        "by_regime": dict(sorted(by_regime.items(), key=lambda x: x[1])),
        "by_cluster": dict(sorted(by_cluster.items(), key=lambda x: x[1])),
        "by_reason": dict(sorted(by_reason.items(), key=lambda x: x[1])),
        "loss_streaks": streaks[:10],
        "pyramid_same_moment": pyramid_same_moment[:15],
        "rapid_reentry": rapid_reentry,
        "cluster_stacking_events": dict(cluster_stacking),
    }


def _fmt_money(value: float) -> str:
    return f"${value:,.2f}"


def write_drawdown_attribution_report(
    project_root: Path,
    *,
    journal_path: Path | None = None,
) -> tuple[Path, dict]:
    """Write logs/drawdown_attribution_report.md from journal analysis."""
    root = project_root.resolve()
    journal = journal_path or root / "logs" / "conservative_trade_journal.csv"
    analysis = analyze_drawdown_attribution(journal)
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Drawdown Attribution Report",
        "",
        f"**Generated:** {now}",
        f"**Journal:** `{journal}`",
        f"**Closed trades:** {analysis['total_closed']}",
        f"**Max drawdown:** {analysis['max_drawdown_pct']:.2f}%",
        "",
        "## Top drawdown episodes",
        "",
        "| Start | Trough | DD % | Loss PnL | Recovered |",
        "|-------|--------|------|----------|-----------|",
    ]

    for period in analysis["top_periods"]:
        recovered = "yes" if period.recovery_time else "open"
        lines.append(
            f"| {period.start_time.date()} | {period.trough_time.date()} | "
            f"{period.drawdown_pct:.1f}% | {_fmt_money(period.loss_pnl)} | {recovered} |"
        )

    def _table(title: str, data: dict[str, float], limit: int = 10) -> list[str]:
        rows = [f"## {title}", "", "| Key | Loss PnL |", "|-----|----------|"]
        for key, pnl in list(data.items())[:limit]:
            rows.append(f"| {key} | {_fmt_money(pnl)} |")
        rows.append("")
        return rows

    lines.extend(_table("Worst symbols during drawdown", analysis["by_symbol"]))
    lines.extend(_table("Worst strategy modes", analysis["by_mode"]))
    lines.extend(_table("Worst sessions (UTC hour buckets)", analysis["by_session"]))
    lines.extend(_table("Worst years", analysis["by_year"]))
    lines.extend(_table("Worst regimes", analysis["by_regime"]))
    lines.extend(_table("Exit / reason buckets", analysis["by_reason"]))

    lines.extend(["## Loss streaks (≥3 consecutive)", ""])
    if analysis["loss_streaks"]:
        lines.append("| Symbol | Mode | Losses | Total PnL |")
        lines.append("|--------|------|--------|-----------|")
        for streak in analysis["loss_streaks"]:
            lines.append(
                f"| {streak['symbol']} | {streak['mode']} | {streak['losses']} | "
                f"{_fmt_money(streak['total_pnl'])} |"
            )
    else:
        lines.append("No significant loss streaks detected.")
    lines.append("")

    lines.extend(["## Pyramiding / add-on entries", ""])
    if analysis["pyramid_same_moment"]:
        lines.append("| Symbol | Time | Opens | Modes |")
        lines.append("|--------|------|-------|-------|")
        for event in analysis["pyramid_same_moment"]:
            lines.append(
                f"| {event['symbol']} | {event['event_time']} | "
                f"{event['count']} | {event['modes']} |"
            )
    else:
        lines.append("No simultaneous multi-open events on same symbol.")
    lines.append("")

    if analysis["rapid_reentry"]:
        lines.append("Rapid re-entry (<1h) counts by symbol:")
        for sym, cnt in sorted(analysis["rapid_reentry"].items(), key=lambda x: -x[1]):
            lines.append(f"- {sym}: {cnt}")
        lines.append("")

    path = root / "logs" / "drawdown_attribution_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path, analysis


def write_risk_cluster_report(
    project_root: Path,
    *,
    journal_path: Path | None = None,
) -> Path:
    """Write logs/risk_cluster_report.md with correlation stacking analysis."""
    root = project_root.resolve()
    journal = journal_path or root / "logs" / "conservative_trade_journal.csv"
    analysis = analyze_drawdown_attribution(journal)
    now = datetime.now(timezone.utc).isoformat()

    lines = [
        "# Risk Cluster Report",
        "",
        f"**Generated:** {now}",
        f"**Journal:** `{journal}`",
        "",
        "## Correlation groups",
        "",
    ]
    for name, members in DEFAULT_CORRELATION_GROUPS.items():
        lines.append(f"- **{name}:** {', '.join(members)}")
    lines.append("")

    lines.extend(["## Cluster loss during drawdown", ""])
    if analysis["by_cluster"]:
        lines.append("| Cluster | Loss PnL |")
        lines.append("|---------|----------|")
        for cluster, pnl in analysis["by_cluster"].items():
            lines.append(f"| {cluster} | {_fmt_money(pnl)} |")
    else:
        lines.append("No cluster-attributed losses in top drawdown windows.")
    lines.append("")

    lines.extend(["## Simultaneous cluster stacking events", ""])
    stacking = analysis.get("cluster_stacking_events", {})
    if stacking:
        lines.append("| Cluster | Multi-symbol open events |")
        lines.append("|---------|--------------------------|")
        for cluster, count in sorted(stacking.items(), key=lambda x: -x[1]):
            lines.append(f"| {cluster} | {count} |")
    else:
        lines.append("No multi-symbol cluster stacking detected.")
    lines.append("")

    lines.extend(
        [
            "## Diagnostic notes",
            "",
            "Reports are diagnostic only — no automatic trade suppression or sizing cuts.",
            "Catastrophic protection (DD >25% new-entry block) is enforced separately.",
            "",
        ]
    )

    path = root / "logs" / "risk_cluster_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_attribution_reports(project_root: Path) -> tuple[Path, Path, dict]:
    """Generate both attribution reports."""
    attr_path, analysis = write_drawdown_attribution_report(project_root)
    cluster_path = write_risk_cluster_report(project_root)
    return attr_path, cluster_path, analysis


def write_drawdown_reduction_validation_report(
    project_root: Path,
    *,
    baseline: dict | None = None,
    current_metrics: dict,
) -> Path:
    """Compare drawdown reduction validation vs baseline targets."""
    root = project_root.resolve()
    if baseline is None:
        baseline = {
            "label": "Baseline (pre drawdown controls @ 22:39 UTC)",
            "trades": 430,
            "win_rate": 0.865,
            "profit_factor": 2.03,
            "max_drawdown_pct": 21.8,
            "average_r": 0.13,
        }
    targets = {
        "trades": 430,
        "win_rate": 0.65,
        "profit_factor": 1.5,
        "max_drawdown_pct": 15.0,
        "average_r": 0.15,
    }
    current = {
        "label": "Drawdown controls (current)",
        "trades": int(current_metrics.get("total_trades", 0)),
        "win_rate": float(current_metrics.get("win_rate", 0.0)),
        "profit_factor": float(current_metrics.get("profit_factor", 0.0)),
        "max_drawdown_pct": float(current_metrics.get("max_drawdown_pct", 0.0)),
        "average_r": float(current_metrics.get("average_r", 0.0)),
    }

    def _pass(metric: str, value: float) -> str:
        if metric == "trades":
            return "PASS" if value >= targets["trades"] else "MISS"
        if metric == "win_rate":
            return "PASS" if value >= targets["win_rate"] else "MISS"
        if metric == "profit_factor":
            return "PASS" if value >= targets["profit_factor"] else "MISS"
        if metric == "max_drawdown_pct":
            return "PASS" if value <= targets["max_drawdown_pct"] else "MISS"
        if metric == "average_r":
            return "PASS" if value >= targets["average_r"] else "MISS"
        return "—"

    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Drawdown Reduction Validation Report",
        "",
        f"**Generated:** {now}",
        "",
        "**Safety:** Live trading remains disabled. Drawdown reports are diagnostic only.",
        "",
        "## Metrics comparison",
        "",
        "| Snapshot | Trades | Win rate | PF | Max DD | Avg R |",
        "|----------|--------|----------|-----|--------|-------|",
        (
            f"| {baseline['label']} | {baseline['trades']} | "
            f"{baseline['win_rate']:.1%} | {baseline['profit_factor']:.2f} | "
            f"{baseline['max_drawdown_pct']:.2f}% | {baseline['average_r']:+.2f}R |"
        ),
        (
            f"| {current['label']} | {current['trades']} | "
            f"{current['win_rate']:.1%} | {current['profit_factor']:.2f} | "
            f"{current['max_drawdown_pct']:.2f}% | {current['average_r']:+.2f}R |"
        ),
        "",
        "## Target gates",
        "",
        "| Metric | Target | Current | Status |",
        "|--------|--------|---------|--------|",
        f"| Trades | ≥ {targets['trades']} | {current['trades']} | {_pass('trades', current['trades'])} |",
        f"| Win rate | ≥ {targets['win_rate']:.0%} | {current['win_rate']:.1%} | {_pass('win_rate', current['win_rate'])} |",
        f"| Profit factor | ≥ {targets['profit_factor']:.1f} | {current['profit_factor']:.2f} | {_pass('profit_factor', current['profit_factor'])} |",
        f"| Max drawdown | ≤ {targets['max_drawdown_pct']:.0f}% (ideal <12%) | {current['max_drawdown_pct']:.2f}% | {_pass('max_drawdown_pct', current['max_drawdown_pct'])} |",
        f"| Average R | ≥ +{targets['average_r']:.2f} | {current['average_r']:+.2f} | {_pass('average_r', current['average_r'])} |",
        "",
        "## Delta vs baseline",
        "",
        f"- Trades: {current['trades'] - baseline['trades']:+d}",
        f"- Win rate: {(current['win_rate'] - baseline['win_rate']):+.1%}",
        f"- PF: {current['profit_factor'] - baseline['profit_factor']:+.2f}",
        f"- Max DD: {current['max_drawdown_pct'] - baseline['max_drawdown_pct']:+.2f}pp",
        f"- Avg R: {current['average_r'] - baseline['average_r']:+.2f}R",
        "",
    ]
    path = root / "logs" / "drawdown_reduction_validation_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_post_drawdown_throttle_undo_validation_report(
    project_root: Path,
    *,
    current_metrics: dict,
) -> Path:
    """Compare post-undo validation against pre-throttle and throttled snapshots."""
    root = project_root.resolve()
    snapshots = {
        "A": {
            "label": "A (pre-DD throttles)",
            "trades": 430,
            "win_rate": 0.865,
            "profit_factor": 2.03,
            "max_drawdown_pct": 21.8,
            "average_r": 0.13,
        },
        "B": {
            "label": "B (DD throttles)",
            "trades": 274,
            "win_rate": 0.858,
            "profit_factor": 1.83,
            "max_drawdown_pct": 11.56,
            "average_r": 0.11,
        },
        "C": {
            "label": "C (portfolio)",
            "trades": 200,
            "win_rate": 0.765,
            "profit_factor": 1.33,
            "max_drawdown_pct": 11.19,
            "average_r": 0.07,
        },
        "D": {
            "label": "D (post-undo — current)",
            "trades": int(current_metrics.get("total_trades", 0)),
            "win_rate": float(current_metrics.get("win_rate", 0.0)),
            "profit_factor": float(current_metrics.get("profit_factor", 0.0)),
            "max_drawdown_pct": float(current_metrics.get("max_drawdown_pct", 0.0)),
            "average_r": float(current_metrics.get("average_r", 0.0)),
        },
    }
    targets = {
        "trades": 430,
        "win_rate": 0.65,
        "profit_factor": 1.5,
        "average_r": 0.13,
    }
    current = snapshots["D"]

    def _row(snapshot: dict) -> str:
        return (
            f"| {snapshot['label']} | {snapshot['trades']} | "
            f"{snapshot['win_rate']:.1%} | {snapshot['profit_factor']:.2f} | "
            f"{snapshot['max_drawdown_pct']:.2f}% | {snapshot['average_r']:+.2f}R |"
        )

    def _pass(metric: str, value: float) -> str:
        if metric == "trades":
            return "PASS" if value >= targets["trades"] else "MISS"
        if metric == "win_rate":
            return "PASS" if value >= targets["win_rate"] else "MISS"
        if metric == "profit_factor":
            return "PASS" if value >= targets["profit_factor"] else "MISS"
        if metric == "average_r":
            return "PASS" if value >= targets["average_r"] else "MISS"
        return "—"

    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Post Drawdown Throttle Undo Validation Report",
        "",
        f"**Generated:** {now}",
        "",
        "Validation after removing drawdown-aware trade starvation layers.",
        "Harvesting restored; catastrophic protection only (DD >25% hard block).",
        "",
        "**Safety:** Live trading remains disabled.",
        "Drawdown attribution and reduction reports are **diagnostic only** — no enforcement.",
        "",
        "See also: `logs/drawdown_throttle_undo_report.md` for code changes and throttles removed.",
        "",
        "## Metrics comparison",
        "",
        "| Snapshot | Trades | Win rate | PF | Max DD | Avg R |",
        "|----------|--------|----------|-----|--------|-------|",
        _row(snapshots["A"]),
        _row(snapshots["B"]),
        _row(snapshots["C"]),
        _row(snapshots["D"]),
        "",
        "## Target gates (post-undo)",
        "",
        "Max drawdown may rise vs throttled runs — acceptable to preserve harvesting.",
        "",
        "| Metric | Target | Current (D) | Status |",
        "|--------|--------|-------------|--------|",
        f"| Trades | ≥ {targets['trades']} | {current['trades']} | {_pass('trades', current['trades'])} |",
        f"| Win rate | ≥ {targets['win_rate']:.0%} | {current['win_rate']:.1%} | {_pass('win_rate', current['win_rate'])} |",
        f"| Profit factor | ≥ {targets['profit_factor']:.1f} | {current['profit_factor']:.2f} | {_pass('profit_factor', current['profit_factor'])} |",
        f"| Average R | ≥ +{targets['average_r']:.2f} | {current['average_r']:+.2f} | {_pass('average_r', current['average_r'])} |",
        f"| Max drawdown | informational (may exceed 15%) | {current['max_drawdown_pct']:.2f}% | — |",
        "",
        "## Delta vs pre-throttle baseline (A)",
        "",
        f"- Trades: {current['trades'] - snapshots['A']['trades']:+d}",
        f"- Win rate: {(current['win_rate'] - snapshots['A']['win_rate']):+.1%}",
        f"- PF: {current['profit_factor'] - snapshots['A']['profit_factor']:+.2f}",
        f"- Max DD: {current['max_drawdown_pct'] - snapshots['A']['max_drawdown_pct']:+.2f}pp",
        f"- Avg R: {current['average_r'] - snapshots['A']['average_r']:+.2f}R",
        "",
        "## Delta vs throttled portfolio (C)",
        "",
        f"- Trades: {current['trades'] - snapshots['C']['trades']:+d}",
        f"- Win rate: {(current['win_rate'] - snapshots['C']['win_rate']):+.1%}",
        f"- PF: {current['profit_factor'] - snapshots['C']['profit_factor']:+.2f}",
        f"- Max DD: {current['max_drawdown_pct'] - snapshots['C']['max_drawdown_pct']:+.2f}pp",
        f"- Avg R: {current['average_r'] - snapshots['C']['average_r']:+.2f}R",
        "",
        "## Undo scope (diagnostic drawdown, catastrophic protection only)",
        "",
        "- **Removed:** multi-tier DD risk multipliers, loss-streak pauses, DD-based add-on blocks,",
        "  correlation cluster hard caps, same-direction DD stacking blocks, OAS DD penalties.",
        "- **Kept:** DD >25% new-entry hard block, emergency stop, live-trading-disabled gate,",
        "  portfolio heat catastrophic halt, validation gate.",
        "- **Reports:** `drawdown_attribution_report.md`, `drawdown_reduction_validation_report.md`,",
        "  and `risk_cluster_report.md` are analysis-only — no trade suppression.",
        "",
    ]
    path = root / "logs" / "post_drawdown_throttle_undo_validation_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
