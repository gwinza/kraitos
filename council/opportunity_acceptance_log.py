"""Runtime log of council-approved opportunities."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class AcceptedOpportunity:
    """One council-approved trade opportunity."""

    symbol: str
    trace_id: str
    timestamp: str
    narrative: str
    micro_class: str | None
    council_votes_for: int
    council_votes_against: int
    council_vote_breakdown: tuple[tuple[str, bool, float], ...]
    price_action_reason: str
    volume_reason: str
    expected_pips: float
    strategy_selected: str
    expansion_mode: bool
    micro_harvest: bool

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["council_vote_breakdown"] = [
            {"member": m, "approve": bool(a), "confidence": float(c)}
            for m, a, c in self.council_vote_breakdown
        ]
        payload["expansion_mode"] = bool(payload["expansion_mode"])
        payload["micro_harvest"] = bool(payload["micro_harvest"])
        return payload


class OpportunityAcceptanceLog:
    """Append accepted opportunities to JSONL + markdown summary."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._entries: list[AcceptedOpportunity] = []
        self._lock = Lock()
        self._jsonl_path = self.project_root / "logs" / "json" / "council_opportunity_acceptance.jsonl"
        self._md_path = self.project_root / "logs" / "council_opportunity_acceptance_log.md"

    def record(self, entry: AcceptedOpportunity) -> None:
        with self._lock:
            self._entries.append(entry)
            self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self._jsonl_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry.to_dict()) + "\n")

    def write_summary(self) -> Path | None:
        with self._lock:
            entries = list(self._entries)
            if not entries and self._jsonl_path.exists():
                entries = self._load_from_jsonl()
            if not entries:
                return None
            now = datetime.now(timezone.utc).isoformat()
            lines = [
                "# Council Opportunity Acceptance Log",
                "",
                f"**Generated:** {now}",
                f"**Accepted opportunities:** {len(entries)}",
                "",
                "| Symbol | Narrative | Votes | Expected pips | Strategy | Micro |",
                "|--------|-----------|-------|---------------|----------|-------|",
            ]
            for e in entries[-50:]:
                votes = f"{e.council_votes_for}/{e.council_votes_for + e.council_votes_against}"
                micro = e.micro_class or ("Y" if e.micro_harvest else "—")
                lines.append(
                    f"| {e.symbol} | {e.narrative[:35]} | {votes} | "
                    f"{e.expected_pips:.1f} | {e.strategy_selected} | {micro} |"
                )
            lines.extend([
                "",
                "## Recent detail",
                "",
            ])
            for e in entries[-10:]:
                lines.extend([
                    f"### {e.symbol} @ {e.timestamp}",
                    "",
                    f"- **Narrative:** {e.narrative}",
                    f"- **Micro class:** {e.micro_class or '—'}",
                    f"- **Council votes:** {e.council_votes_for} for / {e.council_votes_against} against",
                    f"- **Price action:** {e.price_action_reason}",
                    f"- **Volume:** {e.volume_reason}",
                    f"- **Expected pips:** {e.expected_pips:.1f}",
                    f"- **Strategy:** {e.strategy_selected}",
                    "",
                ])
            self._md_path.parent.mkdir(parents=True, exist_ok=True)
            self._md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return self._md_path

    def _load_from_jsonl(self) -> list[AcceptedOpportunity]:
        loaded: list[AcceptedOpportunity] = []
        if not self._jsonl_path.exists():
            return loaded
        for line in self._jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            breakdown = tuple(
                (item["member"], item["approve"], float(item["confidence"]))
                for item in payload.get("council_vote_breakdown", [])
            )
            loaded.append(
                AcceptedOpportunity(
                    symbol=payload["symbol"],
                    trace_id=payload["trace_id"],
                    timestamp=payload["timestamp"],
                    narrative=payload["narrative"],
                    micro_class=payload.get("micro_class"),
                    council_votes_for=int(payload["council_votes_for"]),
                    council_votes_against=int(payload["council_votes_against"]),
                    council_vote_breakdown=breakdown,
                    price_action_reason=payload["price_action_reason"],
                    volume_reason=payload["volume_reason"],
                    expected_pips=float(payload["expected_pips"]),
                    strategy_selected=payload["strategy_selected"],
                    expansion_mode=bool(payload["expansion_mode"]),
                    micro_harvest=bool(payload["micro_harvest"]),
                )
            )
        return loaded

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            if self._jsonl_path.exists():
                self._jsonl_path.unlink()
