"""V4 Picture Theory logging — full decision cycle transparency."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from intelligence.picture_models import StorytellerDecision


def storyteller_journal_fields(decision: StorytellerDecision | None) -> dict[str, object]:
    """Extract V4 fields for trade journal rows."""
    if decision is None:
        return {
            "picture_clarity": "",
            "picture_confidence": 0.0,
            "selected_strategy": "",
            "strategy_fit": 0.0,
            "narrator_story": "",
            "storyteller_snapshot": "",
        }
    top = decision.strategy_rankings[0] if decision.strategy_rankings else None
    return {
        "picture_clarity": decision.picture.clarity,
        "picture_confidence": decision.picture.confidence,
        "selected_strategy": decision.thesis.selected_strategy,
        "strategy_fit": top.fit_score if top else 0.0,
        "narrator_story": decision.narration.full_narration[:500],
        "storyteller_snapshot": json.dumps(
            decision.to_dict(),
            separators=(",", ":"),
            ensure_ascii=True,
        ),
    }


class PictureTheoryReportWriter:
    """Write logs/market_storyteller_report.md each cycle."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._latest: dict[str, StorytellerDecision] = {}

    def record(self, symbol: str, decision: StorytellerDecision) -> None:
        self._latest[symbol.strip().upper()] = decision

    def write_report(self, path: Path | None = None) -> Path | None:
        if not self._latest:
            return None
        report_path = path or (self.project_root / "logs" / "market_storyteller_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Market Storyteller Report (V4)",
            "",
            f"**Generated:** {now}",
            "",
            "Kraitos trades understanding — STORY → PICTURE → THESIS → STRATEGY → EXECUTION",
            "",
        ]
        for symbol in sorted(self._latest):
            d = self._latest[symbol]
            lines.extend([
                f"## {symbol}",
                "",
                f"**Participation:** {d.participation} @ {d.allocation_multiplier:.0%}",
                f"**Reason:** {d.reason}",
                "",
                "### Live story",
                "",
                d.story.narrative,
                "",
                "### Narrator",
                "",
                d.narration.full_narration,
                "",
                "### Fused picture",
                "",
                f"- Clarity: **{d.picture.clarity}**",
                f"- Regime: {d.picture.regime}",
                f"- Dominant side: {d.picture.dominant_side}",
                f"- Confidence: {d.picture.confidence:.0f}/100",
                f"- Summary: {d.picture.summary}",
                "",
                "**Key evidence:**",
            ])
            for item in d.picture.key_evidence[:6]:
                lines.append(f"- {item}")
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
                f"- Allocation: {d.thesis.risk_allocation:.0%}",
                f"- Entry: {d.thesis.entry_logic}",
                f"- Stop: {d.thesis.stop_logic}",
                f"- Target: {d.thesis.target_logic}",
                f"- Invalidation: {d.thesis.invalidation}",
                f"- Thesis clear: {'YES' if d.thesis.thesis_clear else 'NO'}",
                "",
            ])
            if not d.thesis.thesis_clear:
                lines.append(f"*Not trading:* {d.thesis.rejection_reason}")
                lines.append("")

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_cycle_jsonl(self, decision: StorytellerDecision) -> Path:
        path = self.project_root / "logs" / "json" / "storyteller_cycles.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **decision.to_dict(),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
        return path
