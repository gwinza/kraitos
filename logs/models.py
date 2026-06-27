"""Logging data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EventCategory = Literal[
    "system_events",
    "trade_decisions",
    "rejected_trades",
    "risk_approvals",
    "risk_rejections",
    "executed_trades",
    "errors",
]

ALL_CATEGORIES: tuple[EventCategory, ...] = (
    "system_events",
    "trade_decisions",
    "rejected_trades",
    "risk_approvals",
    "risk_rejections",
    "executed_trades",
    "errors",
)


@dataclass(frozen=True)
class LogRecord:
    """Structured log record for traceability."""

    event_id: str
    trace_id: str
    timestamp: str
    category: EventCategory
    event_type: str
    message: str
    symbol: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
