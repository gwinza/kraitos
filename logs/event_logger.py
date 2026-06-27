"""
Professional structured event logger for Kraitos.

Persists traceable decisions and system activity to CSV and JSONL files.
"""

from __future__ import annotations

import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger as loguru_logger

from logs.models import EventCategory, LogRecord
from logs.writers import DualFormatWriter

DEFAULT_LOG_DIR = Path(__file__).resolve().parent

_event_logger: KraitosEventLogger | None = None


def _payload_dict(data: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    """Normalize optional event payloads for safe dict merging."""
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    return {"confirmations": data}


class KraitosEventLogger:
    """Structured logger for all Kraitos decision and system events."""

    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = log_dir or DEFAULT_LOG_DIR
        self._writer = DualFormatWriter(self.log_dir)

    def new_trace_id(self) -> str:
        """Create a trace identifier linking related decisions."""
        return uuid.uuid4().hex

    def new_event_id(self) -> str:
        """Create a unique event identifier."""
        return uuid.uuid4().hex

    def log(
        self,
        category: EventCategory,
        event_type: str,
        message: str,
        *,
        trace_id: str | None = None,
        symbol: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> LogRecord:
        """Write a structured event to CSV and JSON logs."""
        record = LogRecord(
            event_id=self.new_event_id(),
            trace_id=trace_id or self.new_trace_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            category=category,
            event_type=event_type,
            message=message,
            symbol=symbol,
            data=data or {},
        )
        self._writer.write(record)
        loguru_logger.debug(
            f"[{record.category}] {record.event_type} trace={record.trace_id}: {record.message}"
        )
        return record

    def system_event(
        self,
        message: str,
        *,
        event_type: str = "info",
        trace_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> LogRecord:
        return self.log(
            "system_events",
            event_type,
            message,
            trace_id=trace_id,
            data=data,
        )

    def trade_decision(
        self,
        message: str,
        *,
        symbol: str,
        trace_id: str,
        action: str,
        data: dict[str, Any] | None = None,
    ) -> LogRecord:
        payload = {"action": action, **(data or {})}
        return self.log(
            "trade_decisions",
            action,
            message,
            trace_id=trace_id,
            symbol=symbol,
            data=payload,
        )

    def rejected_trade(
        self,
        message: str,
        *,
        symbol: str,
        trace_id: str,
        reason: str,
        data: dict[str, Any] | list[Any] | None = None,
    ) -> LogRecord:
        payload = {"reason": reason, **_payload_dict(data)}
        return self.log(
            "rejected_trades",
            "rejected",
            message,
            trace_id=trace_id,
            symbol=symbol,
            data=payload,
        )

    def risk_approval(
        self,
        message: str,
        *,
        symbol: str,
        trace_id: str,
        lot_size: float,
        data: dict[str, Any] | None = None,
    ) -> LogRecord:
        payload = {"lot_size": lot_size, **(data or {})}
        return self.log(
            "risk_approvals",
            "approved",
            message,
            trace_id=trace_id,
            symbol=symbol,
            data=payload,
        )

    def risk_rejection(
        self,
        message: str,
        *,
        symbol: str,
        trace_id: str,
        reason: str,
        data: dict[str, Any] | None = None,
    ) -> LogRecord:
        payload = {"reason": reason, **(data or {})}
        return self.log(
            "risk_rejections",
            "rejected",
            message,
            trace_id=trace_id,
            symbol=symbol,
            data=payload,
        )

    def executed_trade(
        self,
        message: str,
        *,
        symbol: str,
        trace_id: str,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> LogRecord:
        return self.log(
            "executed_trades",
            event_type,
            message,
            trace_id=trace_id,
            symbol=symbol,
            data=data,
        )

    def error(
        self,
        message: str,
        *,
        trace_id: str | None = None,
        symbol: str | None = None,
        exc: BaseException | None = None,
        data: dict[str, Any] | None = None,
    ) -> LogRecord:
        payload = dict(data or {})
        if exc is not None:
            payload["exception_type"] = type(exc).__name__
            payload["exception_message"] = str(exc)
            payload["traceback"] = traceback.format_exc()
        return self.log(
            "errors",
            "error",
            message,
            trace_id=trace_id,
            symbol=symbol,
            data=payload,
        )


def init_event_logger(log_dir: Path | str | None = None) -> KraitosEventLogger:
    """Initialize the global structured event logger."""
    global _event_logger
    path = Path(log_dir) if log_dir is not None else DEFAULT_LOG_DIR
    _event_logger = KraitosEventLogger(path)
    _event_logger.system_event(
        "Kraitos event logger initialized",
        event_type="startup",
        data={"log_dir": str(path)},
    )
    return _event_logger


def get_event_logger() -> KraitosEventLogger:
    """Return the global event logger, initializing if needed."""
    global _event_logger
    if _event_logger is None:
        return init_event_logger()
    return _event_logger
