"""Historical strategy-fit research for underperforming assets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from intelligence.asset_strategy_memory import AssetStrategyMemory, AssetStatus, SymbolStrategyFit
from intelligence.asset_trend_analyzer import AssetState
from validation.data_universe import YEAR_REGIME_LABELS
from validation.r_metrics import CLOSED_RESULTS

MIN_BUCKET_TRADES = 5
UNDERPERFORM_PF = 1.0
UNDERPERFORM_EXPECTANCY = 0.0


@dataclass
class StrategyFitBucket:
    """Performance slice for one dimension."""

    label: str
    trades: int
    win_rate: float
    profit_factor: float
    expectancy: float
    net_profit: float
    average_r: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "trades": self.trades,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 4),
            "expectancy": round(self.expectancy, 4),
            "net_profit": round(self.net_profit, 2),
            "average_r": round(self.average_r, 4),
        }


@dataclass
class AssetResearchResult:
    """Strategy-fit research output for one symbol."""

    symbol: str
    overall_pf: float
    overall_expectancy: float
    overall_trades: int
    best_strategy: str
    best_trend_state: str
    avoid_strategies: list[str]
    status: AssetStatus
    recommendation: str
    by_mode: dict[str, StrategyFitBucket] = field(default_factory=dict)
    by_regime: dict[str, StrategyFitBucket] = field(default_factory=dict)
    by_year: dict[str, StrategyFitBucket] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "overall_pf": round(self.overall_pf, 4),
            "overall_expectancy": round(self.overall_expectancy, 4),
            "overall_trades": self.overall_trades,
            "best_strategy": self.best_strategy,
            "best_trend_state": self.best_trend_state,
            "avoid_strategies": self.avoid_strategies,
            "status": self.status,
            "recommendation": self.recommendation,
            "by_mode": {k: v.to_dict() for k, v in self.by_mode.items()},
            "by_regime": {k: v.to_dict() for k, v in self.by_regime.items()},
            "by_year": {k: v.to_dict() for k, v in self.by_year.items()},
        }


class AssetStrategyResearcher:
    """Investigate which strategies fit each asset before disabling."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.memory = AssetStrategyMemory(project_root)

    def research_journal(
        self,
        journal_path: Path | None = None,
        *,
        initial_balance: float = 10_000.0,
    ) -> list[AssetResearchResult]:
        path = journal_path or self.project_root / "logs" / "conservative_trade_journal.csv"
        if not path.exists():
            return []
        frame = pd.read_csv(path)
        closed = frame[frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS)].copy()
        if closed.empty:
            return []

        closed["event_time"] = pd.to_datetime(closed["event_time"], utc=True, errors="coerce")
        closed["year"] = closed["event_time"].dt.year.astype(str)
        closed["regime"] = closed["year"].map(
            lambda y: YEAR_REGIME_LABELS.get(int(y), "unknown") if str(y).isdigit() else "unknown"
        )
        closed["direction"] = closed.get("direction", "unknown")
        closed["session"] = closed["event_time"].dt.hour.astype(str)

        results: list[AssetResearchResult] = []
        for symbol, subset in closed.groupby("symbol"):
            result = self._research_symbol(str(symbol), subset)
            results.append(result)
            self._update_memory(result)

        self.memory.save()
        self.write_asset_strategy_fit_report(results)
        self.write_underperformance_report(results)
        return results

    def _research_symbol(self, symbol: str, closed: pd.DataFrame) -> AssetResearchResult:
        overall = _bucket_metrics(closed, symbol)
        by_mode = {
            str(mode): _bucket_metrics(subset, f"{symbol}:{mode}")
            for mode, subset in closed.groupby("mode")
        }
        by_regime = {
            str(regime): _bucket_metrics(subset, f"{symbol}:{regime}")
            for regime, subset in closed.groupby("regime")
        }
        by_year = {
            str(year): _bucket_metrics(subset, f"{symbol}:{year}")
            for year, subset in closed.groupby("year")
        }

        best_mode = max(by_mode.items(), key=lambda item: item[1].expectancy, default=(None, overall))
        best_strategy = best_mode[0] or "harvest"
        avoid = [
            mode
            for mode, bucket in by_mode.items()
            if bucket.trades >= MIN_BUCKET_TRADES
            and (bucket.expectancy < 0 or bucket.profit_factor < UNDERPERFORM_PF)
        ]

        status, recommendation = self._determine_status(
            overall=overall,
            by_mode=by_mode,
            by_regime=by_regime,
            avoid_strategies=avoid,
        )

        return AssetResearchResult(
            symbol=symbol,
            overall_pf=overall.profit_factor,
            overall_expectancy=overall.expectancy,
            overall_trades=overall.trades,
            best_strategy=_map_mode_to_strategy(best_strategy),
            best_trend_state=_infer_best_state(by_regime),
            avoid_strategies=[_map_mode_to_strategy(mode) for mode in avoid],
            status=status,
            recommendation=recommendation,
            by_mode=by_mode,
            by_regime=by_regime,
            by_year=by_year,
        )

    def _determine_status(
        self,
        *,
        overall: StrategyFitBucket,
        by_mode: dict[str, StrategyFitBucket],
        by_regime: dict[str, StrategyFitBucket],
        avoid_strategies: list[str],
    ) -> tuple[AssetStatus, str]:
        qualified_modes = [
            bucket for bucket in by_mode.values() if bucket.trades >= MIN_BUCKET_TRADES
        ]
        positive_modes = [
            bucket for bucket in qualified_modes if bucket.expectancy > 0 and bucket.profit_factor >= 1.1
        ]
        all_negative = qualified_modes and not positive_modes
        excessive_dd = sum(
            1
            for bucket in by_regime.values()
            if bucket.trades >= MIN_BUCKET_TRADES and bucket.net_profit < -500
        ) >= 2

        if all_negative and excessive_dd:
            return (
                "DISABLED",
                "All strategy modes negative expectancy with excessive drawdown across regimes",
            )
        if all_negative:
            return "QUARANTINED", "All qualified strategy modes show negative expectancy"
        if overall.profit_factor < UNDERPERFORM_PF or overall.expectancy < UNDERPERFORM_EXPECTANCY:
            if positive_modes:
                best = max(positive_modes, key=lambda b: b.expectancy)
                return (
                    "CONDITIONAL",
                    f"Overall PF weak but {best.label} shows positive expectancy; use conditionally",
                )
            return "QUARANTINED", "Underperforming with no positive strategy mode found"
        return "APPROVED", "Asset approved with positive historical strategy fit"

    def _update_memory(self, result: AssetResearchResult) -> None:
        fit = self.memory.get_or_create(result.symbol)
        fit.status = result.status
        fit.best_strategy_overall = result.best_strategy
        fit.best_state = result.best_trend_state  # type: ignore[assignment]
        fit.avoid_strategies = result.avoid_strategies
        fit.fit_scores = {
            mode: bucket.expectancy for mode, bucket in result.by_mode.items()
        }
        fit.best_strategies_by_state = _build_state_strategy_map(result)
        fit.notes = result.recommendation
        fit.last_researched_at = datetime.now(timezone.utc).isoformat()
        self.memory.update(fit)

    def write_asset_strategy_fit_report(self, results: list[AssetResearchResult]) -> Path:
        lines = [
            "# Asset Strategy Fit Report",
            "",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            "",
            "| Symbol | Status | Best strategy | Best state | Avoid | Overall PF | Expectancy | Trades |",
            "|--------|--------|---------------|------------|-------|------------|------------|--------|",
        ]
        for result in sorted(results, key=lambda r: r.symbol):
            avoid = ", ".join(result.avoid_strategies) or "none"
            lines.append(
                f"| {result.symbol} | {result.status} | {result.best_strategy} | "
                f"{result.best_trend_state} | {avoid} | {result.overall_pf:.2f} | "
                f"{result.overall_expectancy:+.2f} | {result.overall_trades} |"
            )
        lines.extend(["", "## Recommendations", ""])
        for result in sorted(results, key=lambda r: r.symbol):
            lines.append(f"- **{result.symbol}** ({result.status}): {result.recommendation}")
        path = self.project_root / "logs" / "asset_strategy_fit_report.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def write_underperformance_report(self, results: list[AssetResearchResult]) -> Path:
        under_review = [
            r for r in results if r.status in {"CONDITIONAL", "QUARANTINED", "DISABLED"}
        ]
        lines = [
            "# Asset Underperformance Report",
            "",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            f"**Assets under review:** {len(under_review)}",
            "",
        ]
        if not under_review:
            lines.append("No assets currently under review.")
        else:
            for result in under_review:
                lines.extend(
                    [
                        f"## {result.symbol} — {result.status}",
                        "",
                        f"- Overall PF: **{result.overall_pf:.2f}**",
                        f"- Best strategy: **{result.best_strategy}**",
                        f"- Best trend state: **{result.best_trend_state}**",
                        f"- Avoid: **{', '.join(result.avoid_strategies) or 'none'}**",
                        f"- Action: {result.recommendation}",
                        "",
                    ]
                )
        path = self.project_root / "logs" / "asset_underperformance_report.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


def _bucket_metrics(frame: pd.DataFrame, label: str) -> StrategyFitBucket:
    if frame.empty:
        return StrategyFitBucket(label, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    pnls = pd.to_numeric(frame["profit_loss"], errors="coerce").fillna(0.0)
    winners = pnls[pnls > 0]
    losers = pnls[pnls < 0]
    gross_profit = float(winners.sum())
    gross_loss = abs(float(losers.sum()))
    if gross_loss > 0:
        pf = gross_profit / gross_loss
    elif gross_profit > 0:
        pf = 999.0
    else:
        pf = 0.0
    r_vals = pd.to_numeric(frame.get("r_multiple"), errors="coerce").dropna()
    avg_r = float(r_vals.mean()) if not r_vals.empty else 0.0
    return StrategyFitBucket(
        label=label,
        trades=len(frame),
        win_rate=len(winners) / len(frame) if len(frame) else 0.0,
        profit_factor=pf,
        expectancy=float(pnls.mean()),
        net_profit=float(pnls.sum()),
        average_r=avg_r,
    )


def _map_mode_to_strategy(mode: str) -> str:
    mapping = {
        "harvest": "harvest",
        "scalp": "range_scalper",
        "normal": "normal_trend",
    }
    return mapping.get(mode.strip().lower(), mode)


def _infer_best_state(by_regime: dict[str, StrategyFitBucket]) -> AssetState:
    if not by_regime:
        return "weak_trend"
    best = max(by_regime.values(), key=lambda b: b.expectancy)
    regime = best.label.split(":")[-1] if ":" in best.label else best.label
    if regime == "trending":
        return "strong_uptrend"
    if regime == "ranging":
        return "ranging"
    if regime == "volatile":
        return "volatile_breakout"
    return "weak_trend"


def _build_state_strategy_map(result: AssetResearchResult) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for regime, bucket in result.by_regime.items():
        if bucket.trades < MIN_BUCKET_TRADES:
            continue
        state: AssetState
        if regime == "trending":
            state = "strong_uptrend"
        elif regime == "ranging":
            state = "ranging"
        elif regime == "volatile":
            state = "volatile_breakout"
        else:
            state = "weak_trend"
        best_mode = max(
            (
                (mode, fit)
                for mode, fit in result.by_mode.items()
                if fit.trades >= MIN_BUCKET_TRADES
            ),
            key=lambda item: item[1].expectancy,
            default=(result.best_strategy, StrategyFitBucket("", 0, 0, 0, 0, 0, 0)),
        )
        mapping[state] = _map_mode_to_strategy(best_mode[0])
    if result.best_trend_state and result.best_strategy:
        mapping.setdefault(result.best_trend_state, result.best_strategy)
    return mapping
