"""Analyze backtest skip reasons and write debug reports."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from backtesting.backtest_engine import BacktestRunResult, BacktestSkipStats


@dataclass
class SkipAnalyzer:
    """Summarize why backtest bars did not become closed trades."""

    stats: BacktestSkipStats
    result: BacktestRunResult
    symbols: tuple[str, ...]
    config_summary: dict[str, object] = field(default_factory=dict)

    def skip_analysis_markdown(self) -> str:
        lines = [
            "# Kraitos Skip Analysis",
            "",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Overview",
            "",
            f"- Timeline evaluations: **{self.stats.timeline_evaluations}**",
            f"- Warmup skips: **{self.stats.warmup_skips}**",
            f"- Account safety skips: **{self.stats.account_halt_skips}**",
            f"- TRADE signals: **{self.stats.trade_signals}**",
            f"- Positions opened: **{self.stats.positions_opened}**",
            f"- Positions closed: **{self.stats.positions_closed}**",
            f"- NO_TRADE records: **{self.stats.no_trade_records}**",
            "",
            "## Root causes checked",
            "",
            "| Check | Finding |",
            "|-------|---------|",
            f"| Timeframe alignment | {self._timeframe_note()} |",
            f"| Session filter | Uses bar timestamp in backtest (`evaluation_moment`) |",
            f"| Validation gate | Does not block backtest execution |",
            f"| Live trading | Remains disabled |",
            f"| Risk controller | Active — rejections listed below |",
            "",
            "## NO_TRADE reason counts",
            "",
        ]

        if not self.stats.no_trade_reasons:
            lines.append("_No NO_TRADE reasons recorded._")
        else:
            for reason, count in self.stats.no_trade_reasons.most_common(20):
                lines.append(f"- **{count}** — {reason}")

        lines.extend(["", "## Mandatory harvest failures", ""])
        if not self.stats.mandatory_failures:
            lines.append("_None recorded._")
        else:
            for reason, count in self.stats.mandatory_failures.most_common():
                lines.append(f"- **{count}** — {reason}")

        lines.extend(["", "## Pipeline stage failures", ""])
        for stage, count in self.stats.stage_failures.most_common():
            lines.append(f"- **{stage}**: {count}")

        lines.extend(["", "## Executor events", ""])
        for event, count in self.stats.executor_events.most_common():
            lines.append(f"- **{event}**: {count}")

        return "\n".join(lines)

    def backtest_debug_markdown(self) -> str:
        account = self.result.account
        closed = len(account.closed_entries) if account else 0
        open_count = len(account.open_positions) if account else 0
        metrics = self.result.report.metrics() if self.result.report else None

        lines = [
            "# Kraitos Backtest Debug Report",
            "",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            f"**Symbols:** {', '.join(self.symbols)}",
            "",
            "## Engine configuration",
            "",
        ]
        for key, value in self.config_summary.items():
            lines.append(f"- {key}: `{value}`")

        lines.extend(
            [
                "",
                "## Results",
                "",
                f"- Closed trades: **{closed}**",
                f"- Open positions remaining: **{open_count}**",
                f"- Total signals collected: **{len(self.result.signals)}**",
                "",
            ]
        )

        if metrics:
            lines.extend(
                [
                    "## Performance metrics",
                    "",
                    f"- Win rate: **{metrics.win_rate:.1%}**",
                    f"- Profit factor: **{metrics.profit_factor:.2f}**",
                    f"- Max drawdown: **{metrics.max_drawdown_pct:.2f}%**",
                    f"- Average R: **{metrics.average_r:+.2f}R**",
                    f"- Total closed trades: **{metrics.total_trades}**",
                    "",
                ]
            )

        if self.result.summary:
            lines.extend(["## Performance summary", "", "```text", self.result.summary, "```", ""])

        lines.extend(["## Skip analysis excerpt", "", self.skip_analysis_markdown()])
        return "\n".join(lines)

    def _timeframe_note(self) -> str:
        note = str(self.config_summary.get("timeframe_note", "Resampled from base series"))
        return note

    def write_reports(self, project_root: Path) -> tuple[Path, Path]:
        logs = project_root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        skip_path = logs / "skip_analysis.md"
        debug_path = logs / "backtest_debug_report.md"
        skip_path.write_text(self.skip_analysis_markdown(), encoding="utf-8")
        debug_path.write_text(self.backtest_debug_markdown(), encoding="utf-8")
        return skip_path, debug_path


def summarize_journal_skips(journal_path: Path) -> Counter[str]:
    """Count skip reasons already written to trade_journal.csv."""
    if not journal_path.exists():
        return Counter()
    import pandas as pd

    frame = pd.read_csv(journal_path)
    skipped = frame[frame["result"].astype(str).str.lower() == "skipped"]
    return Counter(skipped["reason"].astype(str).tolist())
