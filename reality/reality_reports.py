"""V8 Reality Engine logging."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from reality.reality_models import REALITY_FIRST_LAW, RealityDecision


def reality_journal_fields(decision: RealityDecision | None) -> dict[str, object]:
    if decision is None:
        return {
            "reality_model": "",
            "convergence_score": 0.0,
            "reality_narrative": "",
            "reality_snapshot": "",
            "world_models_active": 0,
        }
    return {
        "reality_model": decision.thesis.reality_model,
        "convergence_score": decision.convergence.convergence_score,
        "reality_narrative": decision.thesis.reality_narrative[:500],
        "reality_snapshot": json.dumps(decision.to_dict(), separators=(",", ":"), ensure_ascii=True),
        "world_models_active": decision.convergence.active_count,
    }


class RealityReportWriter:
    """Write logs/reality_engine_report.md each cycle."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._latest: dict[str, RealityDecision] = {}

    def record(self, symbol: str, decision: RealityDecision) -> None:
        self._latest[symbol.strip().upper()] = decision

    def write_report(self, path: Path | None = None) -> Path | None:
        if not self._latest:
            return None
        report_path = path or (self.project_root / "logs" / "reality_engine_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Reality Engine Report (V8)",
            "",
            f"**Generated:** {now}",
            "",
            REALITY_FIRST_LAW,
            "",
            "Evidence → World Models → Elimination → Convergence → Expression",
            "",
        ]
        for symbol in sorted(self._latest):
            d = self._latest[symbol]
            lines.extend([
                f"## {symbol}",
                "",
                f"**Convergence:** {d.convergence.convergence_score:.0f}/100 "
                f"(uncertainty {d.convergence.uncertainty:.0f})",
                f"**Dominant reality:** {d.convergence.dominant_model_name or 'none'}",
                f"**Participation:** {d.participation} @ {d.allocation_multiplier:.0%}",
                f"**Reason:** {d.reason}",
                "",
                "### Reality narrative",
                "",
                d.thesis.reality_narrative,
                "",
                "### World Models",
                "",
                "| Model | Power | Status |",
                "|-------|-------|--------|",
            ])
            for model in sorted(d.world_models, key=lambda m: -m.explanatory_power)[:8]:
                lines.append(
                    f"| {model.name} | {model.explanatory_power:.0f}% | {model.status} |"
                )
            lines.extend([
                "",
                "### Thesis",
                "",
                f"- Side: {d.thesis.side}",
                f"- Strategy: {d.thesis.selected_strategy}",
                f"- Thesis clear: {'YES' if d.thesis.thesis_clear else 'NO'}",
                f"- Invalidation: {d.thesis.invalidation[:100]}",
                "",
            ])
            if not d.thesis.thesis_clear:
                lines.append(f"*Observing:* {d.thesis.rejection_reason}")
                lines.append("")

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_cycle_jsonl(self, decision: RealityDecision) -> Path:
        path = self.project_root / "logs" / "json" / "reality_cycles.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), **decision.to_dict()}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
        return path
