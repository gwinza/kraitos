"""Build validation metrics from trade_journal.csv and paper_trades.csv."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backtesting.performance_report import PerformanceMetrics
from config import load_config
from validation import ForwardTestTracker, LiveReadinessReport
from validation.data_quality_report import write_data_quality_report
from validation.error_classifier import classify_errors
from validation.r_metrics import CLOSED_RESULTS, average_r_from_closed_frame
from validation.strategy_validator import StrategyValidationInput, StrategyValidator

MIN_PAPER_TRADES = 30
REALIZED_EVENTS = frozenset({"close", "scale_out"})
DAILY_DRAWDOWN_LIMIT_PCT = 5.0


def metrics_from_journal_frame(frame: pd.DataFrame, initial_balance: float) -> PerformanceMetrics:
    """Compute performance metrics from an in-memory journal frame."""
    if frame.empty:
        return _empty_metrics(initial_balance)

    closed = frame[frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS)]
    if closed.empty:
        return _empty_metrics(initial_balance)

    pnls = pd.to_numeric(closed["profit_loss"], errors="coerce").fillna(0.0)
    winners = pnls[pnls > 0]
    losers = pnls[pnls < 0]
    gross_profit = float(winners.sum())
    gross_loss = abs(float(losers.sum()))
    total = len(closed)

    win_rate = len(winners) / total if total else 0.0
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    average_r = average_r_from_closed_frame(closed)

    balances = pd.to_numeric(closed["balance"], errors="coerce").fillna(initial_balance)
    final_balance = float(balances.iloc[-1]) if not balances.empty else initial_balance
    max_drawdown_pct = _max_drawdown_pct(balances.tolist(), initial_balance)
    daily_pnl = _daily_pnl_from_frame(closed, "event_time", "profit_loss")
    daily_breach = _daily_drawdown_breached(daily_pnl, initial_balance)

    return PerformanceMetrics(
        initial_balance=initial_balance,
        final_balance=final_balance,
        equity=final_balance,
        total_return_pct=_return_pct(initial_balance, final_balance),
        max_drawdown_pct=max_drawdown_pct,
        daily_drawdown_pct=_latest_daily_drawdown_pct(daily_pnl, initial_balance),
        win_rate=win_rate,
        profit_factor=profit_factor,
        average_r=average_r,
        total_trades=total,
        winning_trades=int(len(winners)),
        losing_trades=int(len(losers)),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        daily_pnl=daily_pnl,
        trading_disabled=max_drawdown_pct >= 15.0,
        trading_halted_daily=daily_breach,
    )


def collect_from_logs(
    project_root: Path,
    *,
    backtest_initial_balance: float = 100.0,
    paper_initial_balance: float | None = None,
) -> dict:
    """Read log files and compute backtest/paper validation metrics."""
    logs_dir = project_root / "logs"
    journal_path = logs_dir / "trade_journal.csv"
    paper_path = logs_dir / "paper_trades.csv"
    errors_path = logs_dir / "json" / "errors.jsonl"

    if paper_initial_balance is None:
        try:
            config = load_config(project_root / "config" / "config.yaml")
            paper_initial_balance = float(config.account.balance)
        except Exception:
            paper_initial_balance = 10_000.0

    backtest = _metrics_from_trade_journal(journal_path, backtest_initial_balance)
    paper = _metrics_from_paper_trades(paper_path, paper_initial_balance)
    daily_breaches = _count_daily_drawdown_breaches(
        backtest.daily_pnl,
        paper.daily_pnl,
        backtest.initial_balance,
        paper.initial_balance,
    )
    error_summary = classify_errors(errors_path).to_dict()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backtest": _metrics_to_dict(backtest),
        "paper": _metrics_to_dict(paper),
        "errors": error_summary,
        "summary": {
            "win_rate_backtest": backtest.win_rate,
            "win_rate_paper": paper.win_rate,
            "profit_factor_backtest": backtest.profit_factor,
            "profit_factor_paper": paper.profit_factor,
            "max_drawdown_backtest_pct": backtest.max_drawdown_pct,
            "max_drawdown_paper_pct": paper.max_drawdown_pct,
            "average_r_backtest": backtest.average_r,
            "average_r_paper": paper.average_r,
            "total_trades": backtest.total_trades,
            "paper_trades": paper.total_trades,
            "daily_drawdown_breaches": daily_breaches,
            "critical_errors": error_summary.get("critical_runtime_count", 0),
        },
    }


def write_validation_metrics(
    project_root: Path,
    *,
    run_conservative: bool = True,
    quick: bool = False,
) -> Path:
    """Persist validation metrics to logs/validation_metrics.json."""
    payload = collect_validation_metrics(project_root, run_conservative=run_conservative, quick=quick)
    path = project_root / "logs" / "validation_metrics.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return path


def collect_validation_metrics(
    project_root: Path,
    *,
    run_conservative: bool = True,
    quick: bool = False,
) -> dict:
    """Collect paper metrics and run conservative walk-forward validation."""
    logs_dir = project_root / "logs"
    paper_path = logs_dir / "paper_trades.csv"
    errors_path = logs_dir / "json" / "errors.jsonl"

    try:
        config = load_config(project_root / "config" / "config.yaml")
        initial_balance = float(config.account.balance)
        paper_initial = initial_balance
    except Exception:
        initial_balance = 10_000.0
        paper_initial = 10_000.0

    paper = _metrics_from_paper_trades(paper_path, paper_initial)
    error_summary = classify_errors(errors_path).to_dict()

    if paper.total_trades < MIN_PAPER_TRADES:
        from paper_trading.paper_replay_session import PaperReplayConfig, run_paper_replay_session
        from validation.data_universe import WALK_FORWARD_SYMBOLS, WALK_FORWARD_YEARS

        replay_cfg = PaperReplayConfig(
            years=WALK_FORWARD_YEARS[:1] if quick else WALK_FORWARD_YEARS,
            symbols=("EURUSD", "GBPUSD", "AUDUSD") if quick else WALK_FORWARD_SYMBOLS,
            m1_bars_per_year=12_000 if quick else 6_000,
            step=6 if quick else 4,
        )
        run_paper_replay_session(project_root, config=replay_cfg, overwrite=True)
        paper = _metrics_from_paper_trades(paper_path, paper_initial)

    if run_conservative:
        from validation.conservative_validation import (
            WalkForwardConfig,
            run_conservative_validation,
            validation_payload_from_result,
        )
        from validation.data_universe import WALK_FORWARD_SYMBOLS

        wf_config = WalkForwardConfig(
            years=(2024, 2025) if quick else WalkForwardConfig().years,
            symbols=("EURUSD", "GBPUSD", "AUDUSD") if quick else WALK_FORWARD_SYMBOLS,
            m1_bars_per_year=12_000 if quick else WalkForwardConfig().m1_bars_per_year,
            step=6 if quick else WalkForwardConfig().step,
        )
        result = run_conservative_validation(project_root, config=wf_config)
        payload = validation_payload_from_result(
            result,
            paper_metrics=paper,
            error_summary=error_summary,
        )
        write_data_quality_report(project_root, payload)
        return payload

    legacy = collect_from_logs(project_root, backtest_initial_balance=initial_balance, paper_initial_balance=paper_initial)
    legacy["trust_verdict"] = "QUESTIONABLE"
    legacy["data_quality_score"] = 0.0
    legacy["conservative_metrics"] = legacy.get("backtest", {})
    legacy["optimistic_metrics"] = None
    legacy["validation_engine"] = "legacy_logs"
    return legacy


def run_validation_update(
    project_root: Path,
    *,
    quick: bool = False,
) -> tuple[object, str, Path, Path]:
    """
    Populate metrics, run strategy validation, and write the readiness report.

    Returns:
        (validation_result, report_text, metrics_path, report_path)
    """
    metrics_path = write_validation_metrics(project_root, quick=quick)
    with metrics_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    tracker = ForwardTestTracker(strategy_name="kraitos")
    conservative_raw = payload.get("conservative_metrics") or payload.get("backtest", {})
    tracker.set_backtest_metrics(_dict_to_metrics(conservative_raw))
    tracker.set_paper_metrics(_dict_to_metrics(payload.get("paper", {})))
    tracker.set_trust_verdict(str(payload.get("trust_verdict", "QUESTIONABLE")))
    tracker.set_data_quality_score(float(payload.get("data_quality_score", 0.0)))

    summary = payload.get("summary", {})
    errors = payload.get("errors", {})
    critical_messages = list(errors.get("critical_runtime_errors", []))
    critical_count = int(errors.get("critical_runtime_count", summary.get("critical_errors", 0)))
    for message in critical_messages:
        tracker.record_critical_error(message)
    if critical_count > 0 and not critical_messages:
        tracker.record_critical_error(
            f"{critical_count} critical runtime error(s) recorded in system logs"
        )

    report = LiveReadinessReport()
    validator_input = StrategyValidationInput(
        strategy_name="kraitos",
        backtest=_dict_to_metrics(conservative_raw),
        paper=_dict_to_metrics(payload.get("paper", {})),
        critical_errors=tuple(critical_messages or (
            [f"{critical_count} critical runtime error(s) recorded in system logs"]
            if critical_count > 0
            else []
        )),
        live_trading_enabled=False,
        trust_verdict=str(payload.get("trust_verdict", "QUESTIONABLE")),
        data_quality_score=float(payload.get("data_quality_score", 0.0)),
    )
    validator = StrategyValidator()
    result = validator.validate(validator_input)
    text = report.render(result)

    report_path = project_root / "logs" / "live_readiness_report.md"
    report_path.write_text(_format_readiness_markdown(result, text, payload), encoding="utf-8")
    write_data_quality_report(project_root, payload)
    return result, text, metrics_path, report_path


def _metrics_from_trade_journal(path: Path, initial_balance: float) -> PerformanceMetrics:
    if not path.exists():
        return _empty_metrics(initial_balance)
    frame = pd.read_csv(path)
    return metrics_from_journal_frame(frame, initial_balance)


def _metrics_from_paper_trades(path: Path, initial_balance: float) -> PerformanceMetrics:
    if not path.exists():
        return _empty_metrics(initial_balance)

    frame = pd.read_csv(path)
    if frame.empty:
        return _empty_metrics(initial_balance)

    if "event_time" in frame.columns:
        frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")

    realized = frame[
        frame["event_type"].astype(str).str.lower().isin(REALIZED_EVENTS)
    ].copy()
    realized["closed_pl"] = pd.to_numeric(realized["closed_pl"], errors="coerce").fillna(0.0)
    realized = realized[realized["closed_pl"] != 0.0]

    if realized.empty:
        return _empty_metrics(initial_balance)

    pnls = realized["closed_pl"]
    winners = pnls[pnls > 0]
    losers = pnls[pnls < 0]
    gross_profit = float(winners.sum())
    gross_loss = abs(float(losers.sum()))
    total = len(realized)

    win_rate = len(winners) / total if total else 0.0
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    r_estimates = [_estimate_paper_r(row) for _, row in realized.iterrows()]
    non_zero_r = [value for value in r_estimates if value != 0.0]
    average_r = sum(non_zero_r) / len(non_zero_r) if non_zero_r else 0.0

    balance_series = pd.to_numeric(realized["balance"], errors="coerce").fillna(initial_balance)
    final_balance = float(balance_series.iloc[-1]) if not balance_series.empty else initial_balance
    max_drawdown_pct = _max_drawdown_pct(balance_series.tolist(), initial_balance)
    daily_pnl = _daily_pnl_from_frame(realized, "event_time", "closed_pl")
    daily_breach = _daily_drawdown_breached(daily_pnl, initial_balance)

    return PerformanceMetrics(
        initial_balance=initial_balance,
        final_balance=final_balance,
        equity=final_balance,
        total_return_pct=_return_pct(initial_balance, final_balance),
        max_drawdown_pct=max_drawdown_pct,
        daily_drawdown_pct=_latest_daily_drawdown_pct(daily_pnl, initial_balance),
        win_rate=win_rate,
        profit_factor=profit_factor,
        average_r=average_r,
        total_trades=total,
        winning_trades=int(len(winners)),
        losing_trades=int(len(losers)),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        daily_pnl=daily_pnl,
        trading_disabled=max_drawdown_pct >= 15.0,
        trading_halted_daily=daily_breach,
    )


def _estimate_paper_r(row: pd.Series) -> float:
    from validation.r_metrics import initial_risk_amount

    pnl = float(row.get("closed_pl", 0.0) or 0.0)
    symbol = str(row.get("symbol", "EURUSD"))
    entry = float(row.get("entry_price", 0.0) or 0.0)
    stop = float(row.get("stop_loss", 0.0) or 0.0)
    lot = float(row.get("lot_size", 0.0) or 0.0)
    if pnl == 0.0:
        return 0.0
    risk_amount = initial_risk_amount(
        symbol=symbol,
        entry=entry,
        stop_loss=stop,
        lot_size=lot,
    )
    if risk_amount <= 0:
        return 0.0
    return pnl / risk_amount


def _count_daily_drawdown_breaches(
    backtest_daily: dict[str, float],
    paper_daily: dict[str, float],
    backtest_initial: float,
    paper_initial: float,
) -> int:
    breaches = 0
    for day, pnl in backtest_daily.items():
        if backtest_initial > 0 and (-pnl / backtest_initial * 100.0) >= DAILY_DRAWDOWN_LIMIT_PCT:
            breaches += 1
    for day, pnl in paper_daily.items():
        if paper_initial > 0 and (-pnl / paper_initial * 100.0) >= DAILY_DRAWDOWN_LIMIT_PCT:
            breaches += 1
    return breaches


def _daily_pnl_from_frame(frame: pd.DataFrame, time_col: str, pnl_col: str) -> dict[str, float]:
    daily: dict[str, float] = {}
    for _, row in frame.iterrows():
        moment = row.get(time_col)
        parsed = pd.to_datetime(moment, utc=True, errors="coerce")
        if pd.isna(parsed):
            continue
        day = parsed.date().isoformat()
        pnl = float(pd.to_numeric(row.get(pnl_col), errors="coerce") or 0.0)
        daily[day] = daily.get(day, 0.0) + pnl
    return daily


def _max_drawdown_pct(balances: list[float], initial_balance: float) -> float:
    peak = initial_balance
    max_dd = 0.0
    balance = initial_balance
    for value in balances:
        balance = float(value)
        peak = max(peak, balance)
        if peak > 0:
            max_dd = max(max_dd, (peak - balance) / peak * 100.0)
    return max_dd


def _latest_daily_drawdown_pct(daily_pnl: dict[str, float], initial_balance: float) -> float:
    if not daily_pnl or initial_balance <= 0:
        return 0.0
    last_day = sorted(daily_pnl.keys())[-1]
    loss = max(0.0, -daily_pnl[last_day])
    return loss / initial_balance * 100.0


def _daily_drawdown_breached(daily_pnl: dict[str, float], initial_balance: float) -> bool:
    if initial_balance <= 0:
        return False
    for pnl in daily_pnl.values():
        if (-pnl / initial_balance * 100.0) >= DAILY_DRAWDOWN_LIMIT_PCT:
            return True
    return False


def _return_pct(initial: float, final: float) -> float:
    if initial <= 0:
        return 0.0
    return (final - initial) / initial * 100.0


def _empty_metrics(initial_balance: float) -> PerformanceMetrics:
    return PerformanceMetrics(
        initial_balance=initial_balance,
        final_balance=initial_balance,
        equity=initial_balance,
        total_return_pct=0.0,
        max_drawdown_pct=0.0,
        daily_drawdown_pct=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        average_r=0.0,
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        gross_profit=0.0,
        gross_loss=0.0,
        daily_pnl={},
        trading_disabled=False,
        trading_halted_daily=False,
    )


def _metrics_to_dict(metrics: PerformanceMetrics) -> dict:
    raw = asdict(metrics)
    if raw.get("profit_factor") == float("inf"):
        raw["profit_factor"] = "inf"
    return raw


def _dict_to_metrics(raw: dict) -> PerformanceMetrics:
    profit_factor = raw.get("profit_factor", 0.0)
    if profit_factor == "inf":
        profit_factor = float("inf")
    else:
        profit_factor = float(profit_factor)

    return PerformanceMetrics(
        initial_balance=float(raw.get("initial_balance", 0.0)),
        final_balance=float(raw.get("final_balance", 0.0)),
        equity=float(raw.get("equity", 0.0)),
        total_return_pct=float(raw.get("total_return_pct", 0.0)),
        max_drawdown_pct=float(raw.get("max_drawdown_pct", 0.0)),
        daily_drawdown_pct=float(raw.get("daily_drawdown_pct", 0.0)),
        win_rate=float(raw.get("win_rate", 0.0)),
        profit_factor=profit_factor,
        average_r=float(raw.get("average_r", 0.0)),
        total_trades=int(raw.get("total_trades", 0)),
        winning_trades=int(raw.get("winning_trades", 0)),
        losing_trades=int(raw.get("losing_trades", 0)),
        gross_profit=float(raw.get("gross_profit", 0.0)),
        gross_loss=float(raw.get("gross_loss", 0.0)),
        daily_pnl=dict(raw.get("daily_pnl", {})),
        trading_disabled=bool(raw.get("trading_disabled", False)),
        trading_halted_daily=bool(raw.get("trading_halted_daily", False)),
    )


def _format_readiness_markdown(result: object, report_text: str, payload: dict) -> str:
    summary = payload.get("summary", {})
    lines = [
        "# Kraitos Live Readiness Report",
        "",
        f"**Generated:** {payload.get('generated_at', 'unknown')}",
        f"**Validation status:** `{result.status}`",
        f"**Live trading enabled:** `False` (unchanged — safe mode)",
        "",
        "## Metrics summary (from logs)",
        "",
        f"- Validation engine: **{payload.get('validation_engine', 'unknown')}**",
        f"- Data source: **{payload.get('data_source', 'unknown')}**",
        f"- Trust verdict: **{payload.get('trust_verdict', 'unknown')}**",
        f"- Data quality score: **{payload.get('data_quality_score', 0.0)}**",
        f"- Conservative closed trades: **{summary.get('total_trades', 0)}**",
        f"- Paper closed trades: **{summary.get('paper_trades', 0)}**",
        f"- Optimistic metrics: **{payload.get('optimistic_label', 'n/a')}**",
        f"- Backtest win rate: **{float(summary.get('win_rate_backtest', 0.0)):.1%}**",
        f"- Paper win rate: **{float(summary.get('win_rate_paper', 0.0)):.1%}**",
        f"- Backtest profit factor: **{summary.get('profit_factor_backtest', 0)}**",
        f"- Paper profit factor: **{summary.get('profit_factor_paper', 0)}**",
        f"- Backtest max drawdown: **{float(summary.get('max_drawdown_backtest_pct', 0.0)):.2f}%**",
        f"- Paper max drawdown: **{float(summary.get('max_drawdown_paper_pct', 0.0)):.2f}%**",
        f"- Backtest average R: **{float(summary.get('average_r_backtest', 0.0)):+.2f}R**",
        f"- Paper average R: **{float(summary.get('average_r_paper', 0.0)):+.2f}R**",
        f"- Daily drawdown breaches: **{summary.get('daily_drawdown_breaches', 0)}**",
        f"- Expected test errors: **{summary.get('expected_test_errors', 0)}**",
        f"- Real runtime errors: **{summary.get('real_runtime_errors', 0)}**",
        f"- Critical runtime errors: **{summary.get('critical_errors', 0)}**",
        "",
        "## Validation report",
        "",
        "```text",
        report_text,
        "```",
        "",
    ]
    return "\n".join(lines)
