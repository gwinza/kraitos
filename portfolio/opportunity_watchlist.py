"""Opportunity watchlist — preserve unfunded good setups."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from portfolio.opportunity_score import OpportunityAllocationScore

WatchlistState = Literal[
    "WAITING_FOR_RISK_BUDGET",
    "WAITING_FOR_CORRELATION_RELIEF",
    "WAITING_FOR_SPREAD",
    "WAITING_FOR_CONFIRMATION",
    "EXPIRED",
    "PROMOTED_TO_TRADE",
]


class _StateEnum(str, Enum):
    WAITING_FOR_RISK_BUDGET = "WAITING_FOR_RISK_BUDGET"
    WAITING_FOR_CORRELATION_RELIEF = "WAITING_FOR_CORRELATION_RELIEF"
    WAITING_FOR_SPREAD = "WAITING_FOR_SPREAD"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    EXPIRED = "EXPIRED"
    PROMOTED_TO_TRADE = "PROMOTED_TO_TRADE"


@dataclass
class WatchlistEntry:
    """One watchlisted opportunity."""

    symbol: str
    side: str
    oas: float
    state: WatchlistState
    created_at: datetime
    expires_at: datetime
    reason: str
    trace_id: str = ""
    promoted_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "oas": round(self.oas, 2),
            "state": self.state,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "reason": self.reason,
            "trace_id": self.trace_id,
            "promoted_at": self.promoted_at.isoformat() if self.promoted_at else None,
        }


DEFAULT_TTL_HOURS = 4.0


class OpportunityWatchlist:
    """Queue high-OAS setups deferred by budget, correlation, or spread."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        ttl_hours: float = DEFAULT_TTL_HOURS,
        max_entries: int = 50,
    ) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self.ttl_hours = ttl_hours
        self.max_entries = max_entries
        self._entries: dict[str, WatchlistEntry] = {}

    def _key(self, symbol: str, side: str) -> str:
        return f"{symbol.strip().upper()}:{side.strip().lower()}"

    def add(
        self,
        *,
        symbol: str,
        side: str,
        oas: OpportunityAllocationScore,
        state: WatchlistState,
        reason: str,
        trace_id: str = "",
        evaluation_moment: datetime | None = None,
    ) -> WatchlistEntry:
        now = evaluation_moment or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        expires = now + timedelta(hours=self.ttl_hours)
        key = self._key(symbol, side)
        entry = WatchlistEntry(
            symbol=symbol.strip().upper(),
            side=side.strip().lower(),
            oas=oas.oas,
            state=state,
            created_at=now,
            expires_at=expires,
            reason=reason,
            trace_id=trace_id,
        )
        self._entries[key] = entry
        self._prune(now)
        return entry

    def promote(
        self,
        symbol: str,
        side: str,
        *,
        evaluation_moment: datetime | None = None,
    ) -> WatchlistEntry | None:
        key = self._key(symbol, side)
        entry = self._entries.get(key)
        if entry is None:
            return None
        now = evaluation_moment or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        entry.state = "PROMOTED_TO_TRADE"
        entry.promoted_at = now
        return entry

    def expire_stale(self, evaluation_moment: datetime | None = None) -> list[WatchlistEntry]:
        now = evaluation_moment or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        expired: list[WatchlistEntry] = []
        for key, entry in list(self._entries.items()):
            if entry.state == "PROMOTED_TO_TRADE":
                continue
            if now >= entry.expires_at:
                entry.state = "EXPIRED"
                expired.append(entry)
                del self._entries[key]
        return expired

    def waiting(self) -> list[WatchlistEntry]:
        return [
            e for e in self._entries.values()
            if e.state.startswith("WAITING_")
        ]

    def all_entries(self) -> list[WatchlistEntry]:
        return list(self._entries.values())

    def classify_deferral(
        self,
        *,
        heat_over_limit: bool,
        correlation_blocked: bool,
        spread_too_wide: bool,
        needs_confirmation: bool,
    ) -> WatchlistState:
        if spread_too_wide:
            return "WAITING_FOR_SPREAD"
        if correlation_blocked:
            return "WAITING_FOR_CORRELATION_RELIEF"
        if heat_over_limit:
            return "WAITING_FOR_RISK_BUDGET"
        if needs_confirmation:
            return "WAITING_FOR_CONFIRMATION"
        return "WAITING_FOR_RISK_BUDGET"

    def _prune(self, now: datetime) -> None:
        self.expire_stale(now)
        waiting = sorted(
            [e for e in self._entries.values() if e.state.startswith("WAITING_")],
            key=lambda e: e.oas,
            reverse=True,
        )
        while len(waiting) > self.max_entries:
            drop = waiting.pop()
            key = self._key(drop.symbol, drop.side)
            self._entries.pop(key, None)

    def write_report(self) -> Path | None:
        if self.project_root is None:
            return None
        logs = self.project_root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Opportunity Watchlist Report",
            "",
            f"**Generated:** {now}",
            "",
            f"Active entries: **{len(self._entries)}**",
            "",
            "| Symbol | Side | OAS | State | Reason | Expires |",
            "|--------|------|-----|-------|--------|---------|",
        ]
        for entry in sorted(self._entries.values(), key=lambda e: -e.oas):
            lines.append(
                f"| {entry.symbol} | {entry.side} | {entry.oas:.0f} | "
                f"{entry.state} | {entry.reason[:40]} | {entry.expires_at.isoformat()} |"
            )
        path = logs / "opportunity_watchlist_report.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
