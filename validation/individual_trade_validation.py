"""
Validate Individual Trade Doctrine v1.1 against broker baseline.

Compares frozen broker partial journal (Thesis Edition) vs v1.1 backtest.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from data.importers.pipeline import load_normalized_universe, run_import_pipeline
from intelligence.individual_trade_doctrine import reset_individual_trade_tracker
from intelligence.thesis_projection_learning_engine import (
    reset_thesis_projection_learning_engine,
)
from intelligence.kraitos_thesis_doctrine import reset_thesis_tracker
from validation.metrics_collector import metrics_from_journal_frame
from validation.r_metrics import CLOSED_RESULTS
from validation.reality_validation import _run_backtest
from backtesting.execution_model import ExecutionCostConfig

BROKER_SYMBOLS = ("EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "GBPJPY")
BASELINE_JOURNAL = "broker_partial_journal.csv"
V11_JOURNAL = "path_c_broker_journal.csv"


def _journal_metrics(path: Path, initial: float = 10_000.0) -> dict:
    if not path.exists() or path.stat().st_size < 100:
        return {}
    frame = pd.read_csv(path)
    closed = frame[frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS)]
    if closed.empty:
        return {"trades": 0}
    perf = metrics_from_journal_frame(closed, initial)
    partials = closed[closed["reason"] == "partial_take_profit"]
    opens = frame[frame["result"] == "open"]
    full_sl = 0
    for tid in opens["trade_id"].unique():
        ex = closed[closed["trade_id"] == tid]
        if (ex["reason"] == "stop_loss").any() and not (ex["reason"] == "partial_take_profit").any():
            full_sl += 1
    early = int((closed["reason"] == "early_exit_stagnation").sum())
    pf = perf.profit_factor if perf.profit_factor != float("inf") else 99.0
    return {
        "trades": perf.total_trades,
        "win_rate": perf.win_rate,
        "profit_factor": pf,
        "max_drawdown_pct": perf.max_drawdown_pct,
        "average_r": perf.average_r,
        "tp1_partials": len(partials),
        "tp1_rate": len(partials) / max(len(opens["trade_id"].unique()), 1),
        "full_sl_before_tp1": full_sl,
        "early_exits": early,
        "net_pl": float(closed["profit_loss"].sum()),
    }


def _write_report(
    path: Path,
    *,
    title: str,
    before: dict,
    after: dict,
    tracker: dict,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    lines = [f"# {title}", "", f"**Generated:** {now}", ""]

    def row(label: str, b: dict, a: dict, key: str, fmt: str = ".2f") -> str:
        bv = b.get(key, 0)
        av = a.get(key, 0)
        if fmt == ".1%":
            return f"| {label} | {bv:{fmt}} | {av:{fmt}} |"
        if fmt == "+.2f":
            return f"| {label} | {bv:{fmt}}R | {av:{fmt}}R |"
        return f"| {label} | {bv:{fmt}} | {av:{fmt}} |"

    lines.extend(
        [
            "## Before vs After",
            "",
            "| Metric | Thesis (before) | Path C (v1.1 + watch) |",
            "|--------|-------------------|-----------------|",
            row("Trades", before, after, "trades", "d"),
            row("Win rate", before, after, "win_rate", ".1%"),
            row("Profit factor", before, after, "profit_factor", ".2f"),
            row("Max DD", before, after, "max_drawdown_pct", ".2f"),
            row("Avg R", before, after, "average_r", "+.2f"),
            row("TP1 partials", before, after, "tp1_partials", "d"),
            row("TP1 rate", before, after, "tp1_rate", ".1%"),
            row("Full SL before TP1", before, after, "full_sl_before_tp1", "d"),
            row("Early exits", before, after, "early_exits", "d"),
            row("Net P/L", before, after, "net_pl", ".2f"),
            "",
        ]
    )

    if tracker:
        lines.extend(["## v1.1 doctrine tracker", ""])
        for k, v in tracker.items():
            if isinstance(v, dict):
                lines.append(f"### {k}")
                for sk, sv in v.items():
                    lines.append(f"- {sk}: **{sv}**")
            else:
                lines.append(f"- {k}: **{v}**")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_individual_trade_validation(project_root: Path | None = None) -> dict:
    root = (project_root or Path.cwd()).resolve()
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    before = _journal_metrics(logs / BASELINE_JOURNAL)

    _, _ = run_import_pipeline(root)
    universe = load_normalized_universe(root, BROKER_SYMBOLS)
    if not universe:
        payload = {"error": "no broker normalized data", "before": before}
        (logs / "individual_trade_validation.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        return payload

    reset_thesis_tracker()
    reset_individual_trade_tracker()
    reset_thesis_projection_learning_engine(root)
    ideal = ExecutionCostConfig(spread_pips=1.0, slippage_pips=0.1)
    journal = _run_backtest(
        root,
        universe=universe,
        symbols=BROKER_SYMBOLS,
        costs=ideal,
        journal_name=V11_JOURNAL,
        step=4,
    )
    after = _journal_metrics(journal)
    tracker = reset_individual_trade_tracker().summary()

    _write_report(
        logs / "individual_trade_doctrine_report.md",
        title="Individual Trade Doctrine Report",
        before=before,
        after=after,
        tracker=tracker,
    )
    _write_report(
        logs / "thesis_projection_report.md",
        title="Thesis Projection Report",
        before=before,
        after=after,
        tracker={
            "ready_now": tracker.get("ready_now", 0),
            "skip_weak": tracker.get("skip_weak", 0),
        },
    )
    _write_report(
        logs / "dynamic_exit_report.md",
        title="Dynamic Exit Report",
        before=before,
        after=after,
        tracker={"early_exits": after.get("early_exits", 0)},
    )
    _write_report(
        logs / "individual_trade_validation_report.md",
        title="Individual Trade Validation Report",
        before=before,
        after=after,
        tracker=tracker,
    )

    improved = (
        after.get("profit_factor", 0) > before.get("profit_factor", 0)
        and after.get("tp1_rate", 0) >= before.get("tp1_rate", 0)
        and after.get("full_sl_before_tp1", 999) <= before.get("full_sl_before_tp1", 0)
    )
    if after.get("profit_factor", 0) >= 1.5 and after.get("win_rate", 0) >= 0.65:
        verdict = "READY FOR DEMO FORWARD TESTING"
    elif improved:
        verdict = "REQUIRES FURTHER VALIDATION"
    else:
        verdict = "NOT READY"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "before": before,
        "after": after,
        "tracker": tracker,
        "verdict": verdict,
    }
    (logs / "individual_trade_validation.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    return payload


if __name__ == "__main__":
    result = run_individual_trade_validation()
    print(json.dumps(result, indent=2))
