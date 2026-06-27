"""Structured system error reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from logs.event_logger import KraitosEventLogger


class ErrorReporter:
    """Capture and retrieve system errors for the command center."""

    def __init__(
        self,
        *,
        project_root: Path,
        event_logger: KraitosEventLogger | None = None,
    ) -> None:
        self.project_root = project_root
        self.logs_dir = project_root / "logs"
        self._event_logger = event_logger
        self._critical_errors: list[str] = []

    def report(
        self,
        message: str,
        *,
        exc: BaseException | None = None,
        symbol: str | None = None,
        trace_id: str | None = None,
        critical: bool = False,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Log a system error to structured logs and the in-memory critical list."""
        if self._event_logger is not None:
            self._event_logger.error(
                message,
                exc=exc,
                symbol=symbol,
                trace_id=trace_id,
                data=data,
            )
        if critical:
            cleaned = message.strip()
            if cleaned and cleaned not in self._critical_errors:
                self._critical_errors.append(cleaned)

    @property
    def critical_errors(self) -> tuple[str, ...]:
        return tuple(self._critical_errors)

    def clear_critical_errors(self) -> None:
        self._critical_errors.clear()

    def recent_errors(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return recent errors from the JSONL error log."""
        path = self.logs_dir / "json" / "errors.jsonl"
        if not path.exists():
            return []

        lines: list[str] = []
        try:
            with path.open(encoding="utf-8") as handle:
                lines = [line.strip() for line in handle if line.strip()]
        except OSError:
            return []

        records: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(records))
