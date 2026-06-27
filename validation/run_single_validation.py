"""Safe single-process entry point for conservative validation runs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from loguru import logger

from config import load_config
from validation.conservative_validation import (
    WalkForwardConfig,
    run_conservative_validation,
    validation_payload_from_result,
    write_harvest_intelligence_validation_report,
    write_opportunity_allocation_validation_report,
    write_council_frequency_expansion_validation_report,
    write_market_story_validation_report,
    write_story_evolution_validation_report,
    write_evidence_synthesis_validation_report,
    write_indicator_interpretation_validation_report,
    write_opportunity_hunter_council_validation_report,
    write_intelligence_enhancement_validation_report,
    write_story_aware_participation_validation_report,
    write_thesis_doctrine_validation_report,
)
from brains.auditor_brain import AuditorBrain
from brains.reports import write_brain_separation_reports
from council.rejection_tracker import reset_rejection_tracker, get_rejection_tracker
from validation.drawdown_attribution import (
    run_attribution_reports,
    write_drawdown_reduction_validation_report,
    write_post_drawdown_throttle_undo_validation_report,
)
from validation.portfolio_validation import (
    write_portfolio_construction_validation_report,
    write_portfolio_vs_drawdown_controls_comparison,
)
from validation.error_classifier import classify_errors
from validation.metrics_collector import _metrics_from_paper_trades
from validation.progress_tracker import ValidationProgressTracker
from validation.run_lock import LockHeldError, LockInfo, ValidationRunLock

LIVE_TRADING_KEYS = ("LIVE_TRADING", "ENABLE_LIVE_TRADING", "LIVE_TRADING_ENABLED")
TRUTHY = frozenset({"1", "true", "yes", "on"})


def _project_root() -> Path:
    return Path.cwd().resolve()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single conservative validation (locked).")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Terminate duplicate validation processes and acquire lock even if stale lock exists.",
    )
    return parser.parse_args(argv)


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in TRUTHY


def verify_live_trading_disabled(project_root: Path) -> None:
    """Ensure live trading flags remain disabled in .env."""
    env_path = project_root / ".env"
    values: dict[str, str | None] = {}
    if env_path.exists():
        values = dotenv_values(env_path)

    enabled_keys = [key for key in LIVE_TRADING_KEYS if _is_truthy(values.get(key))]
    if enabled_keys:
        raise RuntimeError(
            "Live trading must remain disabled for validation runs; "
            f"found enabled flags in .env: {', '.join(enabled_keys)}"
        )


def _reset_in_progress_journal(project_root: Path) -> Path:
    journal = project_root / "logs" / "conservative_trade_journal.csv"
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        journal.unlink()
    return journal


def _write_run_report(
    project_root: Path,
    *,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    lock_info: LockInfo | None,
    interruption_reason: str | None = None,
    metrics_payload: dict | None = None,
) -> Path:
    path = project_root / "logs" / "validation_run_report.md"
    elapsed = (finished_at - started_at).total_seconds()
    lines = [
        "# Validation Run Report",
        "",
        f"**Status:** `{status}`",
        f"**Started:** {started_at.isoformat()}",
        f"**Finished:** {finished_at.isoformat()}",
        f"**Elapsed:** {elapsed:.1f}s",
        "",
        "**Walk-forward scope:** 2022–2023 only (2-year validation).",
        "",
        "## Lock",
        "",
    ]
    if lock_info is not None:
        lines.extend(
            [
                f"- PID: `{lock_info.pid}`",
                f"- Lock start: `{lock_info.start_time}`",
                f"- Command: `{lock_info.command}`",
            ]
        )
    else:
        lines.append("- No lock acquired")

    if interruption_reason:
        lines.extend(["", "## Interruption", "", interruption_reason, ""])

    if metrics_payload is not None:
        summary = metrics_payload.get("summary", {})
        conservative = metrics_payload.get("conservative_metrics", {})
        lines.extend(
            [
                "",
                "## Metrics",
                "",
                f"- Trust verdict: **{metrics_payload.get('trust_verdict', 'unknown')}**",
                f"- Data quality score: **{metrics_payload.get('data_quality_score', 0.0)}**",
                f"- Total trades: **{summary.get('total_trades', conservative.get('total_trades', 0))}**",
                f"- Win rate: **{float(summary.get('win_rate_backtest', conservative.get('win_rate', 0.0))):.1%}**",
                f"- Profit factor: **{summary.get('profit_factor_backtest', conservative.get('profit_factor', 0))}**",
                f"- Max drawdown: **{float(summary.get('max_drawdown_backtest_pct', conservative.get('max_drawdown_pct', 0.0))):.2f}%**",
                f"- Average R: **{float(summary.get('average_r_backtest', conservative.get('average_r', 0.0))):+.2f}R**",
            ]
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_single_validation(
    project_root: Path,
    *,
    force: bool = False,
) -> int:
    """Execute one conservative-only validation under an exclusive lock."""
    project_root = project_root.resolve()
    command = " ".join(sys.argv)
    started_at = datetime.now(timezone.utc)
    lock_info: LockInfo | None = None
    progress: ValidationProgressTracker | None = None
    status = "FAILED"
    interruption_reason: str | None = None
    metrics_payload: dict | None = None

    verify_live_trading_disabled(project_root)
    reset_rejection_tracker()
    from portfolio.unlimited_opportunity_tracker import reset_unlimited_opportunity_tracker
    from intelligence.participation_tracker import reset_participation_tracker
    reset_unlimited_opportunity_tracker()
    reset_participation_tracker()
    from intelligence.kraitos_thesis_doctrine import reset_thesis_tracker
    reset_thesis_tracker()

    try:
        with ValidationRunLock(project_root, command=command, force=force) as acquired:
            lock_info = acquired
            journal_path = _reset_in_progress_journal(project_root)
            progress = ValidationProgressTracker(project_root, journal_path=journal_path)

            config = WalkForwardConfig(include_optimistic_demo=False)
            auditor = AuditorBrain(project_root)
            result = auditor.verify_run(
                config=config,
                progress_callback=progress.on_timeline,
                reset_journal=False,
            )

            try:
                stack_config = load_config(project_root / "config" / "config.yaml")
                initial_balance = float(stack_config.account.balance)
            except Exception:
                initial_balance = 10_000.0

            paper_path = project_root / "logs" / "paper_trades.csv"
            errors_path = project_root / "logs" / "json" / "errors.jsonl"
            paper_metrics = _metrics_from_paper_trades(paper_path, initial_balance)
            error_summary = classify_errors(errors_path).to_dict()

            metrics_payload = validation_payload_from_result(
                result,
                paper_metrics=paper_metrics,
                error_summary=error_summary,
            )
            metrics_path = project_root / "logs" / "validation_metrics.json"
            metrics_path.parent.mkdir(parents=True, exist_ok=True)
            with metrics_path.open("w", encoding="utf-8") as handle:
                json.dump(metrics_payload, handle, indent=2)

            write_opportunity_allocation_validation_report(
                project_root,
                conservative_metrics=result.conservative_metrics,
            )
            write_harvest_intelligence_validation_report(
                project_root,
                conservative_metrics=result.conservative_metrics,
            )
            run_attribution_reports(project_root)
            write_drawdown_reduction_validation_report(
                project_root,
                current_metrics=metrics_payload["conservative_metrics"],
            )
            write_portfolio_construction_validation_report(
                project_root,
                current_metrics=metrics_payload["conservative_metrics"],
            )
            write_portfolio_vs_drawdown_controls_comparison(
                project_root,
                current_metrics=metrics_payload["conservative_metrics"],
            )
            write_opportunity_hunter_council_validation_report(
                project_root,
                conservative_metrics=result.conservative_metrics,
            )
            write_council_frequency_expansion_validation_report(
                project_root,
                conservative_metrics=result.conservative_metrics,
            )
            write_market_story_validation_report(
                project_root,
                conservative_metrics=result.conservative_metrics,
            )
            evolution_stats = None
            trader = getattr(progress, "trader_brain", None) if progress else None
            evolution_engine = getattr(trader, "_evolution_engine", None) if trader else None
            if evolution_engine is not None:
                evolution_engine.write_all_reports()
                evolution_stats = {
                    "transitions_detected": evolution_engine.stats.transitions_detected,
                    "impacts_recorded": evolution_engine.stats.impacts_recorded,
                    "forecast_adjustments": evolution_engine.stats.forecast_adjustments,
                    "opportunity_informed": evolution_engine.stats.opportunity_informed,
                    "adaptation_events": evolution_engine.stats.adaptation_events,
                }
            write_story_evolution_validation_report(
                project_root,
                conservative_metrics=result.conservative_metrics,
                evolution_stats=evolution_stats,
            )
            synthesis_stats = None
            rejection_stats = None
            pipeline = getattr(auditor, "last_pipeline", None)
            trader = getattr(pipeline, "trader_brain", None) if pipeline else None
            story_engine = getattr(trader, "_story_engine", None) if trader else None
            if story_engine is not None:
                synth = story_engine.synthesis_engine
                synth.write_all_reports()
                synthesis_stats = {
                    "synthesised": synth.stats.synthesised,
                    "story_clear": synth.stats.story_clear,
                    "story_unclear": synth.stats.story_unclear,
                    "unclear_insufficient": synth.stats.unclear_insufficient,
                    "unclear_incoherent": synth.stats.unclear_incoherent,
                    "unclear_random": synth.stats.unclear_random,
                    "conflicts_interpreted": synth.stats.conflicts_interpreted,
                    "opportunities_recovered": synth.stats.opportunities_recovered,
                }
            tracker = get_rejection_tracker()
            rejection_stats = {
                "evaluations": tracker.evaluations,
                "market_story": tracker.stage_rejections.get("market_story", 0),
            }
            write_evidence_synthesis_validation_report(
                project_root,
                conservative_metrics=result.conservative_metrics,
                synthesis_stats=synthesis_stats,
                rejection_stats=rejection_stats,
            )
            interpretation_stats = None
            if trader is not None:
                interp_engine = getattr(trader, "_interpretation_engine", None)
                if interp_engine is not None:
                    interp_engine.write_all_reports()
                    interpretation_stats = {
                        "interpreted": interp_engine.stats.interpreted,
                        "opportunity_hints_emitted": interp_engine.stats.opportunity_hints_emitted,
                        "evidence_pieces_added": interp_engine.stats.evidence_pieces_added,
                    }
            write_indicator_interpretation_validation_report(
                project_root,
                conservative_metrics=result.conservative_metrics,
                interpretation_stats=interpretation_stats,
            )
            if trader is not None:
                forecast_engine = getattr(trader, "_forecast_engine", None)
                if forecast_engine is not None:
                    forecast_engine.write_forecast_quality_report()
                psych_engine = getattr(trader, "_psychology_engine", None)
                if psych_engine is not None:
                    psych_engine.write_all_reports()
                memory_engine = getattr(trader, "_memory_engine", None)
                if memory_engine is not None:
                    memory_engine.write_all_reports()
                reasoning_layer = getattr(trader, "_reasoning_layer", None)
                if reasoning_layer is not None:
                    reasoning_layer.write_human_trader_reasoning_report()

            quality_stats: dict = {
                "interpretation": interpretation_stats or {},
                "synthesis": synthesis_stats or {},
                "rejection": rejection_stats or {},
            }
            if trader is not None:
                forecast_engine = getattr(trader, "_forecast_engine", None)
                if forecast_engine is not None:
                    n = max(forecast_engine.stats.forecasts_issued, 1)
                    quality_stats["forecast"] = {
                        "forecasts_issued": forecast_engine.stats.forecasts_issued,
                        "synthesis_informed": forecast_engine.stats.synthesis_informed,
                        "psychology_informed": forecast_engine.stats.psychology_informed,
                        "evolution_informed": forecast_engine.stats.evolution_informed,
                        "memory_informed": forecast_engine.stats.memory_informed,
                        "avg_continuation": forecast_engine._prob_sums.get("continuation", 0) / n,
                        "avg_reversal": forecast_engine._prob_sums.get("reversal", 0) / n,
                        "most_likely_counts": dict(forecast_engine.stats.most_likely_counts),
                    }
                psych_engine = getattr(trader, "_psychology_engine", None)
                if psych_engine is not None:
                    quality_stats["psychology"] = {
                        "inferred": psych_engine.stats.inferred,
                        "opportunity_expansions_emitted": psych_engine.stats.opportunity_expansions_emitted,
                        "evidence_pieces_added": psych_engine.stats.evidence_pieces_added,
                    }
                memory_engine = getattr(trader, "_memory_engine", None)
                if memory_engine is not None:
                    quality_stats["memory"] = {
                        "recorded": memory_engine.stats.recorded,
                        "recalls": memory_engine.stats.recalls,
                        "successes_tracked": memory_engine.stats.successes_tracked,
                        "failures_tracked": memory_engine.stats.failures_tracked,
                        "evidence_pieces_added": memory_engine.stats.evidence_pieces_added,
                    }
                reasoning_layer = getattr(trader, "_reasoning_layer", None)
                if reasoning_layer is not None:
                    quality_stats["reasoning"] = {
                        "explained": reasoning_layer.stats.explained,
                        "evidence_pieces_added": reasoning_layer.stats.evidence_pieces_added,
                    }
                harvest_engine = getattr(trader, "_harvest_engine", None)
                if harvest_engine is not None:
                    hstats = getattr(harvest_engine, "stats", None)
                    if hstats is not None:
                        quality_stats["harvest"] = {
                            "candles_probed": hstats.candles_probed,
                            "windows_detected": hstats.windows_detected,
                            "micro_harvests_approved": hstats.micro_harvests_approved,
                            "story_overrides": hstats.story_overrides,
                            "patterns": dict(hstats.patterns),
                            "missed_reasons": dict(hstats.missed_reasons),
                        }
            from intelligence.participation_tracker import get_participation_tracker

            quality_stats["participation"] = get_participation_tracker().summary()
            write_intelligence_enhancement_validation_report(
                project_root,
                conservative_metrics=result.conservative_metrics,
                quality_stats=quality_stats,
            )
            from intelligence.participation_reports import write_all_participation_reports

            write_all_participation_reports(
                project_root,
                quality_stats=quality_stats,
                harvest_stats=quality_stats.get("harvest"),
            )
            write_story_aware_participation_validation_report(
                project_root,
                conservative_metrics=result.conservative_metrics,
                quality_stats=quality_stats,
                harvest_stats=quality_stats.get("harvest"),
            )
            from intelligence.kraitos_thesis_doctrine import (
                get_thesis_tracker,
                write_thesis_doctrine_report,
            )

            thesis_stats = get_thesis_tracker().summary()
            quality_stats["thesis"] = thesis_stats
            write_thesis_doctrine_report(project_root)
            write_thesis_doctrine_validation_report(
                project_root,
                conservative_metrics=result.conservative_metrics,
                thesis_stats=thesis_stats,
            )
            tracker.write_diagnostic(project_root / "logs" / "council_trade_frequency_diagnostic.md")
            from council.opportunity_acceptance_log import OpportunityAcceptanceLog
            OpportunityAcceptanceLog(project_root).write_summary()
            write_post_drawdown_throttle_undo_validation_report(
                project_root,
                current_metrics=metrics_payload["conservative_metrics"],
            )
            from portfolio.doctrine_reports import (
                write_allocation_vs_rejection_report,
                write_portfolio_allocation_doctrine_report,
                write_risk_blocker_removal_report,
                write_risk_manager_allocation_only_report,
                write_risk_manager_allocation_only_validation_report,
            )

            portfolio_engine = getattr(
                getattr(progress, "trader_brain", None), "_portfolio_engine", None
            )
            if portfolio_engine is not None:
                portfolio_engine.write_doctrine_reports()
            else:
                write_portfolio_allocation_doctrine_report(project_root)
                write_allocation_vs_rejection_report(project_root)
            write_risk_manager_allocation_only_report(project_root)
            write_risk_blocker_removal_report(project_root)
            write_risk_manager_allocation_only_validation_report(
                project_root,
                current_metrics=metrics_payload["conservative_metrics"],
            )
            from portfolio.doctrine_reports import (
                write_all_opportunities_taken_report,
                write_simultaneous_trade_capacity_report,
                write_unlimited_opportunity_execution_report,
                write_unlimited_opportunity_validation_report,
            )

            write_unlimited_opportunity_execution_report(project_root)
            write_all_opportunities_taken_report(project_root)
            write_simultaneous_trade_capacity_report(project_root)
            write_unlimited_opportunity_validation_report(
                project_root,
                current_metrics=metrics_payload["conservative_metrics"],
            )
            gate_report = auditor.check_validation_gates(
                result.conservative_metrics,
                paper_metrics=paper_metrics,
            )
            write_brain_separation_reports(
                project_root,
                trader=getattr(progress, "trader_brain", None),
                auditor=auditor,
                metrics=result.conservative_metrics,
                gate_report=gate_report,
            )
            auditor.record_violation_fixed(
                "Removed StrategyQualityGate from trader discovery path"
            )
            auditor.record_violation_fixed(
                "Moved conservative execution to AuditorBrain ownership"
            )
            status = "SUCCESS"
    except LockHeldError as exc:
        interruption_reason = str(exc)
        logger.error("Validation refused: {}", exc)
        status = "REFUSED"
        return 2
    except KeyboardInterrupt:
        interruption_reason = "Interrupted by user (KeyboardInterrupt)"
        status = "INTERRUPTED"
        logger.warning(interruption_reason)
        return 130
    except Exception as exc:
        interruption_reason = f"Validation failed: {exc}"
        status = "FAILED"
        logger.exception(interruption_reason)
        return 1
    finally:
        finished_at = datetime.now(timezone.utc)
        if progress is not None:
            progress.finalize()
        _write_run_report(
            project_root,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            lock_info=lock_info,
            interruption_reason=interruption_reason if status != "SUCCESS" else None,
            metrics_payload=metrics_payload if status == "SUCCESS" else None,
        )

    logger.info(
        "Validation complete: trades={} win_rate={:.1%} pf={}",
        metrics_payload["summary"]["total_trades"] if metrics_payload else 0,
        float(metrics_payload["summary"]["win_rate_backtest"]) if metrics_payload else 0.0,
        metrics_payload["summary"]["profit_factor_backtest"] if metrics_payload else 0,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return run_single_validation(_project_root(), force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
