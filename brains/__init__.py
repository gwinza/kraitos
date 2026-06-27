"""Trader Brain / Auditor Brain — permanent architectural separation."""

from __future__ import annotations

from brains.models import TradeCandidate, TraderBrainStats, TraderContext
from brains.trader_brain import TraderBrain

DNA_STATEMENT = """
Kraitos separates thinking from auditing.

The Trader Brain understands markets, forecasts outcomes, discovers opportunities and executes decisively.

The Auditor Brain validates outcomes using conservative assumptions to prevent bias and self-deception.

The Auditor never dictates how opportunities are discovered.

The Trader hunts.
The Auditor verifies.
""".strip()


def __getattr__(name: str):
    """Lazy exports to avoid circular imports with backtesting."""
    if name == "AuditorBrain":
        from brains.auditor_brain import AuditorBrain

        return AuditorBrain
    if name in {
        "write_auditor_brain_report",
        "write_brain_separation_audit",
        "write_brain_separation_reports",
        "write_trader_brain_report",
    }:
        from brains import reports as _reports

        return getattr(_reports, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AuditorBrain",
    "DNA_STATEMENT",
    "TradeCandidate",
    "TraderBrain",
    "TraderBrainStats",
    "TraderContext",
    "write_auditor_brain_report",
    "write_brain_separation_audit",
    "write_brain_separation_reports",
    "write_trader_brain_report",
]
