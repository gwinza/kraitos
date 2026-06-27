"""Runtime metrics for unlimited opportunity execution doctrine."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter


@dataclass
class UnlimitedOpportunityTracker:
    """Accumulate per-cycle opportunity execution stats."""

    opportunities_seen: int = 0
    opportunities_taken: int = 0
    opportunities_rejected: int = 0
    rejection_reasons: Counter[str] = field(default_factory=Counter)
    max_simultaneous_open: int = 0
    simultaneous_samples: list[int] = field(default_factory=list)
    trades_per_timestamp: Counter[str] = field(default_factory=Counter)
    trades_per_symbol: Counter[str] = field(default_factory=Counter)
    trades_per_class: Counter[str] = field(default_factory=Counter)
    remaining_caps: list[str] = field(default_factory=list)

    def record_candidates(self, *, moment_key: str, candidates: list[object]) -> None:
        self.opportunities_seen += len(candidates)
        for candidate in candidates:
            symbol = getattr(candidate, "symbol", "")
            setup = getattr(candidate, "setup_kind", "harvest")
            trade_intent = getattr(candidate, "trade_intent", False)
            entry = getattr(candidate, "entry", None)
            risk = getattr(candidate, "risk", None)
            reason = ""
            if entry is not None and getattr(entry, "explanation", None):
                reason = entry.explanation
            elif risk is not None:
                reason = getattr(risk, "reason", "")
            if trade_intent:
                self.opportunities_taken += 1
                self.trades_per_timestamp[moment_key] += 1
                self.trades_per_symbol[symbol] += 1
                self.trades_per_class[setup] += 1
            else:
                self.opportunities_rejected += 1
                self.rejection_reasons[reason[:80] or "no_trade"] += 1

    def record_cycle(
        self,
        *,
        moment_key: str,
        candidates: list[object],
        signals: list[object],
    ) -> None:
        self.opportunities_seen += len(candidates)
        for candidate, signal in zip(candidates, signals):
            symbol = getattr(candidate, "symbol", "")
            setup = getattr(candidate, "setup_kind", "harvest")
            decision = getattr(signal, "decision", "NO_TRADE")
            reason = getattr(signal, "reason", "")
            if decision == "TRADE":
                self.opportunities_taken += 1
                self.trades_per_timestamp[moment_key] += 1
                self.trades_per_symbol[symbol] += 1
                self.trades_per_class[setup] += 1
            else:
                self.opportunities_rejected += 1
                self.rejection_reasons[reason[:80] or "no_trade"] += 1

    def record_open_count(self, count: int) -> None:
        self.simultaneous_samples.append(count)
        self.max_simultaneous_open = max(self.max_simultaneous_open, count)

    @property
    def avg_simultaneous_open(self) -> float:
        if not self.simultaneous_samples:
            return 0.0
        return sum(self.simultaneous_samples) / len(self.simultaneous_samples)

    def summary(self) -> dict:
        return {
            "opportunities_seen": self.opportunities_seen,
            "opportunities_taken": self.opportunities_taken,
            "opportunities_rejected": self.opportunities_rejected,
            "max_simultaneous_open": self.max_simultaneous_open,
            "avg_simultaneous_open": round(self.avg_simultaneous_open, 2),
            "remaining_caps": list(self.remaining_caps),
        }


_GLOBAL_TRACKER = UnlimitedOpportunityTracker()


def get_unlimited_opportunity_tracker() -> UnlimitedOpportunityTracker:
    return _GLOBAL_TRACKER


def reset_unlimited_opportunity_tracker() -> UnlimitedOpportunityTracker:
    global _GLOBAL_TRACKER
    _GLOBAL_TRACKER = UnlimitedOpportunityTracker()
    return _GLOBAL_TRACKER
