"""V5 Market Mind logging — full cognitive cycle transparency."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from intelligence.market_mind_models import MARKET_MIND_PHILOSOPHY, MarketMindDecision
from intelligence.picture_reports import storyteller_journal_fields


def market_mind_journal_fields(decision: MarketMindDecision | None) -> dict[str, object]:
    """Extract V5 fields for trade journal rows."""
    if decision is None:
        base = storyteller_journal_fields(None)
        base["mind_state"] = ""
        base["market_mind_snapshot"] = ""
        return base
    if not hasattr(decision, "as_storyteller"):
        base = storyteller_journal_fields(None)
        base["mind_state"] = getattr(decision, "mind_state", "")
        base["market_mind_snapshot"] = ""
        return base
    base = storyteller_journal_fields(decision.as_storyteller())
    base["mind_state"] = decision.mind_state
    base["market_mind_snapshot"] = json.dumps(
        decision.to_dict(),
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return base


class MarketMindReportWriter:
    """Write logs/market_mind_report.md each cycle."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._latest: dict[str, MarketMindDecision] = {}

    def record(self, symbol: str, decision: MarketMindDecision) -> None:
        self._latest[symbol.strip().upper()] = decision

    def write_report(self, path: Path | None = None) -> Path | None:
        if not self._latest:
            return None
        report_path = path or (self.project_root / "logs" / "market_mind_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Market Mind Report (V5)",
            "",
            f"**Generated:** {now}",
            "",
            MARKET_MIND_PHILOSOPHY,
            "",
            "OBSERVE → PICTURE → REASON → THESIS → STRATEGY → EXECUTION → LEARN",
            "",
        ]
        for symbol in sorted(self._latest):
            d = self._latest[symbol]
            lines.extend([
                f"## {symbol}",
                "",
                f"**Mind state:** {d.mind_state}",
                f"**Participation:** {d.participation} @ {d.allocation_multiplier:.0%}",
                f"**Reason:** {d.reason}",
                "",
            ])
            if d.evidence_changes:
                lines.append("### Evidence changes")
                lines.append("")
                for change in d.evidence_changes:
                    lines.append(f"- {change}")
                lines.append("")
            lines.extend([
                "### Narrator",
                "",
                d.narration.full_narration,
                "",
                "### Market picture",
                "",
                f"- Clarity: **{d.picture.clarity}**",
                f"- Regime: {d.picture.regime}",
                f"- Dominant side: {d.picture.dominant_side}",
                f"- Confidence: {d.picture.confidence:.0f}/100",
                f"- Summary: {d.picture.summary}",
                "",
                "**Departments contributing:**",
            ])
            for dept in d.picture.departments:
                lines.append(
                    f"- **{dept.department}** ({dept.confidence:.0f}%): {dept.observation[:90]}"
                )
            if d.picture.contradictions:
                lines.append("")
                lines.append("**Contradictions:**")
                for item in d.picture.contradictions[:4]:
                    lines.append(f"- {item}")
            lines.extend([
                "",
                "### Strategy ranking",
                "",
                "| Strategy | Fit | Rationale |",
                "|----------|-----|-----------|",
            ])
            for fit in d.strategy_rankings[:5]:
                lines.append(
                    f"| {fit.strategy_name} | {fit.fit_score:.0f}% | {fit.rationale[:60]} |"
                )
            lines.extend([
                "",
                "### Trade thesis",
                "",
                f"- Side: {d.thesis.side}",
                f"- Strategy: {d.thesis.selected_strategy}",
                f"- Confidence: {d.thesis.confidence:.0f}/100",
                f"- Thesis clear: {'YES' if d.thesis.thesis_clear else 'NO'}",
                f"- Invalidation: {d.thesis.invalidation[:120]}",
                "",
            ])
            if not d.thesis.thesis_clear:
                lines.append(f"*Observing:* {d.thesis.rejection_reason}")
                lines.append("")

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_cycle_jsonl(self, decision: MarketMindDecision) -> Path:
        path = self.project_root / "logs" / "json" / "market_mind_cycles.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **decision.to_dict(),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
        return path
