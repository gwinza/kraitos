"""Edge alert detection — tracks new/changed opportunities for push notifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sports.models import Decision, MatchAnalysis


@dataclass(frozen=True)
class EdgeAlert:
    match_id: str
    match: str
    decision: str
    grade: str
    edge_score: float
    ev_pct: float | None
    message: str
    is_new: bool

    def to_dict(self) -> dict:
        return {
            "match_id": self.match_id,
            "match": self.match,
            "decision": self.decision,
            "grade": self.grade,
            "edge_score": round(self.edge_score, 1),
            "ev_pct": round(self.ev_pct, 2) if self.ev_pct is not None else None,
            "message": self.message,
            "is_new": self.is_new,
        }


class EdgeAlertService:
    """Detect new A/A+ edges since last scan — for mobile push notifications."""

    NOTIFY_GRADES = frozenset({"A+", "A", "B"})
    NOTIFY_DECISIONS = frozenset({Decision.VALUE_BET, Decision.ARBITRAGE})

    def __init__(self, project_root: Path | None = None) -> None:
        root = project_root or Path(__file__).resolve().parents[1]
        self.state_path = root / "logs" / "sports_edge_state.json"
        self._known: dict[str, dict] = self._load()

    def process(self, analyses: list[MatchAnalysis]) -> list[EdgeAlert]:
        alerts: list[EdgeAlert] = []
        current: dict[str, dict] = {}

        for a in analyses:
            if a.decision not in self.NOTIFY_DECISIONS:
                continue
            if a.grade.value not in self.NOTIFY_GRADES:
                continue

            ev = a.value_bet.ev_pct if a.value_bet else None
            key = a.match_id
            snapshot = {
                "decision": a.decision.value,
                "grade": a.grade.value,
                "edge_score": a.edge_score,
                "ev_pct": ev,
            }
            current[key] = snapshot

            prev = self._known.get(key)
            is_new = prev is None
            upgraded = prev and a.edge_score > prev.get("edge_score", 0) + 5

            if is_new or upgraded:
                msg = (
                    f"{'NEW' if is_new else 'UPGRADED'} EDGE: {a.match_label} — "
                    f"{a.decision.value} ({a.grade.value}) Edge {a.edge_score:.0f}/100"
                )
                if ev:
                    msg += f" | EV {ev:+.1f}%"
                alerts.append(
                    EdgeAlert(
                        match_id=a.match_id,
                        match=a.match_label,
                        decision=a.decision.value,
                        grade=a.grade.value,
                        edge_score=a.edge_score,
                        ev_pct=ev,
                        message=msg,
                        is_new=is_new,
                    )
                )

        self._known = current
        self._save()
        return alerts

    def _load(self) -> dict[str, dict]:
        if self.state_path.exists():
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "edges" in data:
                return data["edges"]
            return data if isinstance(data, dict) else {}
        return {}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"updated": datetime.now(timezone.utc).isoformat(), "edges": self._known}
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
