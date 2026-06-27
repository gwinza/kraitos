"""Runtime markdown reports for the Opportunity Hunter Council."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from council.opportunity_hunter_council import CouncilConsensus


class CouncilReportWriter:
    """Write council debate and consensus reports."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._latest: dict[str, CouncilConsensus] = {}

    def record(self, symbol: str, consensus: CouncilConsensus) -> None:
        self._latest[symbol.strip().upper()] = consensus

    def write_report(self, path: Path | None = None) -> Path | None:
        if not self._latest:
            return None
        report_path = path or (self.project_root / "logs" / "opportunity_hunter_council_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Opportunity Hunter Council Report",
            "",
            f"**Generated:** {now}",
            "",
            "Narrative-first council debate — indicators confirm, never decide.",
            "",
        ]
        for symbol in sorted(self._latest):
            c = self._latest[symbol]
            lines.extend([
                f"## {symbol}",
                "",
                f"**Consensus narrative:** {c.consensus_narrative}",
                f"**Consensus forecast:** {c.consensus_forecast}",
                f"**Consensus confidence:** {c.consensus_confidence:.0f}",
                f"**Opportunity edge:** {c.opportunity_edge}",
                f"**Allow opportunity:** {'YES' if c.allow_opportunity else 'NO'}",
                "",
                "| Professor | Story | Forecast | Confidence |",
                "|-----------|-------|----------|------------|",
            ])
            for op in c.member_opinions:
                lines.append(
                    f"| {op.member_name} | {op.story[:40]} | {op.forecast[:30]} | "
                    f"{op.confidence:.0f} |"
                )
            lines.append("")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path
