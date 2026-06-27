"""Classify runtime log errors for validation gating."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

EXPECTED_TEST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"emergency\s+stop", re.IGNORECASE),
    re.compile(r"operator\s+emergency\s+stop", re.IGNORECASE),
    re.compile(r"\btest\b", re.IGNORECASE),
    re.compile(r"deliberate\s+stop", re.IGNORECASE),
)

CRITICAL_RUNTIME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"unhandled", re.IGNORECASE),
    re.compile(r"traceback", re.IGNORECASE),
    re.compile(r"fatal", re.IGNORECASE),
    re.compile(r"corrupt", re.IGNORECASE),
    re.compile(r"broker\s+connection\s+failed", re.IGNORECASE),
    re.compile(r"data\s+feed\s+lost", re.IGNORECASE),
)


@dataclass
class ErrorClassification:
    """Separated error buckets for validation reporting."""

    expected_test_errors: list[str] = field(default_factory=list)
    real_runtime_errors: list[str] = field(default_factory=list)
    critical_runtime_errors: list[str] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return len(self.critical_runtime_errors)

    @property
    def expected_test_count(self) -> int:
        return len(self.expected_test_errors)

    @property
    def real_runtime_count(self) -> int:
        return len(self.real_runtime_errors)

    def to_dict(self) -> dict:
        return {
            "expected_test_errors": list(self.expected_test_errors),
            "real_runtime_errors": list(self.real_runtime_errors),
            "critical_runtime_errors": list(self.critical_runtime_errors),
            "expected_test_count": len(self.expected_test_errors),
            "real_runtime_count": len(self.real_runtime_errors),
            "critical_runtime_count": self.critical_count,
        }


def _is_error_event(payload: dict) -> bool:
    event_type = str(payload.get("event_type", "")).lower()
    message = str(payload.get("message", "")).lower()
    return event_type == "error" or "error" in message


def _matches_any(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def classify_errors(path: Path) -> ErrorClassification:
    """Read errors.jsonl and bucket entries for validation."""
    result = ErrorClassification()
    if not path.exists():
        return result

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not _is_error_event(payload):
                continue

            message = str(payload.get("message", "")).strip() or "unknown error"
            category = str(payload.get("category", "")).lower()
            combined = f"{category} {message}"

            if _matches_any(combined, EXPECTED_TEST_PATTERNS):
                if message not in result.expected_test_errors:
                    result.expected_test_errors.append(message)
                continue

            if _matches_any(combined, CRITICAL_RUNTIME_PATTERNS):
                if message not in result.critical_runtime_errors:
                    result.critical_runtime_errors.append(message)
                continue

            if message not in result.real_runtime_errors:
                result.real_runtime_errors.append(message)

    return result
