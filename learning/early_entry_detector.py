"""Early entry detector — learn from good_idea_early losses and delay confirmation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Literal

Side = Literal["buy", "sell"]

MEMORY_FILENAME = "early_entry_memory.json"
MIN_SAMPLES_TO_DELAY = 3
DELAY_CONFIDENCE_PENALTY = 8.0
MIN_DELAY_CONFIRMATION = 68.0


@dataclass
class EarlyEntryRecord:
    """Per symbol/setup early-entry loss pattern."""

    symbol: str
    entry_type: str
    side: str
    early_losses: int = 0
    confirmed_wins: int = 0
    last_loss_r: float = 0.0

    @property
    def should_delay(self) -> bool:
        return self.early_losses >= MIN_SAMPLES_TO_DELAY and self.early_losses > self.confirmed_wins

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "entry_type": self.entry_type,
            "side": self.side,
            "early_losses": self.early_losses,
            "confirmed_wins": self.confirmed_wins,
            "last_loss_r": round(self.last_loss_r, 4),
            "should_delay": self.should_delay,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EarlyEntryRecord:
        return cls(
            symbol=str(payload.get("symbol", "")),
            entry_type=str(payload.get("entry_type", "unknown")),
            side=str(payload.get("side", "buy")),
            early_losses=int(payload.get("early_losses", 0)),
            confirmed_wins=int(payload.get("confirmed_wins", 0)),
            last_loss_r=float(payload.get("last_loss_r", 0.0)),
        )


@dataclass
class EarlyEntryDelayDecision:
    """Whether patience should wait for extra confirmation."""

    delay: bool
    confidence_penalty: float
    reason: str


class EarlyEntryDetector:
    """
    Track good_idea_early losses and require stronger confirmation before re-entry.

    When the thesis was right but timing was early, future entries on the same
    symbol/setup wait until price confirms (higher bar in patience engine).
    """

    def __init__(self, project_root: Path | None) -> None:
        self._root = project_root
        self._path = (
            (project_root / "logs" / MEMORY_FILENAME) if project_root else None
        )
        self._lock = Lock()
        self._records: dict[str, EarlyEntryRecord] = {}
        self._load()

    def record_outcome(
        self,
        *,
        symbol: str,
        side: Side,
        entry_type: str,
        loss_class: str,
        r_multiple: float,
        won: bool,
        had_confirmation: bool = False,
    ) -> None:
        """Update memory from a closed trade."""
        if loss_class == "good_idea_early" or (
            not won and r_multiple <= -0.5 and loss_class in {"", "unknown", "good_idea_no_acceptance"}
        ):
            if loss_class not in {"", "unknown", "good_idea_early", "good_idea_no_acceptance"}:
                return
            key = self._key(symbol, entry_type, side)
            with self._lock:
                rec = self._records.get(key) or EarlyEntryRecord(
                    symbol=symbol.strip().upper(),
                    entry_type=entry_type or "unknown",
                    side=side,
                )
                rec.early_losses += 1
                rec.last_loss_r = r_multiple
                self._records[key] = rec
                self._save()
            return

        if won and had_confirmation:
            key = self._key(symbol, entry_type, side)
            with self._lock:
                rec = self._records.get(key)
                if rec is None:
                    return
                rec.confirmed_wins += 1
                self._save()

    def evaluate_delay(
        self,
        *,
        symbol: str,
        side: Side,
        entry_type: str,
        confirmation_strength: float,
    ) -> EarlyEntryDelayDecision:
        """Return whether entry should wait for stronger confirmation."""
        key = self._key(symbol, entry_type, side)
        rec = self._records.get(key)
        if rec is None or not rec.should_delay:
            return EarlyEntryDelayDecision(False, 0.0, "")

        min_strength = MIN_DELAY_CONFIRMATION + DELAY_CONFIDENCE_PENALTY
        if confirmation_strength >= min_strength:
            return EarlyEntryDelayDecision(
                False,
                0.0,
                f"Early-entry memory satisfied — confirmation {confirmation_strength:.0f}%",
            )

        return EarlyEntryDelayDecision(
            delay=True,
            confidence_penalty=DELAY_CONFIDENCE_PENALTY,
            reason=(
                f"Early-entry memory: {rec.early_losses} premature {entry_type} losses on "
                f"{symbol} — await stronger confirmation (need ≥{min_strength:.0f}%)"
            ),
        )

    def classify_early_entry(
        self,
        *,
        side: Side,
        story_direction: str,
        entry_type: str,
        had_confirmation: bool,
        r_multiple: float,
        bars_to_favourable: int | None,
    ) -> str:
        """Classify loss as good_idea_early when thesis aligned but confirmation missing."""
        aligned = (
            (side == "buy" and story_direction == "bullish")
            or (side == "sell" and story_direction == "bearish")
        )
        if not aligned or r_multiple > -0.25:
            return "unknown"

        if had_confirmation:
            return "unknown"

        if bars_to_favourable is not None and bars_to_favourable <= 8:
            return "good_idea_early"

        if entry_type in {
            "pullback_into_value",
            "retest_broken_structure",
            "liquidity_sweep_rejection",
        }:
            return "good_idea_early"
        return "unknown"

    @staticmethod
    def _key(symbol: str, entry_type: str, side: str) -> str:
        return f"{symbol.strip().upper()}|{entry_type or 'unknown'}|{side}"

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            with self._path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            for item in payload.get("records", []):
                rec = EarlyEntryRecord.from_dict(item)
                self._records[self._key(rec.symbol, rec.entry_type, rec.side)] = rec
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            self._records = {}

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "records": [rec.to_dict() for rec in self._records.values()],
        }
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)


_detector_cache: dict[str, EarlyEntryDetector] = {}


def get_early_entry_detector(project_root: Path | None) -> EarlyEntryDetector:
    """Return cached early-entry detector for project root."""
    key = str(project_root) if project_root else "__none__"
    if key not in _detector_cache:
        _detector_cache[key] = EarlyEntryDetector(project_root)
    return _detector_cache[key]


__all__ = [
    "EarlyEntryDelayDecision",
    "EarlyEntryDetector",
    "EarlyEntryRecord",
    "get_early_entry_detector",
]
