"""Track pipeline rejection stages for council frequency diagnostics."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


@dataclass
class CouncilRejectionTracker:
    """Accumulate rejection counts across validation timeline evaluations."""

    evaluations: int = 0
    stage_rejections: Counter[str] = field(default_factory=Counter)
    reason_samples: Counter[str] = field(default_factory=Counter)
    council_denied: int = 0
    council_allowed: int = 0
    micro_harvest_allowed: int = 0
    trades_emitted: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record_evaluation(self) -> None:
        with self._lock:
            self.evaluations += 1

    def record_stage(self, stage: str, reason: str = "") -> None:
        with self._lock:
            self.stage_rejections[stage] += 1
            if reason:
                key = reason[:120]
                self.reason_samples[key] += 1

    def record_council(self, *, allowed: bool, micro_harvest: bool = False) -> None:
        with self._lock:
            if allowed:
                self.council_allowed += 1
                if micro_harvest:
                    self.micro_harvest_allowed += 1
            else:
                self.council_denied += 1

    def record_trade(self) -> None:
        with self._lock:
            self.trades_emitted += 1

    def write_diagnostic(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        total_rejects = sum(self.stage_rejections.values())
        lines = [
            "# Council Trade Frequency Diagnostic",
            "",
            f"**Generated:** {now}",
            "",
            "Rejection-path analysis for Opportunity Hunter Council expansion tuning.",
            "",
            "## Summary",
            "",
            f"- Timeline evaluations: **{self.evaluations}**",
            f"- Trades emitted: **{self.trades_emitted}**",
            f"- Council allowed: **{self.council_allowed}** ({self._pct(self.council_allowed, self.evaluations)})",
            f"- Council denied: **{self.council_denied}** ({self._pct(self.council_denied, self.evaluations)})",
            f"- Micro-harvest paths: **{self.micro_harvest_allowed}**",
            f"- Stage rejections: **{total_rejects}**",
            "",
            "## Stage rejection counts",
            "",
            "| Stage | Count | % of evaluations |",
            "|-------|-------|------------------|",
        ]
        for stage, count in self.stage_rejections.most_common():
            lines.append(
                f"| {stage} | {count} | {self._pct(count, self.evaluations)} |"
            )
        if not self.stage_rejections:
            lines.append("| (none recorded) | 0 | 0% |")

        lines.extend([
            "",
            "## Top rejection reasons (sampled)",
            "",
        ])
        for reason, count in self.reason_samples.most_common(25):
            lines.append(f"- **{count}×** {reason}")
        if not self.reason_samples:
            lines.append("- No sampled reasons recorded")

        lines.extend([
            "",
            "## Gate analysis (code paths)",
            "",
            "| Layer | Typical blocker | Expansion fix |",
            "|-------|-----------------|---------------|",
            "| Council | Weighted confidence < threshold | 3-of-6 / 2-of-4 voting, threshold 32 |",
            "| Narrative | No micro-class edge | 7 micro-harvest narrative classes |",
            "| Forecast | Pip range too wide | 1–3 pip micro harvest range |",
            "| Harvest score | Band below conditional | Conditional from 38, council override |",
            "| Dynamic pip | skip_trade (spread/ATR) | Micro spread-aware targets |",
            "| Marketplace | no_trade dominance | Scalp/micro preferred in range |",
            "| Harvest engine | Secondary < 2 | 1 secondary when council micro-harvest |",
            "| Indicators | (confirm only) | Boost only — never block |",
            "",
        ])
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _pct(count: int, total: int) -> str:
        if total <= 0:
            return "0%"
        return f"{100.0 * count / total:.1f}%"


_GLOBAL_TRACKER: CouncilRejectionTracker | None = None


def get_rejection_tracker() -> CouncilRejectionTracker:
    global _GLOBAL_TRACKER
    if _GLOBAL_TRACKER is None:
        _GLOBAL_TRACKER = CouncilRejectionTracker()
    return _GLOBAL_TRACKER


def reset_rejection_tracker() -> CouncilRejectionTracker:
    global _GLOBAL_TRACKER
    _GLOBAL_TRACKER = CouncilRejectionTracker()
    return _GLOBAL_TRACKER
