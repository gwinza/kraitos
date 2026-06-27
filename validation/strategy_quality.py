"""Analyze conservative journal quality and build runtime strategy filters."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from backtesting.performance_report import PerformanceMetrics
from validation.data_universe import YEAR_REGIME_LABELS
from validation.metrics_collector import metrics_from_journal_frame
from validation.r_metrics import CLOSED_RESULTS, average_r_from_closed_frame

from controls.strategy_quality_gate import FILTERS_PATH, PF_QUARANTINE, load_strategy_quality_filters

MIN_BUCKET_TRADES = 8
PF_FULL_RISK = 1.3
DD_FULL_RISK_PCT = 10.0
DRAWDOWN_STRICT_PCT = 10.0


@dataclass
class BucketMetrics:
    """Performance stats for a symbol/year/regime/mode slice."""

    label: str
    total_trades: int
    win_rate: float
    profit_factor: float
    average_r: float
    max_drawdown_pct: float
    net_profit: float
    expectancy: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 4)
            if self.profit_factor != float("inf")
            else "inf",
            "average_r": round(self.average_r, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "net_profit": round(self.net_profit, 2),
            "expectancy": round(self.expectancy, 4),
        }


@dataclass
class StrategyQualityAnalysis:
    """Full analysis output from a conservative journal."""

    generated_at: str
    journal_path: str
    overall: BucketMetrics
    by_symbol: dict[str, BucketMetrics] = field(default_factory=dict)
    by_year: dict[str, BucketMetrics] = field(default_factory=dict)
    by_regime: dict[str, BucketMetrics] = field(default_factory=dict)
    by_mode: dict[str, BucketMetrics] = field(default_factory=dict)
    by_symbol_mode: dict[str, BucketMetrics] = field(default_factory=dict)
    disabled_symbols: list[str] = field(default_factory=list)
    quarantined_symbol_modes: list[str] = field(default_factory=list)
    disabled_regimes: list[str] = field(default_factory=list)
    symbol_risk_multipliers: dict[str, float] = field(default_factory=dict)

    def to_filters_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "journal_path": self.journal_path,
            "disabled_symbols": self.disabled_symbols,
            "quarantined_symbol_modes": self.quarantined_symbol_modes,
            "disabled_regimes": self.disabled_regimes,
            "symbol_risk_multipliers": self.symbol_risk_multipliers,
            "thresholds": {
                "pf_quarantine": PF_QUARANTINE,
                "pf_full_risk": PF_FULL_RISK,
                "dd_full_risk_pct": DD_FULL_RISK_PCT,
                "drawdown_strict_pct": DRAWDOWN_STRICT_PCT,
                "min_bucket_trades": MIN_BUCKET_TRADES,
            },
            "by_symbol": {k: v.to_dict() for k, v in self.by_symbol.items()},
            "by_regime": {k: v.to_dict() for k, v in self.by_regime.items()},
        }


def analyze_conservative_journal(
    journal_path: Path,
    *,
    initial_balance: float = 10_000.0,
) -> StrategyQualityAnalysis:
    """Compute bucket metrics and derive strategy quality filters."""
    path = journal_path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Journal not found: {path}")

    frame = pd.read_csv(path)
    closed = _closed_frame(frame)
    if closed.empty:
        return StrategyQualityAnalysis(
            generated_at=datetime.now(timezone.utc).isoformat(),
            journal_path=str(path),
            overall=_empty_bucket("overall"),
        )

    closed = closed.copy()
    closed["event_time"] = pd.to_datetime(closed["event_time"], utc=True, errors="coerce")
    closed["year"] = closed["event_time"].dt.year.astype(str)
    closed["regime"] = closed["year"].map(
        lambda y: YEAR_REGIME_LABELS.get(int(y), "unknown") if y.isdigit() else "unknown"
    )

    overall = _bucket_metrics(closed, "overall", initial_balance)
    by_symbol = {
        str(symbol): _bucket_metrics(subset, str(symbol), initial_balance)
        for symbol, subset in closed.groupby("symbol")
    }
    by_year = {
        str(year): _bucket_metrics(subset, str(year), initial_balance)
        for year, subset in closed.groupby("year")
    }
    by_regime = {
        str(regime): _bucket_metrics(subset, str(regime), initial_balance)
        for regime, subset in closed.groupby("regime")
    }
    by_mode = {
        str(mode): _bucket_metrics(subset, str(mode), initial_balance)
        for mode, subset in closed.groupby("mode")
    }
    by_symbol_mode: dict[str, BucketMetrics] = {}
    for (symbol, mode), subset in closed.groupby(["symbol", "mode"]):
        key = f"{symbol}:{mode}"
        by_symbol_mode[key] = _bucket_metrics(subset, key, initial_balance)

    disabled_symbols: list[str] = []
    quarantined: list[str] = []
    disabled_regimes: list[str] = []
    multipliers: dict[str, float] = {}

    for symbol, metrics in by_symbol.items():
        if metrics.total_trades < MIN_BUCKET_TRADES:
            multipliers[symbol] = 1.0
            continue
        if metrics.expectancy < 0 or metrics.net_profit < 0:
            disabled_symbols.append(symbol)
            multipliers[symbol] = 0.0
            continue
        multipliers[symbol] = _adaptive_multiplier(
            metrics.profit_factor,
            metrics.max_drawdown_pct,
        )
        if metrics.profit_factor < PF_QUARANTINE:
            if symbol not in disabled_symbols:
                disabled_symbols.append(symbol)
            multipliers[symbol] = 0.0

    for key, metrics in by_symbol_mode.items():
        if metrics.total_trades < MIN_BUCKET_TRADES:
            continue
        if metrics.profit_factor < PF_QUARANTINE or metrics.expectancy < 0:
            quarantined.append(key)

    for regime, metrics in by_regime.items():
        if metrics.total_trades < MIN_BUCKET_TRADES:
            continue
        if metrics.expectancy < 0 or metrics.net_profit < 0:
            disabled_regimes.append(regime)

    return StrategyQualityAnalysis(
        generated_at=datetime.now(timezone.utc).isoformat(),
        journal_path=str(path),
        overall=overall,
        by_symbol=by_symbol,
        by_year=by_year,
        by_regime=by_regime,
        by_mode=by_mode,
        by_symbol_mode=by_symbol_mode,
        disabled_symbols=sorted(set(disabled_symbols)),
        quarantined_symbol_modes=sorted(set(quarantined)),
        disabled_regimes=sorted(set(disabled_regimes)),
        symbol_risk_multipliers=multipliers,
    )


def write_strategy_quality_reports(
    project_root: Path,
    analysis: StrategyQualityAnalysis,
) -> tuple[Path, Path, Path]:
    """Write strategy, symbol, and regime expectancy markdown reports."""
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    strategy_path = logs / "strategy_quality_report.md"
    symbol_path = logs / "symbol_expectancy_report.md"
    regime_path = logs / "regime_expectancy_report.md"

    strategy_path.write_text(_strategy_quality_markdown(analysis), encoding="utf-8")
    symbol_path.write_text(_symbol_expectancy_markdown(analysis), encoding="utf-8")
    regime_path.write_text(_regime_expectancy_markdown(analysis), encoding="utf-8")
    return strategy_path, symbol_path, regime_path


def save_strategy_quality_filters(
    project_root: Path,
    analysis: StrategyQualityAnalysis,
) -> Path:
    """Persist runtime filter configuration."""
    path = project_root / "logs" / FILTERS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(analysis.to_filters_dict(), handle, indent=2)
    return path


def refresh_strategy_quality_from_journal(
    project_root: Path,
    *,
    journal_name: str = "conservative_trade_journal.csv",
    initial_balance: float = 10_000.0,
) -> StrategyQualityAnalysis:
    """Analyze journal, write reports and filters."""
    journal = project_root / "logs" / journal_name
    analysis = analyze_conservative_journal(journal, initial_balance=initial_balance)
    write_strategy_quality_reports(project_root, analysis)
    save_strategy_quality_filters(project_root, analysis)
    return analysis


def _closed_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS)].copy()


def _bucket_metrics(
    closed: pd.DataFrame,
    label: str,
    initial_balance: float,
) -> BucketMetrics:
    if closed.empty:
        return _empty_bucket(label)

    perf = metrics_from_journal_frame(closed, initial_balance)
    pnls = pd.to_numeric(closed["profit_loss"], errors="coerce").fillna(0.0)
    expectancy = float(pnls.mean()) if len(pnls) else 0.0
    net_profit = float(pnls.sum())
    pf = perf.profit_factor if perf.profit_factor != float("inf") else 999.0

    return BucketMetrics(
        label=label,
        total_trades=perf.total_trades,
        win_rate=perf.win_rate,
        profit_factor=pf,
        average_r=perf.average_r,
        max_drawdown_pct=perf.max_drawdown_pct,
        net_profit=net_profit,
        expectancy=expectancy,
    )


def _empty_bucket(label: str) -> BucketMetrics:
    return BucketMetrics(
        label=label,
        total_trades=0,
        win_rate=0.0,
        profit_factor=0.0,
        average_r=0.0,
        max_drawdown_pct=0.0,
        net_profit=0.0,
        expectancy=0.0,
    )


def _adaptive_multiplier(profit_factor: float, max_drawdown_pct: float) -> float:
    if profit_factor < PF_QUARANTINE:
        return 0.0
    if profit_factor < PF_FULL_RISK:
        return 0.5
    if max_drawdown_pct <= DD_FULL_RISK_PCT:
        return 1.0
    return 0.5


def _rank_buckets(buckets: dict[str, BucketMetrics], key: str) -> list[tuple[str, BucketMetrics]]:
    metric_getters = {
        "profit_factor": lambda m: m.profit_factor,
        "average_r": lambda m: m.average_r,
        "win_rate": lambda m: m.win_rate,
        "max_drawdown_pct": lambda m: -m.max_drawdown_pct,
        "net_profit": lambda m: m.net_profit,
        "expectancy": lambda m: m.expectancy,
    }
    getter = metric_getters.get(key, lambda m: m.net_profit)
    return sorted(buckets.items(), key=lambda item: getter(item[1]), reverse=True)


def _strategy_quality_markdown(analysis: StrategyQualityAnalysis) -> str:
    lines = [
        "# Kraitos Strategy Quality Report",
        "",
        f"**Generated:** {analysis.generated_at}",
        f"**Journal:** `{analysis.journal_path}`",
        "",
        "## Overall conservative performance",
        "",
        _format_bucket(analysis.overall),
        "",
        "## Active filters",
        "",
        f"- Disabled symbols: **{', '.join(analysis.disabled_symbols) or 'none'}**",
        f"- Quarantined symbol:mode: **{', '.join(analysis.quarantined_symbol_modes) or 'none'}**",
        f"- Disabled regimes: **{', '.join(analysis.disabled_regimes) or 'none'}**",
        "",
        "### Adaptive risk multipliers",
        "",
    ]
    for symbol, mult in sorted(analysis.symbol_risk_multipliers.items()):
        lines.append(f"- **{symbol}**: {mult:.0%} risk")
    lines.extend(["", "## Best / worst by dimension", ""])
    for title, buckets, metric in (
        ("Symbol", analysis.by_symbol, "profit_factor"),
        ("Year", analysis.by_year, "net_profit"),
        ("Regime", analysis.by_regime, "average_r"),
        ("Mode", analysis.by_mode, "profit_factor"),
    ):
        if not buckets:
            continue
        ranked = _rank_buckets(buckets, metric)
        best = ranked[0]
        worst = ranked[-1]
        lines.append(f"### {title}")
        lines.append(f"- Best ({metric}): **{best[0]}** — {_one_line_bucket(best[1])}")
        lines.append(f"- Worst ({metric}): **{worst[0]}** — {_one_line_bucket(worst[1])}")
        lines.append("")
    return "\n".join(lines)


def _symbol_expectancy_markdown(analysis: StrategyQualityAnalysis) -> str:
    lines = [
        "# Symbol Expectancy Report",
        "",
        f"**Generated:** {analysis.generated_at}",
        "",
        "| Symbol | Trades | Win% | PF | Avg R | Max DD% | Net $ | Expectancy | Risk mult |",
        "|--------|--------|------|-----|-------|---------|-------|------------|-----------|",
    ]
    for symbol, metrics in sorted(analysis.by_symbol.items()):
        mult = analysis.symbol_risk_multipliers.get(symbol, 1.0)
        status = "OFF" if symbol in analysis.disabled_symbols else f"{mult:.0%}"
        lines.append(
            f"| {symbol} | {metrics.total_trades} | {metrics.win_rate:.1%} | "
            f"{metrics.profit_factor:.2f} | {metrics.average_r:+.2f} | "
            f"{metrics.max_drawdown_pct:.2f} | {metrics.net_profit:+.0f} | "
            f"{metrics.expectancy:+.2f} | {status} |"
        )
    lines.extend(["", "## Symbol:mode quarantine", ""])
    if analysis.quarantined_symbol_modes:
        for item in analysis.quarantined_symbol_modes:
            lines.append(f"- `{item}`")
    else:
        lines.append("- None")
    return "\n".join(lines)


def _regime_expectancy_markdown(analysis: StrategyQualityAnalysis) -> str:
    lines = [
        "# Regime Expectancy Report",
        "",
        f"**Generated:** {analysis.generated_at}",
        "",
        "| Regime | Trades | Win% | PF | Avg R | Max DD% | Net $ | Expectancy | Status |",
        "|--------|--------|------|-----|-------|---------|-------|------------|--------|",
    ]
    for regime, metrics in sorted(analysis.by_regime.items()):
        status = "DISABLED" if regime in analysis.disabled_regimes else "ACTIVE"
        lines.append(
            f"| {regime} | {metrics.total_trades} | {metrics.win_rate:.1%} | "
            f"{metrics.profit_factor:.2f} | {metrics.average_r:+.2f} | "
            f"{metrics.max_drawdown_pct:.2f} | {metrics.net_profit:+.0f} | "
            f"{metrics.expectancy:+.2f} | {status} |"
        )
    lines.extend(["", "## By year", "", "| Year | Trades | PF | Avg R | Net $ |", "|------|--------|-----|-------|-------|"])
    for year, metrics in sorted(analysis.by_year.items()):
        lines.append(
            f"| {year} | {metrics.total_trades} | {metrics.profit_factor:.2f} | "
            f"{metrics.average_r:+.2f} | {metrics.net_profit:+.0f} |"
        )
    return "\n".join(lines)


def _format_bucket(metrics: BucketMetrics) -> str:
    return (
        f"- Trades: **{metrics.total_trades}**\n"
        f"- Win rate: **{metrics.win_rate:.1%}**\n"
        f"- Profit factor: **{metrics.profit_factor:.2f}**\n"
        f"- Average R: **{metrics.average_r:+.2f}**\n"
        f"- Max drawdown: **{metrics.max_drawdown_pct:.2f}%**\n"
        f"- Net profit: **${metrics.net_profit:+,.2f}**\n"
        f"- Expectancy/trade: **${metrics.expectancy:+.2f}**"
    )


def _one_line_bucket(metrics: BucketMetrics) -> str:
    return (
        f"PF {metrics.profit_factor:.2f}, R {metrics.average_r:+.2f}, "
        f"net ${metrics.net_profit:+.0f}, {metrics.total_trades} trades"
    )
