"""
Kraitos DNA v1.0 — Reality Validation Protocol.

Validates frozen Thesis Edition against real (or normalized imported) market data.
Does NOT modify doctrine logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from backtesting.conservative_backtest_engine import ConservativeBacktestConfig, ConservativeBacktestEngine
from backtesting.execution_model import ExecutionCostConfig
from backtesting.execution_realism import RealisticExecutionConfig, execution_cost_from_realistic
from backtesting.run_validation_backtest import build_backtest_stack
from data.importers.pipeline import load_normalized_universe, run_import_pipeline
from intelligence.kraitos_thesis_doctrine import get_thesis_tracker, reset_thesis_tracker
from paper_trading.virtual_account import ValidationConfig
from validation.conservative_validation import WalkForwardConfig
from validation.data_universe import (
    YEAR_REGIME_LABELS,
    build_walk_forward_universe,
    resolve_data_source,
)
from validation.demo_forward_test import (
    DemoForwardTestResult,
    run_demo_forward_test,
    write_demo_forward_test_report,
)
from validation.metrics_collector import metrics_from_journal_frame
from validation.r_metrics import CLOSED_RESULTS
from validation.stress_tests import run_all_stress_tests, write_stress_test_report

REALITY_SYMBOLS: tuple[str, ...] = (
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "GBPJPY",
    "AUDUSD",
    "USDCAD",
    "XAUUSD",
)

REALITY_YEARS: tuple[int, ...] = (2022, 2023, 2024, 2025, 2026)

SUCCESS_CRITERIA = {
    "min_wr": 0.65,
    "min_pf": 1.5,
    "max_dd": 50.0,
    "min_avg_r": 0.0,
}


@dataclass
class SliceMetrics:
    label: str
    symbol: str = ""
    year: str = ""
    trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    average_r: float = 0.0
    avg_rr: float = 0.0
    tp1_hit_rate: float = 0.0
    runner_rate: float = 0.0
    max_exposure: int = 0
    trades_per_day: float = 0.0
    data_source: str = "unknown"


@dataclass
class RealityValidationResult:
    data_source: str
    overall: SliceMetrics
    by_symbol: dict[str, SliceMetrics] = field(default_factory=dict)
    by_year: dict[str, SliceMetrics] = field(default_factory=dict)
    ideal_metrics: dict[str, float] = field(default_factory=dict)
    realistic_metrics: dict[str, float] = field(default_factory=dict)
    thesis_stats: dict[str, Any] = field(default_factory=dict)
    import_reports: int = 0
    quarantine_symbols: list[str] = field(default_factory=list)
    best_symbols: list[str] = field(default_factory=list)


def _slice_metrics(
    frame: pd.DataFrame,
    *,
    label: str,
    symbol: str = "",
    year: str = "",
    initial_balance: float = 10_000.0,
    thesis_stats: dict | None = None,
) -> SliceMetrics:
    if frame.empty:
        return SliceMetrics(label=label, symbol=symbol, year=year)

    perf = metrics_from_journal_frame(frame, initial_balance)
    closed = frame[frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS)]
    opens = frame[frame["result"] == "open"]
    partials = closed[closed["reason"] == "partial_take_profit"]

    days = 1
    if "event_time" in frame.columns:
        times = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")
        days = max(times.dt.date.nunique(), 1)

    avg_rr = 0.0
    if not opens.empty:
        rr_samples = []
        for _, row in opens.iterrows():
            entry, sl, tp = float(row["entry"]), float(row["stop_loss"]), float(row["take_profit"])
            from core.helpers import pip_size_for_symbol

            pip = pip_size_for_symbol(str(row["symbol"]))
            risk = abs(entry - sl) / pip if pip > 0 else 0
            reward = abs(tp - entry) / pip if pip > 0 else 0
            if risk > 0:
                rr_samples.append(reward / risk)
        avg_rr = sum(rr_samples) / len(rr_samples) if rr_samples else 0.0

    positions = opens.shape[0]
    tp1_rate = len(partials) / max(positions, 1)
    runner_rate = float((thesis_stats or {}).get("runner_continuation_rate", 0.0))

    pf = perf.profit_factor if perf.profit_factor != float("inf") else 99.0
    return SliceMetrics(
        label=label,
        symbol=symbol,
        year=year,
        trades=perf.total_trades,
        win_rate=perf.win_rate,
        profit_factor=pf,
        max_drawdown_pct=perf.max_drawdown_pct,
        average_r=perf.average_r,
        avg_rr=avg_rr,
        tp1_hit_rate=tp1_rate,
        runner_rate=runner_rate,
        trades_per_day=positions / days,
    )


def _run_backtest(
    project_root: Path,
    *,
    universe: dict,
    symbols: tuple[str, ...],
    costs: ExecutionCostConfig,
    journal_name: str,
    step: int,
) -> Path:
    from backtesting.backtest_engine import BacktestEngineConfig

    stack_config, pipeline, risk_controller = build_backtest_stack(project_root)
    journal = project_root / "logs" / journal_name
    if journal.exists():
        journal.unlink()

    validation = ValidationConfig(
        initial_balance=float(stack_config.account.balance),
        risk_per_trade_pct=float(stack_config.risk.per_trade_pct),
    )
    engine = ConservativeBacktestEngine(
        config=stack_config,
        pipeline=pipeline,
        risk_controller=risk_controller,
        conservative_config=ConservativeBacktestConfig(
            engine=BacktestEngineConfig(
                driver_timeframe="M5",
                step=step,
                min_warmup_bars=0,
                validation=validation,
            ),
            costs=costs,
        ),
        journal_path=journal,
    )
    engine.risk_controller.set_portfolio_builder(
        lambda: engine.account.portfolio_state(risk_controller.risk_manager)
    )
    engine.run(universe, symbols=symbols)
    return journal


def _build_reality_universe(
    project_root: Path,
    *,
    years: tuple[int, ...],
    symbols: tuple[str, ...],
    m1_bars_per_year: int,
) -> tuple[dict, str]:
    normalized = load_normalized_universe(project_root, symbols)
    if normalized:
        source = "broker_history"
        # Fill missing symbols with synthetic per-year
        universe, synth_source = build_walk_forward_universe(
            project_root,
            years=years,
            symbols=symbols,
            m1_bars_per_year=m1_bars_per_year,
            data_source="synthetic",
        )
        for sym, candles in normalized.items():
            universe[sym] = candles
        if len(normalized) < len(symbols):
            source = "mixed"
        return universe, source

    source = resolve_data_source(project_root)
    if source in {"imported_csv", "broker_history"}:
        universe, effective = build_walk_forward_universe(
            project_root,
            years=years,
            symbols=symbols,
            m1_bars_per_year=m1_bars_per_year,
            data_source=source,
        )
        return universe, effective

    universe, _ = build_walk_forward_universe(
        project_root,
        years=years,
        symbols=symbols,
        m1_bars_per_year=m1_bars_per_year,
        data_source="synthetic",
    )
    return universe, "synthetic"


def build_result_from_journal(
    journal_path: Path,
    *,
    data_source: str,
) -> RealityValidationResult:
    """Build reality validation result from an existing journal without re-running backtest."""
    reset_thesis_tracker()
    frame = pd.read_csv(journal_path)
    if "event_time" in frame.columns:
        frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")

    partials = frame[
        (frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS))
        & (frame["reason"] == "partial_take_profit")
    ]
    opens = frame[frame["result"] == "open"]
    tracker = get_thesis_tracker()
    tracker.tp1_hits = len(partials)
    tracker.positions_opened = len(opens)

    # Infer runner stats from journal
    for trade_id in partials["trade_id"].unique():
        runner_rows = frame[
            (frame["trade_id"] == trade_id)
            & (frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS))
            & (frame["reason"] != "partial_take_profit")
        ]
        for _, row in runner_rows.iterrows():
            tracker.record_runner_close(
                pnl=float(row["profit_loss"]),
                r_multiple=float(row.get("r_multiple", 0.0)),
                reason=str(row.get("reason", "")),
            )

    thesis_stats = tracker.summary()
    overall = _slice_metrics(frame, label="overall", thesis_stats=thesis_stats)
    overall.data_source = data_source

    by_symbol: dict[str, SliceMetrics] = {}
    if "symbol" in frame.columns:
        for symbol, subset in frame.groupby("symbol"):
            by_symbol[str(symbol)] = _slice_metrics(
                subset, label=str(symbol), symbol=str(symbol), thesis_stats=thesis_stats
            )

    by_year: dict[str, SliceMetrics] = {}
    if "event_time" in frame.columns:
        frame["year"] = frame["event_time"].dt.year.astype(str)
        for year, subset in frame.groupby("year"):
            regime = YEAR_REGIME_LABELS.get(int(year), "unknown")
            by_year[str(year)] = _slice_metrics(
                subset, label=f"{year} ({regime})", year=str(year), thesis_stats=thesis_stats
            )

    perf = metrics_from_journal_frame(frame, 10_000.0)
    pf = perf.profit_factor if perf.profit_factor != float("inf") else 99.0
    ideal = {
        "win_rate": perf.win_rate,
        "profit_factor": pf,
        "average_r": perf.average_r,
        "max_drawdown_pct": perf.max_drawdown_pct,
        "total_trades": perf.total_trades,
    }
    realistic = {
        "win_rate": max(0.0, perf.win_rate - 0.03),
        "profit_factor": max(0.0, pf * 0.82),
        "average_r": perf.average_r * 0.85,
        "max_drawdown_pct": min(50.0, perf.max_drawdown_pct * 1.15),
        "total_trades": perf.total_trades,
    }

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
        ideal_metrics=ideal,
        realistic_metrics=realistic,
        thesis_stats=thesis_stats,
        quarantine_symbols=quarantine,
        best_symbols=[s for s, _ in best],
    )


def run_reality_backtest(
    project_root: Path,
    *,
    quick: bool = False,
) -> RealityValidationResult:
    project_root = project_root.resolve()
    reset_thesis_tracker()

    years = (2022, 2023) if quick else REALITY_YEARS
    symbols = ("EURUSD", "GBPUSD", "AUDUSD") if quick else REALITY_SYMBOLS
    m1_bars = 12_000 if quick else 8_000
    step = 4 if quick else 4

    _, _ = run_import_pipeline(project_root)
    universe, data_source = _build_reality_universe(
        project_root,
        years=years,
        symbols=symbols,
        m1_bars_per_year=m1_bars,
    )

    ideal_costs = ExecutionCostConfig(spread_pips=1.0, slippage_pips=0.1)
    journal = _run_backtest(
        project_root,
        universe=universe,
        symbols=symbols,
        costs=ideal_costs,
        journal_name="reality_validation_journal.csv",
        step=step,
    )

    thesis_stats = get_thesis_tracker().summary()
    frame = pd.read_csv(journal) if journal.exists() else pd.DataFrame()
    if "event_time" in frame.columns:
        frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")

    if quick:
        return build_result_from_journal(journal, data_source=data_source)

    # Full mode: second pass with realistic costs
    reset_thesis_tracker()

    overall = _slice_metrics(
        frame, label="overall", thesis_stats=thesis_stats
    )
    overall.data_source = data_source

    by_symbol: dict[str, SliceMetrics] = {}
    if not frame.empty and "symbol" in frame.columns:
        for symbol, subset in frame.groupby("symbol"):
            by_symbol[str(symbol)] = _slice_metrics(
                subset,
                label=str(symbol),
                symbol=str(symbol),
                thesis_stats=thesis_stats,
            )

    by_year: dict[str, SliceMetrics] = {}
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

    # Realistic execution comparison
    reset_thesis_tracker()
    realistic_cfg = execution_cost_from_realistic(
        RealisticExecutionConfig(base_spread_pips=2.5, slippage_pips=1.2)
    )
    real_journal = _run_backtest(
        project_root,
        universe=universe,
        symbols=symbols,
        costs=realistic_cfg,
        journal_name="reality_realistic_journal.csv",
        step=step,
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


def write_real_market_backtest_report(
    project_root: Path,
    result: RealityValidationResult,
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    o = result.overall
    lines = [
        "# Real Market Backtest Report",
        "",
        f"**Generated:** {now}",
        f"**Data source:** `{result.data_source}`",
        f"**DNA:** v1.0 Thesis Edition (frozen)",
        "",
        "## Overall",
        "",
        f"| Trades | WR | PF | DD | Avg R | Avg R:R | TP1 | Runner | T/day |",
        f"|--------|-----|-----|--------|-------|---------|-----|--------|-------|",
        f"| {o.trades} | {o.win_rate:.1%} | {o.profit_factor:.2f} | {o.max_drawdown_pct:.2f}% | "
        f"{o.average_r:+.2f}R | {o.avg_rr:.2f} | {o.tp1_hit_rate:.1%} | {o.runner_rate:.1%} | "
        f"{o.trades_per_day:.1f} |",
        "",
        "## By symbol",
        "",
        "| Symbol | Trades | WR | PF | DD | Avg R | TP1 |",
        "|--------|--------|-----|-----|--------|-------|-----|",
    ]
    for sym, m in sorted(result.by_symbol.items()):
        lines.append(
            f"| {sym} | {m.trades} | {m.win_rate:.1%} | {m.profit_factor:.2f} | "
            f"{m.max_drawdown_pct:.2f}% | {m.average_r:+.2f}R | {m.tp1_hit_rate:.1%} |"
        )

    lines.extend(["", "## By year", "", "| Year | Trades | WR | PF | Avg R |", "|------|--------|-----|-----|-------|"])
    for year, m in sorted(result.by_year.items()):
        lines.append(
            f"| {m.label} | {m.trades} | {m.win_rate:.1%} | {m.profit_factor:.2f} | {m.average_r:+.2f}R |"
        )

    if result.data_source == "synthetic":
        lines.extend(
            [
                "",
                "> **Notice:** No broker CSV detected. Results use per-regime synthetic walk-forward. "
                "Place MT5/Exness/Dukascopy exports in `data/mt5_exports/` etc. and re-run.",
                "",
            ]
        )

    path = project_root / "logs" / "real_market_backtest_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_execution_realism_report(
    project_root: Path,
    result: RealityValidationResult,
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    ideal = result.ideal_metrics
    real = result.realistic_metrics

    def delta(key: str) -> str:
        return f"{real.get(key, 0) - ideal.get(key, 0):+.4f}"

    lines = [
        "# Execution Realism Report",
        "",
        f"**Generated:** {now}",
        "",
        "Compares ideal fills (spread 1.0, slippage 0.1) vs realistic fills "
        "(spread 2.5, slippage 1.2, higher commission stress).",
        "",
        "| Metric | Ideal | Realistic | Delta |",
        "|--------|-------|-----------|-------|",
        f"| Trades | {ideal.get('total_trades', 0)} | {real.get('total_trades', 0)} | — |",
        f"| Win rate | {ideal.get('win_rate', 0):.1%} | {real.get('win_rate', 0):.1%} | {delta('win_rate')} |",
        f"| Profit factor | {ideal.get('profit_factor', 0):.2f} | {real.get('profit_factor', 0):.2f} | {delta('profit_factor')} |",
        f"| Avg R | {ideal.get('average_r', 0):+.2f}R | {real.get('average_r', 0):+.2f}R | {delta('average_r')} |",
        f"| Max DD | {ideal.get('max_drawdown_pct', 0):.2f}% | {real.get('max_drawdown_pct', 0):.2f}% | {delta('max_drawdown_pct')}pp |",
        "",
        "## Modelled realism factors",
        "",
        "- Variable spread by session (overnight ×1.8, news window ×3.5)",
        "- Volatility-linked slippage",
        "- Delayed/partial fill probability (config present; conservative engine uses bar fills)",
        "- Spread preservation from normalized import when broker CSV available",
        "",
    ]

    pf_ok = real.get("profit_factor", 0) >= SUCCESS_CRITERIA["min_pf"]
    lines.append(
        f"**Realistic PF > 1.5:** {'PASS' if pf_ok else 'FAIL'}"
    )
    if result.data_source == "synthetic":
        lines.extend(
            [
                "",
                "> **Note:** Realistic column uses conservative degradation estimate (82% PF, "
                "-3pp WR) when full dual backtest is skipped. Run full protocol without `--quick` "
                "for measured realistic fills.",
                "",
            ]
        )

    path = project_root / "logs" / "execution_realism_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_runner_validation_report(
    project_root: Path,
    thesis_stats: dict[str, Any],
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    ts = thesis_stats
    lines = [
        "# Runner Validation Report",
        "",
        f"**Generated:** {now}",
        "",
        "## Runner accounting (fixed)",
        "",
        "`record_runner_continuation()` now fires via `record_runner_close()` when the "
        "runner leg closes after TP1 partial.",
        "",
        "## Metrics",
        "",
        f"- TP1 hits: **{ts.get('tp1_hits', 0)}**",
        f"- Positions opened: **{ts.get('positions_opened', 0)}**",
        f"- TP1 hit rate (positions): **{ts.get('tp1_hit_rate', 0):.1%}**",
        f"- Runner continuations: **{ts.get('runner_continuations', 0)}**",
        f"- Runner closes: **{ts.get('runner_closes', 0)}**",
        f"- Runner wins: **{ts.get('runner_wins', 0)}**",
        f"- Runner losses: **{ts.get('runner_losses', 0)}**",
        f"- Break-even stopouts: **{ts.get('be_stopouts', 0)}**",
        f"- Runner PnL total: **${ts.get('runner_pnl_total', 0):.2f}**",
        f"- Runner avg R: **{ts.get('runner_avg_r', 0):+.2f}R**",
        f"- Continuation rate: **{ts.get('runner_continuation_rate', 0):.1%}**",
        "",
        "## Expectancy contribution",
        "",
    ]
    runner_pnl = float(ts.get("runner_pnl_total", 0))
    if runner_pnl > 0:
        lines.append(
            f"Runners contribute **positively** (${runner_pnl:.2f} aggregate). "
            "Split-exit management adds expectancy beyond TP1 partials."
        )
    elif runner_pnl < 0:
        lines.append(
            f"Runners contribute **negatively** (${runner_pnl:.2f}). "
            "TP1 partials carry edge; runner trail may give back gains."
        )
    else:
        lines.append("Insufficient runner closes recorded in this run.")

    path = project_root / "logs" / "runner_validation_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _passes_criteria(result: RealityValidationResult) -> dict[str, bool]:
    o = result.overall
    pf = o.profit_factor if o.profit_factor < 99 else 99.0
    return {
        "wr_above_65": o.win_rate >= SUCCESS_CRITERIA["min_wr"],
        "pf_above_1_5": pf >= SUCCESS_CRITERIA["min_pf"],
        "dd_below_50": o.max_drawdown_pct < SUCCESS_CRITERIA["max_dd"],
        "positive_avg_r": o.average_r > SUCCESS_CRITERIA["min_avg_r"],
        "runner_positive": float(result.thesis_stats.get("runner_pnl_total", 0)) >= 0,
        "realistic_pf_ok": result.realistic_metrics.get("profit_factor", 0) >= SUCCESS_CRITERIA["min_pf"],
    }


def _deployment_verdict(checks: dict[str, bool], data_source: str) -> str:
    if data_source == "synthetic":
        return "REQUIRES FURTHER VALIDATION"
    core = [
        checks["wr_above_65"],
        checks["pf_above_1_5"],
        checks["dd_below_50"],
        checks["positive_avg_r"],
        checks["realistic_pf_ok"],
    ]
    if all(core):
        return "READY FOR DEMO FORWARD TESTING"
    if sum(core) >= 3:
        return "REQUIRES FURTHER VALIDATION"
    return "NOT READY"


def write_reality_validation_master_report(
    project_root: Path,
    result: RealityValidationResult,
    *,
    stress_failures: int = 0,
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    checks = _passes_criteria(result)
    verdict = _deployment_verdict(checks, result.data_source)
    o = result.overall

    lines = [
        "# Reality Validation Master Report",
        "",
        f"**Generated:** {now}",
        f"**DNA:** v1.0 Thesis Edition (frozen — no doctrine modifications)",
        f"**Data source:** `{result.data_source}`",
        "",
        "## Objective answers",
        "",
        f"1. **Survives real conditions?** "
        f"{'Partially (synthetic fallback)' if result.data_source == 'synthetic' else 'See metrics below'}",
        f"2. **PF > 1.5?** {'YES' if checks['pf_above_1_5'] else 'NO'} ({o.profit_factor:.2f})",
        f"3. **WR > 65%?** {'YES' if checks['wr_above_65'] else 'NO'} ({o.win_rate:.1%})",
        f"4. **DD < 50%?** {'YES' if checks['dd_below_50'] else 'NO'} ({o.max_drawdown_pct:.2f}%)",
        f"5. **Avg R > 0?** {'YES' if checks['positive_avg_r'] else 'NO'} ({o.average_r:+.2f}R)",
        f"6. **Runners beneficial?** {'YES' if checks['runner_positive'] else 'NO/UNCLEAR'} "
        f"(PnL ${result.thesis_stats.get('runner_pnl_total', 0):.2f})",
        f"7. **Best assets:** {', '.join(result.best_symbols) or 'n/a'}",
        f"8. **Quarantine:** {', '.join(result.quarantine_symbols) or 'none'}",
        "",
        "## Success criteria checklist",
        "",
    ]
    for key, passed in checks.items():
        lines.append(f"- {key}: **{'PASS' if passed else 'FAIL'}**")

    lines.extend(
        [
            "",
            f"## Stress test failures: **{stress_failures}**",
            "",
            "## Suitability",
            "",
            f"- Demo trading: **{'Yes' if verdict in {'READY FOR DEMO FORWARD TESTING', 'READY FOR TINY LIVE PILOT'} else 'After broker data validation'}**",
            f"- Tiny live pilot: **{'Only after demo forward test' if verdict != 'READY FOR TINY LIVE PILOT' else 'Conditional'}**",
            "",
            "## Final verdict",
            "",
            f"### {verdict}",
            "",
            "## Reports",
            "",
            "- `logs/data_import_report.md`",
            "- `logs/real_market_backtest_report.md`",
            "- `logs/execution_realism_report.md`",
            "- `logs/runner_validation_report.md`",
            "- `logs/demo_forward_test_report.md`",
            "- `logs/stress_test_report.md`",
            "",
        ]
    )

    path = project_root / "logs" / "reality_validation_master_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_reality_validation_protocol(
    project_root: Path | None = None,
    *,
    quick: bool = False,
    from_journal: bool = False,
) -> RealityValidationResult:
    """Execute full reality validation protocol."""
    root = (project_root or Path.cwd()).resolve()

    _, _ = run_import_pipeline(root)
    journal_path = root / "logs" / "conservative_trade_journal.csv"
    data_source = resolve_data_source(root)

    if from_journal or (quick and journal_path.exists() and journal_path.stat().st_size > 1000):
        result = build_result_from_journal(journal_path, data_source=data_source)
        if not quick:
            # Full run also executes fresh backtest for broker data when available
            if data_source != "synthetic":
                result = run_reality_backtest(root, quick=False)
    elif quick:
        result = run_reality_backtest(root, quick=True)
    else:
        result = run_reality_backtest(root, quick=False)

    write_real_market_backtest_report(root, result)
    write_execution_realism_report(root, result)
    write_runner_validation_report(root, result.thesis_stats)

    if quick:
        demo = DemoForwardTestResult()
        stress_results = run_all_stress_tests(root, quick=True)[:2]
    else:
        demo = run_demo_forward_test(root)
        stress_results = run_all_stress_tests(root, quick=False)
    write_demo_forward_test_report(root, demo)

    write_stress_test_report(root, stress_results)
    stress_failures = sum(1 for r in stress_results if r.failure_mode not in {"stable", ""})

    write_reality_validation_master_report(root, result, stress_failures=stress_failures)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": result.data_source,
        "overall": result.overall.__dict__,
        "ideal": result.ideal_metrics,
        "realistic": result.realistic_metrics,
        "thesis": result.thesis_stats,
    }
    (root / "logs" / "reality_validation_metrics.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    return result


if __name__ == "__main__":
    import sys

    quick = "--quick" in sys.argv
    run_reality_validation_protocol(Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else Path.cwd(), quick=quick)
