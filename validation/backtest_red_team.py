"""Red-team audit of Kraitos backtest realism and trustworthiness."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd

from backtesting.backtest_engine import BacktestEngine, BacktestEngineConfig
from backtesting.conservative_backtest_engine import ConservativeBacktestConfig, ConservativeBacktestEngine
from backtesting.execution_model import ExecutionCostConfig, slice_closed_candles, slice_inclusive_candles
from backtesting.performance_report import PerformanceMetrics, PerformanceReport
from backtesting.run_validation_backtest import build_backtest_stack
from backtesting.synthetic_market import generate_symbol_universe
from paper_trading.virtual_account import ValidationConfig

TrustRating = Literal["TRUSTWORTHY", "QUESTIONABLE", "INVALID"]


@dataclass(frozen=True)
class BiasFinding:
    """Single red-team issue identified in the backtest path."""

    code: str
    severity: str
    description: str
    optimistic: bool
    conservative_mitigation: str


@dataclass
class RedTeamComparison:
    """Optimistic vs conservative replay metrics."""

    optimistic: PerformanceMetrics
    conservative: PerformanceMetrics
    optimistic_trades: int
    conservative_trades: int
    test_bars_m1: int
    test_symbols: tuple[str, ...]


@dataclass
class RedTeamVerdict:
    """Overall trust assessment."""

    rating: TrustRating
    reasons: list[str] = field(default_factory=list)
    findings: list[BiasFinding] = field(default_factory=list)
    comparison: RedTeamComparison | None = None


def audit_known_biases() -> list[BiasFinding]:
    """Document biases present in the default (optimistic) replay path."""
    return [
        BiasFinding(
            code="incomplete_bar_lookahead",
            severity="critical",
            description=(
                "Default engine evaluates at bar open timestamps but passes the "
                "full OHLC of that bar into the pipeline (close/high/low not known yet)."
            ),
            optimistic=True,
            conservative_mitigation="Evaluate at bar close with closed-candle slice only.",
        ),
        BiasFinding(
            code="htf_partial_period",
            severity="critical",
            description=(
                "Inclusive candle slice (time <= moment) keeps higher-timeframe bars "
                "whose periods have not finished, leaking future M1 resample data."
            ),
            optimistic=True,
            conservative_mitigation="Exclude HTF bars until bar_close_time <= moment.",
        ),
        BiasFinding(
            code="same_bar_entry",
            severity="high",
            description="TRADE signals fill on the same driver bar close used for confirmation.",
            optimistic=True,
            conservative_mitigation="Queue fills for next bar open.",
        ),
        BiasFinding(
            code="tp_sl_ambiguity",
            severity="medium",
            description="When both TP and SL are inside one bar, outcome must be conservative.",
            optimistic=False,
            conservative_mitigation="Stop loss is checked first when both levels trade.",
        ),
        BiasFinding(
            code="missing_commission",
            severity="high",
            description="Default replay applies spread only; no per-lot commission.",
            optimistic=True,
            conservative_mitigation="Round-turn commission debited on open and close.",
        ),
        BiasFinding(
            code="missing_slippage",
            severity="medium",
            description="Fills assume exact bid/ask with no slippage.",
            optimistic=True,
            conservative_mitigation="Configurable slippage pips applied against the trader.",
        ),
        BiasFinding(
            code="backtest_end_close",
            severity="medium",
            description="Open positions closed at final mid close (can flatter returns).",
            optimistic=True,
            conservative_mitigation="Mark at spread-adjusted price; label as backtest_end_mark.",
        ),
        BiasFinding(
            code="synthetic_weekday_filter",
            severity="medium",
            description="Synthetic generator skips weekends, concentrating on weekday liquidity.",
            optimistic=True,
            conservative_mitigation="Use longer spans and real tick data for production validation.",
        ),
        BiasFinding(
            code="short_sample_window",
            severity="medium",
            description="Reported 96.2% run covers only a few weeks of synthetic data.",
            optimistic=True,
            conservative_mitigation="Extend history and include volatile/ranging regimes.",
        ),
        BiasFinding(
            code="overlapping_signals",
            severity="low",
            description="Multiple concurrent positions per correlated group are allowed until risk caps.",
            optimistic=True,
            conservative_mitigation="Risk controller enforces correlated exposure (unchanged).",
        ),
    ]


def compare_candle_slices(
    candles: dict[str, pd.DataFrame],
    moment: datetime,
) -> dict[str, int]:
    """Return bar-count deltas between optimistic and closed-only slicing."""
    inclusive = slice_inclusive_candles(candles, moment)
    closed = slice_closed_candles(candles, moment)
    delta: dict[str, int] = {}
    for timeframe in inclusive:
        inc_frame = inclusive.get(timeframe)
        closed_frame = closed.get(timeframe)
        inc_len = len(inc_frame) if inc_frame is not None and not inc_frame.empty else 0
        closed_len = len(closed_frame) if closed_frame is not None and not closed_frame.empty else 0
        delta[timeframe] = inc_len - closed_len
    return delta


def run_red_team_comparison(
    project_root: Path,
    *,
    symbols: tuple[str, ...] = ("EURUSD", "GBPUSD"),
    m1_bars: int = 35_000,
    step: int = 4,
) -> RedTeamComparison:
    """Run optimistic and conservative replays on the same synthetic data."""
    project_root = project_root.resolve()
    config, pipeline, risk_controller = build_backtest_stack(project_root)
    candles = generate_symbol_universe(symbols, bars=m1_bars)

    validation = ValidationConfig(
        initial_balance=float(config.account.balance),
        risk_per_trade_pct=float(config.risk.per_trade_pct),
        spread_pips=0.5,
    )

    optimistic_engine = BacktestEngine(
        config=config,
        pipeline=pipeline,
        risk_controller=risk_controller,
        engine_config=BacktestEngineConfig(
            driver_timeframe="M5",
            step=step,
            min_warmup_bars=0,
            validation=validation,
        ),
        journal_path=project_root / "logs" / "red_team_optimistic_journal.csv",
    )
    optimistic_engine.risk_controller.set_portfolio_builder(
        lambda: optimistic_engine.account.portfolio_state(risk_controller.risk_manager)
    )

    conservative_engine = ConservativeBacktestEngine(
        config=config,
        pipeline=pipeline,
        risk_controller=risk_controller,
        conservative_config=ConservativeBacktestConfig(
            engine=BacktestEngineConfig(
                driver_timeframe="M5",
                step=step,
                min_warmup_bars=0,
                validation=validation,
            ),
            costs=ExecutionCostConfig(
                spread_pips=1.2,
                commission_per_lot_round_turn=7.0,
                slippage_pips=0.3,
            ),
        ),
        journal_path=project_root / "logs" / "red_team_conservative_journal.csv",
    )
    conservative_engine.risk_controller.set_portfolio_builder(
        lambda: conservative_engine.account.portfolio_state(risk_controller.risk_manager)
    )

    optimistic_result = optimistic_engine.run(candles, symbols=symbols)
    conservative_result = conservative_engine.run(candles, symbols=symbols)

    optimistic_metrics = PerformanceReport(optimistic_result.account).metrics()
    conservative_metrics = PerformanceReport(conservative_result.account).metrics()

    return RedTeamComparison(
        optimistic=optimistic_metrics,
        conservative=conservative_metrics,
        optimistic_trades=optimistic_metrics.total_trades,
        conservative_trades=conservative_metrics.total_trades,
        test_bars_m1=m1_bars,
        test_symbols=symbols,
    )


def assess_trustworthiness(
    findings: list[BiasFinding],
    comparison: RedTeamComparison | None,
    *,
    reported_win_rate: float | None = None,
    reported_return_pct: float | None = None,
) -> RedTeamVerdict:
    """Assign TRUSTWORTHY, QUESTIONABLE, or INVALID."""
    reasons: list[str] = []
    critical = [finding for finding in findings if finding.severity == "critical" and finding.optimistic]

    if comparison is not None:
        opt = comparison.optimistic
        con = comparison.conservative
        win_delta = (opt.win_rate - con.win_rate) * 100.0
        return_delta = opt.total_return_pct - con.total_return_pct

        if win_delta >= 25.0:
            reasons.append(f"Win rate drops {win_delta:.1f} pts under conservative fills ({opt.win_rate:.1%} -> {con.win_rate:.1%}).")
        if return_delta >= 20.0:
            reasons.append(f"Return drops {return_delta:.1f} pts under conservative fills ({opt.total_return_pct:+.1f}% -> {con.total_return_pct:+.1f}%).")
        if con.total_trades < 30:
            reasons.append(f"Conservative sample only {con.total_trades} closed trades (low statistical confidence).")
        if opt.win_rate >= 0.90 and con.win_rate < 0.55:
            reasons.append("Very high optimistic win rate collapses under conservative execution.")

    if reported_win_rate is not None and reported_win_rate >= 0.90:
        reasons.append(f"Published backtest win rate {reported_win_rate:.1%} is unusually high for FX.")
    if reported_return_pct is not None and reported_return_pct >= 40.0:
        reasons.append(f"Published return {reported_return_pct:+.1f}% over a short synthetic window is aggressive.")

    if critical:
        reasons.append(f"{len(critical)} critical optimistic bias(es) documented in default engine.")

    rating: TrustRating
    if (
        comparison is not None
        and comparison.optimistic.win_rate >= 0.85
        and comparison.conservative.win_rate < 0.45
    ) or (reported_win_rate is not None and reported_win_rate >= 0.95 and len(critical) >= 2):
        rating = "INVALID"
    elif reasons or critical:
        rating = "QUESTIONABLE"
    else:
        rating = "TRUSTWORTHY"

    return RedTeamVerdict(rating=rating, reasons=reasons, findings=findings, comparison=comparison)


def _parse_reported_metrics(debug_report_path: Path) -> tuple[float | None, float | None]:
    if not debug_report_path.exists():
        return None, None
    text = debug_report_path.read_text(encoding="utf-8")
    win_match = re.search(r"Win rate:\s*\*\*([\d.]+)%\*\*", text)
    return_match = re.search(r"Total return:\s*([+-]?[\d.]+)%", text)
    win_rate = float(win_match.group(1)) / 100.0 if win_match else None
    return_pct = float(return_match.group(1)) if return_match else None
    return win_rate, return_pct


def generate_red_team_report(
    project_root: Path,
    *,
    m1_bars: int = 35_000,
    run_comparison: bool = True,
) -> RedTeamVerdict:
    """Run audit, optional comparison, and write logs/backtest_red_team_report.md."""
    project_root = project_root.resolve()
    findings = audit_known_biases()
    debug_path = project_root / "logs" / "backtest_debug_report.md"
    reported_win, reported_return = _parse_reported_metrics(debug_path)

    comparison = run_red_team_comparison(project_root, m1_bars=m1_bars) if run_comparison else None
    verdict = assess_trustworthiness(
        findings,
        comparison,
        reported_win_rate=reported_win,
        reported_return_pct=reported_return,
    )

    report_path = project_root / "logs" / "backtest_red_team_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_markdown(verdict, reported_win, reported_return), encoding="utf-8")
    return verdict


def _render_markdown(
    verdict: RedTeamVerdict,
    reported_win: float | None,
    reported_return: float | None,
) -> str:
    lines = [
        "# Kraitos Backtest Red-Team Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Trust rating:** **{verdict.rating}**",
        "",
        "## Executive summary",
        "",
    ]

    if verdict.rating == "TRUSTWORTHY":
        lines.append("Optimistic and conservative replays are aligned enough for exploratory use.")
    elif verdict.rating == "QUESTIONABLE":
        lines.append(
            "Reported performance is likely **inflated** by simulation assumptions. "
            "Do not use the default backtest for live-readiness decisions without fixes."
        )
    else:
        lines.append(
            "Backtest results are **not credible** for strategy validation under the default engine."
        )

    if reported_win is not None or reported_return is not None:
        lines.extend(["", "## Reported debug backtest (optimistic path)", ""])
        if reported_win is not None:
            lines.append(f"- Win rate: **{reported_win:.1%}**")
        if reported_return is not None:
            lines.append(f"- Total return: **{reported_return:+.2f}%**")

    lines.extend(["", "## Verdict reasons", ""])
    if verdict.reasons:
        for reason in verdict.reasons:
            lines.append(f"- {reason}")
    else:
        lines.append("- No major gaps detected between optimistic and conservative assumptions.")

    lines.extend(["", "## Bias checklist", "", "| Code | Severity | Optimistic? | Mitigation |", "|------|----------|-------------|------------|"])
    for finding in verdict.findings:
        lines.append(
            f"| {finding.code} | {finding.severity} | "
            f"{'yes' if finding.optimistic else 'no'} | {finding.conservative_mitigation} |"
        )

    if verdict.comparison is not None:
        opt = verdict.comparison.optimistic
        con = verdict.comparison.conservative
        lines.extend(
            [
                "",
                "## Optimistic vs conservative replay",
                "",
                f"- Sample: **{verdict.comparison.test_bars_m1}** M1 bars, symbols {', '.join(verdict.comparison.test_symbols)}",
                "",
                "| Metric | Optimistic | Conservative |",
                "|--------|------------|--------------|",
                f"| Closed trades | {opt.total_trades} | {con.total_trades} |",
                f"| Win rate | {opt.win_rate:.1%} | {con.win_rate:.1%} |",
                f"| Total return | {opt.total_return_pct:+.2f}% | {con.total_return_pct:+.2f}% |",
                f"| Profit factor | {opt.profit_factor:.2f} | {con.profit_factor:.2f} |",
                f"| Max drawdown | {opt.max_drawdown_pct:.2f}% | {con.max_drawdown_pct:.2f}% |",
                "",
                "### Conservative execution assumptions",
                "",
                "- Closed candles only (no partial HTF periods)",
                "- Signal at bar close, entry at next bar open",
                "- Stop loss first when TP and SL share a bar",
                "- Spread 1.2 pips, slippage 0.3 pips, commission $7/lot round turn",
                "",
            ]
        )

    lines.extend(
        [
            "## Recommendations",
            "",
            "1. Adopt `ConservativeBacktestEngine` for validation gates.",
            "2. Replace inclusive candle slicing in the default engine when auditing.",
            "3. Validate on real tick or M1 data spanning multiple regimes.",
            "4. Keep `LIVE_TRADING` disabled until forward/paper sample is sufficient.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Kraitos backtest red-team audit")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--bars", type=int, default=35_000)
    parser.add_argument("--no-run", action="store_true", help="Skip replay comparison")
    args = parser.parse_args()

    verdict = generate_red_team_report(
        args.root,
        m1_bars=args.bars,
        run_comparison=not args.no_run,
    )
    print(f"Trust rating: {verdict.rating}")
    for reason in verdict.reasons:
        print(f" - {reason}")
    return 0 if verdict.rating == "TRUSTWORTHY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
