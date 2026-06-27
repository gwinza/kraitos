"""Track story-aware participation metrics during validation and live cycles."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from threading import Lock

_lock = Lock()
_tracker: StoryAwareParticipationTracker | None = None


@dataclass
class StoryAwareParticipationTracker:
    """Collect participation doctrine metrics — never used to suppress trades."""

    story_explanations: int = 0
    indicator_interpretations: int = 0
    psychology_inferences: int = 0
    harvest_windows: int = 0
    opportunities_seen: int = 0
    opportunities_taken: int = 0
    opportunities_missed: int = 0
    simultaneous_trades_max: int = 0
    pips_targeted: list[float] = field(default_factory=list)
    pips_captured: list[float] = field(default_factory=list)
    trades_by_class: Counter[str] = field(default_factory=Counter)
    trades_by_asset: Counter[str] = field(default_factory=Counter)
    missed_harvest_reasons: Counter[str] = field(default_factory=Counter)
    harvest_patterns: Counter[str] = field(default_factory=Counter)

    def record_story(self) -> None:
        self.story_explanations += 1

    def record_interpretation(self) -> None:
        self.indicator_interpretations += 1

    def record_psychology(self) -> None:
        self.psychology_inferences += 1

    def record_harvest_window(self, pattern: str) -> None:
        self.harvest_windows += 1
        self.harvest_patterns[pattern] += 1

    def record_opportunity_seen(self) -> None:
        self.opportunities_seen += 1

    def record_opportunity_taken(self, *, symbol: str, tier: str, target_pips: float) -> None:
        self.opportunities_taken += 1
        self.trades_by_class[tier] += 1
        self.trades_by_asset[symbol.strip().upper()] += 1
        if target_pips > 0:
            self.pips_targeted.append(target_pips)

    def record_opportunity_missed(self, reason: str) -> None:
        self.opportunities_missed += 1
        key = (reason or "unknown")[:100]
        self.missed_harvest_reasons[key] += 1

    def record_pips_captured(self, pips: float) -> None:
        if pips != 0.0:
            self.pips_captured.append(abs(pips))

    def record_simultaneous(self, count: int) -> None:
        self.simultaneous_trades_max = max(self.simultaneous_trades_max, count)

    def summary(self) -> dict[str, object]:
        avg_target = (
            sum(self.pips_targeted) / len(self.pips_targeted) if self.pips_targeted else 0.0
        )
        avg_captured = (
            sum(self.pips_captured) / len(self.pips_captured) if self.pips_captured else 0.0
        )
        return {
            "story_explanations": self.story_explanations,
            "indicator_interpretations": self.indicator_interpretations,
            "psychology_inferences": self.psychology_inferences,
            "harvest_windows": self.harvest_windows,
            "opportunities_seen": self.opportunities_seen,
            "opportunities_taken": self.opportunities_taken,
            "opportunities_missed": self.opportunities_missed,
            "simultaneous_trades_max": self.simultaneous_trades_max,
            "avg_pips_targeted": round(avg_target, 2),
            "avg_pips_captured": round(avg_captured, 2),
            "trades_by_class": dict(self.trades_by_class),
            "trades_by_asset": dict(self.trades_by_asset),
            "top_missed_reasons": self.missed_harvest_reasons.most_common(10),
            "harvest_patterns": dict(self.harvest_patterns),
        }


def get_participation_tracker() -> StoryAwareParticipationTracker:
    global _tracker
    with _lock:
        if _tracker is None:
            _tracker = StoryAwareParticipationTracker()
        return _tracker


def reset_participation_tracker() -> StoryAwareParticipationTracker:
    global _tracker
    with _lock:
        _tracker = StoryAwareParticipationTracker()
        return _tracker
