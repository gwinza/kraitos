"""Markdown reports for Kraitos V3 Cognitive Council deliberations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from council.cognitive_models import CIODecision


def cognitive_journal_fields(decision: CIODecision | None) -> dict[str, object]:
    """Extract CIO fields for trade journal rows."""
    if decision is None:
        return {
            "cio_confidence": 0.0,
            "cio_allocation": 0.0,
            "cio_mode": "",
            "cio_summary": "",
            "cognitive_snapshot": "",
        }
    execution = decision.execution
    return {
        "cio_confidence": round(decision.thesis.confidence, 2),
        "cio_allocation": round(execution.allocation_multiplier, 4),
        "cio_mode": execution.mode,
        "cio_summary": decision.summary[:500],
        "cognitive_snapshot": json.dumps(
            decision.to_dict(),
            separators=(",", ":"),
            ensure_ascii=True,
        ),
    }


class CognitiveReportWriter:
    """Write CIO deliberation and council evidence reports."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._latest: dict[str, CIODecision] = {}

    def record(self, symbol: str, decision: CIODecision) -> None:
        self._latest[symbol.strip().upper()] = decision

    def write_report(self, path: Path | None = None) -> Path | None:
        if not self._latest:
            return None
        report_path = path or (self.project_root / "logs" / "cognitive_council_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Cognitive Council Report",
            "",
            f"**Generated:** {now}",
            "",
            "Kraitos V3 parallel cognitive architecture — twelve specialist councils",
            "deliberate simultaneously; the CIO fuses evidence into one probabilistic thesis.",
            "",
        ]
        for symbol in sorted(self._latest):
            decision = self._latest[symbol]
            thesis = decision.thesis
            execution = decision.execution
            understanding = thesis.market_understanding
            lines.extend([
                f"## {symbol}",
                "",
                f"**CIO summary:** {decision.summary}",
                f"**Regime:** {decision.regime}",
                f"**Can trade:** {'YES' if decision.can_trade else 'NO'}",
                f"**Observe only:** {'YES' if decision.observe_only else 'NO'}",
                "",
                "### Market understanding",
                "",
                f"- **What:** {understanding.what_is_happening[:240]}",
                f"- **Why:** {understanding.why_it_is_happening[:240]}",
                f"- **Who controls:** {understanding.who_controls}",
                f"- **Liquidity:** {understanding.liquidity_location}",
                f"- **Destination:** {understanding.price_destination}",
                f"- **Smart money:** {understanding.smart_money_view[:200]}",
                f"- **Highest probability:** {understanding.highest_probability_outcome}",
                "",
                "### Probabilistic thesis",
                "",
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| Side | {thesis.side} |",
                f"| Confidence | {thesis.confidence:.0f}/100 |",
                f"| P(success) | {thesis.success_probability:.0%} |",
                f"| Expected R | {thesis.expected_reward_r:.2f} |",
                f"| Opportunity quality | {thesis.opportunity_quality:.0f}/100 |",
                f"| Risk score | {thesis.risk_score:.1f} |",
                "",
                f"**Narrative:** {thesis.narrative[:300]}",
                "",
                f"**Forecast:** {thesis.forecast[:300]}",
                "",
                "### Execution strategy",
                "",
                f"- **Mode:** {execution.mode}",
                f"- **Allocation:** {execution.allocation_multiplier:.0%}",
                f"- **Timing:** {execution.timing_guidance}",
                f"- **Entry style:** {execution.entry_style}",
                f"- **Rationale:** {execution.rationale}",
                "",
            ])
            if decision.hard_vetoes:
                lines.append("### Hard vetoes")
                lines.append("")
                for veto in decision.hard_vetoes:
                    lines.append(f"- `{veto.code}` — {veto.reason}")
                lines.append("")

            if thesis.conflicts:
                lines.append("### Conflicts resolved")
                lines.append("")
                for conflict in thesis.conflicts:
                    lines.append(f"- {conflict}")
                lines.append("")

            lines.extend([
                "### Council observations",
                "",
                "| Council | Headline | Direction | Confidence | P(success) |",
                "|---------|----------|-----------|------------|------------|",
            ])
            for obs in decision.council_observations:
                lines.append(
                    f"| {obs.council} | {obs.headline[:50]} | {obs.direction} | "
                    f"{obs.confidence:.0f} | {obs.success_probability:.0%} |"
                )
            lines.append("")

            if decision.deliberation:
                lines.extend([
                    "### Internal deliberation",
                    "",
                ])
                for msg in decision.deliberation[:20]:
                    target = f" → {msg.to_council}" if msg.to_council else ""
                    lines.append(f"- **[R{msg.round_index}] {msg.from_council}{target}:** {msg.message[:200]}")
                lines.append("")

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path
