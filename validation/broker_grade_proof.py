"""
Kraitos DNA v1.0 — Broker-Grade Proof Run.

Validates frozen Thesis Edition on imported broker CSVs only.
Does NOT modify doctrine. Reports truth when data is absent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from data.importers.base import validate_timestamp_continuity
from data.importers.pipeline import import_all_sources, load_normalized_universe, run_import_pipeline
from intelligence.kraitos_thesis_doctrine import get_thesis_tracker, reset_thesis_tracker
from backtesting.execution_model import ExecutionCostConfig
from backtesting.execution_realism import RealisticExecutionConfig, execution_cost_from_realistic
from validation.metrics_collector import metrics_from_journal_frame
from validation.conservative_validation import SNAPSHOT_M, SNAPSHOT_STORY_AWARE
from validation.reality_validation import (
    REALITY_SYMBOLS,
    REALITY_YEARS,
    RealityValidationResult,
    SUCCESS_CRITERIA,
    YEAR_REGIME_LABELS,
    _run_backtest,
    _slice_metrics,
    build_result_from_journal,
    run_reality_validation_protocol,
)

BROKER_SYMBOLS: tuple[str, ...] = (
    "EURUSD",
    "GBPUSD",
    "AUDUSD",
    "USDJPY",
    "GBPJPY",
    "XAUUSD",
)

BROKER_YEARS: tuple[int, ...] = (2022, 2023, 2024, 2025, 2026)

BROKER_FOLDERS: tuple[str, ...] = (
    "mt5_exports",
    "exness_exports",
    "dukascopy_exports",
    "normalized",
)

SNAPSHOT_THESIS = {
    "label": "Thesis Doctrine Edition",
    "trades": 4298,
    "win_rate": 0.820,
    "profit_factor": 8.53,
    "max_drawdown_pct": 2.87,
    "average_r": 0.90,
    "trades_per_day": 8.53,
}

SNAPSHOT_SYNTHETIC_REALITY = {
    "label": "Synthetic Reality Validation",
    "trades": 4298,
    "win_rate": 0.820,
    "profit_factor": 8.53,
    "max_drawdown_pct": 2.87,
    "average_r": 0.90,
    "trades_per_day": 858.0,
    "data_source": "synthetic",
}


@dataclass
class CsvInventory:
    folder: str
    path: str
    symbol_guess: str
    size_bytes: int


@dataclass
class BrokerProofState:
    folders_ok: bool
    csv_files: list[CsvInventory] = field(default_factory=list)
    normalized_symbols: list[str] = field(default_factory=list)
    import_reports: list[Any] = field(default_factory=list)
    continuity: dict[str, dict] = field(default_factory=dict)
    broker_data_present: bool = False
    validation_result: RealityValidationResult | None = None


def ensure_broker_data_folders(project_root: Path) -> dict[str, bool]:
    data = project_root / "data"
    status: dict[str, bool] = {}
    for name in BROKER_FOLDERS:
        path = data / name
        path.mkdir(parents=True, exist_ok=True)
        status[name] = path.is_dir()
    return status


def scan_import_folders(project_root: Path) -> list[CsvInventory]:
    data = project_root / "data"
    found: list[CsvInventory] = []
    scan_dirs = ("mt5_exports", "exness_exports", "dukascopy_exports", "broker_history", "imported_csv")
    for folder in scan_dirs:
        root = data / folder
        if not root.is_dir():
            continue
        for csv_path in sorted(root.rglob("*.csv")):
            sym = csv_path.stem.upper().split("_")[0].split("-")[0]
            found.append(
                CsvInventory(
                    folder=folder,
                    path=str(csv_path),
                    symbol_guess=sym,
                    size_bytes=csv_path.stat().st_size,
                )
            )
    return found


def _example_filenames() -> list[str]:
    examples = []
    for sym in BROKER_SYMBOLS:
        examples.extend(
            [
                f"data/mt5_exports/{sym}_M1.csv",
                f"data/mt5_exports/{sym}.csv",
                f"data/exness_exports/{sym}-M1.csv",
                f"data/dukascopy_exports/{sym}_dukascopy_m1.csv",
            ]
        )
    return examples


def write_broker_data_missing_report(project_root: Path, state: BrokerProofState) -> Path:
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Broker Data Missing Report",
        "",
        f"**Generated:** {now}",
        f"**DNA:** v1.0 Thesis Edition (frozen)",
        "",
        "## Status: BROKER DATA NOT FOUND",
        "",
        "Broker-grade proof run **cannot proceed**. No CSV files were detected in import folders.",
        "",
        "## Folder status",
        "",
    ]
    for folder in BROKER_FOLDERS:
        exists = (project_root / "data" / folder).is_dir()
        lines.append(f"- `data/{folder}/` — **{'exists' if exists else 'MISSING'}** (empty)")

    lines.extend(
        [
            "",
            "## Required symbols",
            "",
        ]
    )
    for sym in BROKER_SYMBOLS:
        lines.append(f"- **{sym}**")

    lines.extend(
        [
            "",
            "## Required timeframe",
            "",
            "**M1 (1-minute OHLCV)** — UTC timestamps preferred",
            "",
            "## Required years",
            "",
        ]
    )
    for year in BROKER_YEARS:
        label = f"{year} YTD" if year == 2026 else str(year)
        lines.append(f"- **{label}**")

    lines.extend(
        [
            "",
            "## Required columns",
            "",
            "`time/timestamp, open, high, low, close, volume` (optional: `spread` or `spread_pips`)",
            "",
            "## Example filenames",
            "",
        ]
    )
    for ex in _example_filenames()[:12]:
        lines.append(f"- `{ex}`")
    lines.append(f"- _(and similar for remaining symbols — {len(BROKER_SYMBOLS)} total)_")

    lines.extend(
        [
            "",
            "## Scanned inventory",
            "",
            f"CSV files found: **{len(state.csv_files)}**",
            "",
            "## Next steps",
            "",
            "1. Export M1 history from MT5, Exness, or Dukascopy for each symbol",
            "2. Place files in the appropriate `data/*_exports/` folder",
            "3. Re-run: `python -m validation.broker_grade_proof`",
            "",
            "> **Do not** substitute synthetic data for broker proof. Kraitos must be judged on real imports.",
            "",
        ]
    )

    path = logs / "broker_data_missing_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _classify_symbol(metrics: dict | None) -> str:
    if metrics is None or metrics.get("trades", 0) < 8:
        return "NOT ENOUGH DATA"
    pf = float(metrics.get("profit_factor", 0))
    avg_r = float(metrics.get("average_r", 0))
    wr = float(metrics.get("win_rate", 0))
    if pf >= 1.5 and avg_r > 0 and wr >= 0.65:
        return "CORE TRADEABLE"
    if pf >= 1.0 and avg_r >= 0:
        return "CONDITIONAL"
    if metrics.get("trades", 0) >= 8:
        return "QUARANTINE"
    return "NOT ENOUGH DATA"


def _snapshot_row(s: dict) -> str:
    return (
        f"| {s['label']} | {s['trades']} | {s['win_rate']:.1%} | "
        f"{s['profit_factor']:.2f} | {s['max_drawdown_pct']:.2f}% | {s['average_r']:+.2f}R |"
    )


def _passes_criteria(result: RealityValidationResult | None) -> dict[str, bool]:
    if result is None:
        return {k: False for k in ("wr", "pf", "dd", "avg_r", "runner", "no_catastrophic")}
    o = result.overall
    pf = min(o.profit_factor, 99.0)
    runner_pnl = float(result.thesis_stats.get("runner_pnl_total", 0))
    catastrophic = any(
        s in result.quarantine_symbols
        for s in BROKER_SYMBOLS
        if result.by_symbol.get(s, None) and result.by_symbol[s].trades >= 30
    )
    return {
        "wr": o.win_rate >= SUCCESS_CRITERIA["min_wr"],
        "pf": pf >= SUCCESS_CRITERIA["min_pf"],
        "dd": o.max_drawdown_pct < SUCCESS_CRITERIA["max_dd"],
        "avg_r": o.average_r > SUCCESS_CRITERIA["min_avg_r"],
        "runner": runner_pnl >= 0,
        "no_catastrophic": not catastrophic,
    }


def _verdict(passes: dict[str, bool], broker_present: bool) -> str:
    if not broker_present:
        return "NOT READY"
    if all(passes.values()):
        return "READY FOR DEMO FORWARD TESTING"
    if passes.get("pf") and passes.get("dd") and passes.get("avg_r"):
        return "REQUIRES FURTHER VALIDATION"
    return "NOT READY"


def write_broker_data_import_report(
    project_root: Path,
    state: BrokerProofState,
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Broker Data Import Report",
        "",
        f"**Generated:** {now}",
        "",
        f"**Broker CSV files found:** {len(state.csv_files)}",
        f"**Normalized symbols:** {', '.join(state.normalized_symbols) or '(none)'}",
        "",
    ]
    if not state.broker_data_present:
        lines.extend(
            [
                "## Result",
                "",
                "**BLOCKED** — no broker CSVs imported. See `broker_data_missing_report.md`.",
                "",
            ]
        )
    else:
        lines.extend(["## Import results", ""])
        for report in state.import_reports:
            status = "OK" if getattr(report, "ok", False) else "FAIL"
            lines.append(f"### {report.symbol} ({report.source}) — {status}")
            lines.append(f"- Input: `{report.input_path}`")
            lines.append(f"- Output: `{report.output_path}`")
            lines.append(
                f"- Rows: {report.rows_read} → {report.rows_written} "
                f"(dupes: {report.duplicates_removed}, gaps filled: {report.missing_filled})"
            )
            cont = state.continuity.get(report.symbol, {})
            if cont:
                lines.append(f"- Continuity: {cont.get('bars', 0)} bars, "
                             f"gaps>{60}min: {cont.get('gaps_over_threshold', 0)}, "
                             f"years: {cont.get('year_coverage', {})}")
            lines.append("")

    path = project_root / "logs" / "broker_data_import_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_broker_real_market_backtest_report(
    project_root: Path,
    state: BrokerProofState,
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Broker Real Market Backtest Report",
        "",
        f"**Generated:** {now}",
        "",
    ]
    if not state.broker_data_present or state.validation_result is None:
        lines.extend(
            [
                "## Status: NOT RUN",
                "",
                "Broker-grade backtest requires imported CSV data. **No broker metrics produced.**",
                "",
                "## Reference only — prior synthetic validation (NOT broker proof)",
                "",
                "| Edition | Trades | WR | PF | DD | Avg R |",
                "|---------|--------|-----|-----|--------|-------|",
                _snapshot_row(SNAPSHOT_M),
                _snapshot_row(SNAPSHOT_STORY_AWARE),
                _snapshot_row(SNAPSHOT_THESIS),
                _snapshot_row(SNAPSHOT_SYNTHETIC_REALITY),
                "",
            ]
        )
    else:
        r = state.validation_result
        o = r.overall
        lines.extend(
            [
                f"**Data source:** `{r.data_source}`",
                "",
                "## Overall",
                "",
                f"| Trades | WR | PF | DD | Avg R | Avg R:R | TP1 | Runner | T/active day |",
                f"|--------|-----|-----|--------|-------|---------|-----|--------|--------------|",
                f"| {o.trades} | {o.win_rate:.1%} | {o.profit_factor:.2f} | {o.max_drawdown_pct:.2f}% | "
                f"{o.average_r:+.2f}R | {o.avg_rr:.2f} | {o.tp1_hit_rate:.1%} | {o.runner_rate:.1%} | "
                f"{o.trades_per_day:.1f} |",
                "",
                "## By symbol",
                "",
                "| Symbol | Trades | WR | PF | DD | Avg R | TP1 | Class |",
                "|--------|--------|-----|-----|--------|-------|-----|-------|",
            ]
        )
        for sym in BROKER_SYMBOLS:
            m = r.by_symbol.get(sym)
            if m is None:
                lines.append(f"| {sym} | 0 | — | — | — | — | — | NOT ENOUGH DATA |")
                continue
            cls = _classify_symbol(m.__dict__)
            lines.append(
                f"| {sym} | {m.trades} | {m.win_rate:.1%} | {m.profit_factor:.2f} | "
                f"{m.max_drawdown_pct:.2f}% | {m.average_r:+.2f}R | {m.tp1_hit_rate:.1%} | {cls} |"
            )
        lines.extend(["", "## By year", "", "| Year | Trades | WR | PF | Avg R |", "|------|--------|-----|-----|-------|"])
        for year, m in sorted(r.by_year.items()):
            lines.append(
                f"| {m.label} | {m.trades} | {m.win_rate:.1%} | {m.profit_factor:.2f} | {m.average_r:+.2f}R |"
            )

    path = project_root / "logs" / "broker_real_market_backtest_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_broker_execution_realism_report(
    project_root: Path,
    state: BrokerProofState,
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Broker Execution Realism Report",
        "",
        f"**Generated:** {now}",
        "",
    ]
    if not state.broker_data_present or state.validation_result is None:
        lines.extend(
            [
                "## Status: NOT RUN",
                "",
                "Ideal vs realistic fill comparison requires broker backtest. **Blocked.**",
                "",
                "Synthetic reference (estimated realistic degradation):",
                "",
                "| Metric | Ideal | Realistic (est.) |",
                "|--------|-------|------------------|",
                "| PF | 8.53 | 7.00 |",
                "| WR | 82.0% | 79.0% |",
                "| Avg R | +0.90R | +0.76R |",
                "",
            ]
        )
    else:
        r = state.validation_result
        ideal = r.ideal_metrics
        real = r.realistic_metrics
        lines.extend(
            [
                "## Ideal vs realistic fills (broker data)",
                "",
                "| Metric | Ideal | Realistic | Delta |",
                "|--------|-------|-----------|-------|",
                f"| WR | {ideal.get('win_rate', 0):.1%} | {real.get('win_rate', 0):.1%} | "
                f"{real.get('win_rate', 0) - ideal.get('win_rate', 0):+.1%} |",
                f"| PF | {ideal.get('profit_factor', 0):.2f} | {real.get('profit_factor', 0):.2f} | "
                f"{real.get('profit_factor', 0) - ideal.get('profit_factor', 0):+.2f} |",
                f"| Avg R | {ideal.get('average_r', 0):+.2f}R | {real.get('average_r', 0):+.2f}R | "
                f"{real.get('average_r', 0) - ideal.get('average_r', 0):+.2f}R |",
                f"| Max DD | {ideal.get('max_drawdown_pct', 0):.2f}% | {real.get('max_drawdown_pct', 0):.2f}% | — |",
                "",
                "### Spread / slippage impact",
                "",
                "Measured via dual backtest: ideal (spread 1.0, slip 0.1) vs realistic (spread 2.5, slip 1.2).",
                "",
            ]
        )

    path = project_root / "logs" / "broker_execution_realism_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_broker_runner_validation_report(
    project_root: Path,
    state: BrokerProofState,
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    ts = (state.validation_result.thesis_stats if state.validation_result else {}) or {}
    lines = [
        "# Broker Runner Validation Report",
        "",
        f"**Generated:** {now}",
        "",
    ]
    if not state.broker_data_present:
        lines.extend(
            [
                "## Status: NOT RUN",
                "",
                "Runner validation on broker data blocked — no imports.",
                "",
                "Synthetic reference (Thesis validation journal):",
                "",
                f"- TP1 hit rate: **67.6%**",
                f"- Runner PnL: **$329.18**",
                f"- Runner avg R: **+1.94R**",
                f"- Runner closes recorded: **8** (journal gap — most runners close at backtest end without row)",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"- TP1 hits: **{ts.get('tp1_hits', 0)}**",
                f"- TP1 rate: **{ts.get('tp1_hit_rate', 0):.1%}**",
                f"- Runner PnL: **${ts.get('runner_pnl_total', 0):.2f}**",
                f"- Runner avg R: **{ts.get('runner_avg_r', 0):+.2f}R**",
                f"- Runner wins/losses: **{ts.get('runner_wins', 0)}/{ts.get('runner_losses', 0)}**",
                f"- BE stopouts: **{ts.get('be_stopouts', 0)}**",
                "",
            ]
        )
        contrib = float(ts.get("runner_pnl_total", 0))
        if contrib > 0:
            lines.append("Runners contribute **positively** to broker-grade expectancy.")
        elif contrib < 0:
            lines.append("Runners contribute **negatively** on broker data.")
        else:
            lines.append("Runner contribution **unclear** — insufficient closes recorded.")

    path = project_root / "logs" / "broker_runner_validation_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_broker_stress_test_report(project_root: Path, state: BrokerProofState) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    stress_path = project_root / "logs" / "stress_test_report.md"
    lines = [
        "# Broker Stress Test Report",
        "",
        f"**Generated:** {now}",
        "",
    ]
    if not state.broker_data_present:
        lines.extend(
            [
                "## Status: NOT RUN ON BROKER DATA",
                "",
                "Stress matrix uses synthetic scenario candles. Not valid as broker proof.",
                "",
            ]
        )
        if stress_path.exists():
            lines.append("See `stress_test_report.md` for synthetic stress reference only.")
    elif stress_path.exists():
        lines.append("Full stress results: see `stress_test_report.md` from reality validation run.")
    else:
        lines.append("Stress tests pending — run with broker data loaded.")

    path = project_root / "logs" / "broker_stress_test_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_broker_grade_master_report(
    project_root: Path,
    state: BrokerProofState,
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    passes = _passes_criteria(state.validation_result)
    verdict = _verdict(passes, state.broker_data_present)

    lines = [
        "# Broker-Grade Master Report",
        "",
        f"**Generated:** {now}",
        f"**DNA:** v1.0 Thesis Edition (frozen — no doctrine changes)",
        "",
        "## Executive summary",
        "",
    ]
    if not state.broker_data_present:
        lines.extend(
            [
                "**Broker-grade proof run did not execute.** Zero CSV files found in import folders. "
                "Kraitos cannot be validated on real market data until M1 broker exports are provided.",
                "",
                f"### Final verdict: **{verdict}**",
                "",
                "Reason: No broker data — proof run blocked by design (no synthetic substitution).",
                "",
            ]
        )
    else:
        r = state.validation_result
        o = r.overall if r else None
        lines.extend(
            [
                f"Broker data source: **{r.data_source if r else 'unknown'}**",
                f"Overall: WR {o.win_rate:.1%}, PF {o.profit_factor:.2f}, DD {o.max_drawdown_pct:.2f}%, "
                f"Avg R {o.average_r:+.2f}R" if o else "",
                "",
                f"### Final verdict: **{verdict}**",
                "",
            ]
        )

    lines.extend(
        [
            "## Comparison vs prior editions",
            "",
            "| Edition | Trades | WR | PF | DD | Avg R |",
            "|---------|--------|-----|-----|--------|-------|",
            _snapshot_row(SNAPSHOT_M),
            _snapshot_row(SNAPSHOT_STORY_AWARE),
            _snapshot_row(SNAPSHOT_THESIS),
            _snapshot_row(SNAPSHOT_SYNTHETIC_REALITY),
        ]
    )
    if state.validation_result:
        o = state.validation_result.overall
        lines.append(
            f"| **Broker Proof (this run)** | {o.trades} | {o.win_rate:.1%} | "
            f"{o.profit_factor:.2f} | {o.max_drawdown_pct:.2f}% | {o.average_r:+.2f}R |"
        )
    else:
        lines.append("| **Broker Proof (this run)** | — | — | — | — | — |")

    lines.extend(
        [
            "",
            "> Synthetic editions are **reference only**. Broker proof requires imported CSV results in the row above.",
            "",
            "## Pass criteria",
            "",
        ]
    )
    for key, ok in passes.items():
        lines.append(f"- {key}: **{'PASS' if ok else 'FAIL / N/A'}**")

    lines.extend(["", "## Asset classification", "", "| Symbol | Classification |", "|--------|----------------|"])
    if state.validation_result:
        for sym in BROKER_SYMBOLS:
            m = state.validation_result.by_symbol.get(sym)
            cls = _classify_symbol(m.__dict__ if m else None)
            lines.append(f"| {sym} | {cls} |")
    else:
        for sym in BROKER_SYMBOLS:
            lines.append(f"| {sym} | NOT ENOUGH DATA |")

    lines.extend(
        [
            "",
            "## Reports",
            "",
            "- `logs/broker_data_missing_report.md` (if applicable)",
            "- `logs/broker_data_import_report.md`",
            "- `logs/broker_real_market_backtest_report.md`",
            "- `logs/broker_execution_realism_report.md`",
            "- `logs/broker_runner_validation_report.md`",
            "- `logs/broker_stress_test_report.md`",
            "",
        ]
    )

    path = project_root / "logs" / "broker_grade_master_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _available_broker_symbols(project_root: Path) -> tuple[str, ...]:
    normalized = project_root / "data" / "normalized"
    return tuple(
        s for s in BROKER_SYMBOLS if (normalized / f"{s}_M1.csv").is_file()
    )


def run_partial_broker_validation(project_root: Path) -> RealityValidationResult | None:
    """Run backtest on imported broker CSVs only — no synthetic symbol/year fill."""
    root = project_root.resolve()
    _, _ = run_import_pipeline(root)
    available = _available_broker_symbols(root)
    if not available:
        return None

    universe = load_normalized_universe(root, available)
    missing = [s for s in BROKER_SYMBOLS if s not in available]
    data_source = (
        f"broker_partial ({len(available)}/{len(BROKER_SYMBOLS)} symbols: "
        f"{', '.join(available)}; missing: {', '.join(missing) or 'none'})"
    )

    reset_thesis_tracker()
    ideal_costs = ExecutionCostConfig(spread_pips=1.0, slippage_pips=0.1)
    journal = _run_backtest(
        root,
        universe=universe,
        symbols=available,
        costs=ideal_costs,
        journal_name="broker_partial_journal.csv",
        step=12,
    )

    thesis_stats = get_thesis_tracker().summary()
    frame = pd.read_csv(journal) if journal.exists() else pd.DataFrame()
    if "event_time" in frame.columns:
        frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")

    overall = _slice_metrics(frame, label="overall", thesis_stats=thesis_stats)
    overall.data_source = data_source

    by_symbol: dict[str, Any] = {}
    if not frame.empty and "symbol" in frame.columns:
        for symbol, subset in frame.groupby("symbol"):
            by_symbol[str(symbol)] = _slice_metrics(
                subset, label=str(symbol), symbol=str(symbol), thesis_stats=thesis_stats
            )

    by_year: dict[str, Any] = {}
    if not frame.empty and "event_time" in frame.columns:
        frame["year"] = frame["event_time"].dt.year.astype(str)
        for year, subset in frame.groupby("year"):
            regime = YEAR_REGIME_LABELS.get(int(year), "unknown")
            by_year[str(year)] = _slice_metrics(
                subset,
                label=f"{year} ({regime})",
                year=str(year),
                thesis_stats=thesis_stats,
            )

    reset_thesis_tracker()
    realistic_cfg = execution_cost_from_realistic(
        RealisticExecutionConfig(base_spread_pips=2.5, slippage_pips=1.2)
    )
    real_journal = _run_backtest(
        root,
        universe=universe,
        symbols=available,
        costs=realistic_cfg,
        journal_name="broker_partial_realistic_journal.csv",
        step=12,
    )
    ideal_perf = metrics_from_journal_frame(frame, 10_000.0) if not frame.empty else None
    real_frame = pd.read_csv(real_journal) if real_journal.exists() else pd.DataFrame()
    real_perf = metrics_from_journal_frame(real_frame, 10_000.0) if not real_frame.empty else None

    quarantine = [
        s for s, m in by_symbol.items()
        if m.trades >= 8 and (m.profit_factor < 1.0 or m.average_r < 0)
    ]
    best = sorted(
        by_symbol.items(),
        key=lambda x: x[1].profit_factor * max(x[1].average_r, 0.01),
        reverse=True,
    )[:3]

    return RealityValidationResult(
        data_source=data_source,
        overall=overall,
        by_symbol=by_symbol,
        by_year=by_year,
        ideal_metrics={
            "win_rate": ideal_perf.win_rate if ideal_perf else 0.0,
            "profit_factor": ideal_perf.profit_factor if ideal_perf else 0.0,
            "average_r": ideal_perf.average_r if ideal_perf else 0.0,
            "max_drawdown_pct": ideal_perf.max_drawdown_pct if ideal_perf else 0.0,
            "total_trades": ideal_perf.total_trades if ideal_perf else 0,
        },
        realistic_metrics={
            "win_rate": real_perf.win_rate if real_perf else 0.0,
            "profit_factor": real_perf.profit_factor if real_perf else 0.0,
            "average_r": real_perf.average_r if real_perf else 0.0,
            "max_drawdown_pct": real_perf.max_drawdown_pct if real_perf else 0.0,
            "total_trades": real_perf.total_trades if real_perf else 0,
        },
        thesis_stats=thesis_stats,
        quarantine_symbols=quarantine,
        best_symbols=[s for s, _ in best],
    )


def run_broker_grade_proof(project_root: Path | None = None, *, force: bool = False) -> BrokerProofState:
    """Execute broker-grade proof run."""
    from validation.broker_data_readiness import run_broker_data_readiness

    root = (project_root or Path.cwd()).resolve()
    state = BrokerProofState(folders_ok=True)
    ensure_broker_data_folders(root)
    state.csv_files = scan_import_folders(root)
    state.broker_data_present = len(state.csv_files) > 0

    readiness = run_broker_data_readiness(root)
    if not readiness.all_ready and not force:
        if not state.broker_data_present:
            write_broker_data_missing_report(root, state)
        write_broker_data_import_report(root, state)
        write_broker_real_market_backtest_report(root, state)
        write_broker_execution_realism_report(root, state)
        write_broker_runner_validation_report(root, state)
        write_broker_stress_test_report(root, state)
        write_broker_grade_master_report(root, state)
        print("BROKER PROOF BLOCKED — data not ready.")
        print("Run: python -m validation.broker_data_readiness")
        print("Or with current files: python -m validation.broker_grade_proof --force")
        print(f"Report: {readiness.report_path}")
        return state

    if not readiness.all_ready and force:
        print("BROKER PROOF — running with partial data (--force)")
        print(f"Ready: {readiness.ready_count}/{len(readiness.symbols)} symbols")
        print(f"Report: {readiness.report_path}")

    if not state.broker_data_present:
        write_broker_data_missing_report(root, state)
    else:
        reports = import_all_sources(root)
        state.import_reports = reports
        normalized_dir = root / "data" / "normalized"
        for report in reports:
            if not report.ok:
                continue
            state.normalized_symbols.append(report.symbol)
            out = normalized_dir / f"{report.symbol}_M1.csv"
            if out.exists():
                frame = pd.read_csv(out)
                state.continuity[report.symbol] = validate_timestamp_continuity(frame)

        # Full reality validation — no --quick, no journal shortcut
        if force:
            state.validation_result = run_partial_broker_validation(root)
        else:
            state.validation_result = run_reality_validation_protocol(
                root, quick=False, from_journal=False
            )

    write_broker_data_import_report(root, state)
    write_broker_real_market_backtest_report(root, state)
    write_broker_execution_realism_report(root, state)
    write_broker_runner_validation_report(root, state)
    write_broker_stress_test_report(root, state)
    master = write_broker_grade_master_report(root, state)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "broker_data_present": state.broker_data_present,
        "csv_files_found": len(state.csv_files),
        "normalized_symbols": state.normalized_symbols,
        "verdict": _verdict(_passes_criteria(state.validation_result), state.broker_data_present),
        "master_report": str(master),
    }
    (root / "logs" / "broker_grade_proof.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    return state


if __name__ == "__main__":
    import sys

    force = "--force" in sys.argv
    run_broker_grade_proof(force=force)
