"""Persist council member performance per regime."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEMORY_FILENAME = "council_memory.json"

COUNCIL_MEMBERS = (
    "story",
    "trend",
    "structure",
    "liquidity",
    "volume",
    "volatility",
    "order_flow",
    "session",
    "psychology",
    "memory",
    "risk",
    "execution",
    # Legacy observer council keys (backward compatible)
    "price_action",
    "market_structure",
    "opportunity",
)


@dataclass
class MemberPerformance:
    """Performance stats for one council member in a regime bucket."""

    member: str
    regime: str
    trades: int = 0
    wins: int = 0
    win_rate: float = 0.0
    average_confidence: float = 0.0
    calibration_score: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "member": self.member,
            "regime": self.regime,
            "trades": self.trades,
            "wins": self.wins,
            "win_rate": round(self.win_rate, 4),
            "average_confidence": round(self.average_confidence, 2),
            "calibration_score": round(self.calibration_score, 4),
        }


@dataclass
class CouncilMemory:
    """Track which council members perform best per regime."""

    project_root: Path
    records: dict[str, MemberPerformance] = field(default_factory=dict)

    def _key(self, member: str, regime: str) -> str:
        return f"{member}|{regime.strip().lower()}"

    def record_outcome(
        self,
        *,
        member: str,
        regime: str,
        confidence: float,
        success: bool,
    ) -> None:
        key = self._key(member, regime)
        rec = self.records.get(key)
        if rec is None:
            rec = MemberPerformance(member=member, regime=regime)
            self.records[key] = rec
        rec.trades += 1
        if success:
            rec.wins += 1
        rec.win_rate = rec.wins / max(rec.trades, 1)
        rec.average_confidence = (
            rec.average_confidence * (rec.trades - 1) + confidence
        ) / rec.trades
        hit_rate = rec.win_rate
        conf_norm = rec.average_confidence / 100.0
        rec.calibration_score = 1.0 - abs(hit_rate - conf_norm)

    def weight_for(self, member: str, regime: str) -> float:
        """Return voting weight boost from historical calibration (0.8–1.2)."""
        rec = self.records.get(self._key(member, regime))
        if rec is None or rec.trades < 3:
            return 1.0
        return max(0.8, min(1.2, 0.9 + rec.calibration_score * 0.3))

    def save(self) -> Path:
        path = self.project_root / "logs" / MEMORY_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "records": [r.to_dict() for r in self.records.values()],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def load(self) -> None:
        path = self.project_root / "logs" / MEMORY_FILENAME
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for item in data.get("records", []):
                rec = MemberPerformance(
                    member=item["member"],
                    regime=item["regime"],
                    trades=int(item.get("trades", 0)),
                    wins=int(item.get("wins", 0)),
                    win_rate=float(item.get("win_rate", 0.0)),
                    average_confidence=float(item.get("average_confidence", 0.0)),
                    calibration_score=float(item.get("calibration_score", 0.5)),
                )
                self.records[self._key(rec.member, rec.regime)] = rec
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass

    def best_members(self, regime: str, top_n: int = 3) -> list[str]:
        candidates = [
            r for r in self.records.values()
            if r.regime == regime and r.trades >= 3
        ]
        candidates.sort(key=lambda r: r.calibration_score, reverse=True)
        return [r.member for r in candidates[:top_n]]
